"""Top-level orchestrator for the Life Time reservation bot.

The bot prefers Life Time's direct member-login APIs for auth because that
path is stable in CI and does not depend on the browser successfully
completing the SPA redirect chain. Selenium remains as a fallback when the
direct auth path fails or is explicitly disabled.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from lifetime_bot.api import (
    API_BASE,
    SUBSCRIPTION_KEY,
    ClassEvent,
    LifetimeAPIClient,
    LifetimeAPIError,
    RegistrationResult,
    SessionTokens,
    match_class,
)
from lifetime_bot.config import BotConfig
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.utils.timing import get_target_date
from lifetime_bot.webdriver import create_driver

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.support.ui import WebDriverWait


TOKEN_TRIGGER_URL = "https://my.lifetime.life/my-account/reservations.html"
TOKEN_SEARCH_HOST = "api.lifetimefitness.com"
REQUIRED_HEADERS = ("x-ltf-jwe", "x-ltf-profile", "x-ltf-ssoid")
DIRECT_LOGIN_URL = f"{API_BASE}/auth/v2/login"
PROFILE_URL = f"{API_BASE}/user-profile/profile"


class LifetimeReservationBot:
    """Orchestrates login → token extraction → API-driven reservation."""

    def __init__(self, config: BotConfig | None = None) -> None:
        self.config = config or BotConfig.from_env()
        self.email_service = EmailNotificationService(self.config.email)
        self.sms_service = SMSNotificationService(self.config.sms)
        self.driver: WebDriver | None = None
        self.wait: WebDriverWait | None = None
        self.api_session: requests.Session | None = None

    # -- Public entry point --------------------------------------------------

    def reserve_class(self) -> bool:
        """Run the full login → find class → register flow. Raises on failure."""
        target_date = self._get_target_date()
        class_details = self._get_class_details(target_date)

        try:
            tokens = self._login_and_extract_tokens()
        except Exception as exc:
            self._report_failure(exc, class_details, phase="login")
            raise

        client = LifetimeAPIClient(tokens, session=self.api_session)
        try:
            event = self._find_target_event(client, target_date)
            if event is None:
                raise LifetimeAPIError(
                    f"Target class not found in schedule for {target_date}. "
                    f"Looked for name~='{self.config.target_class.name}' "
                    f"instructor~='{self.config.target_class.instructor or '(ignored)'}' "
                    f"at {self.config.target_class.start_time}-{self.config.target_class.end_time}."
                )
            print(
                f"Matched class '{event.name}' with {event.instructor} at "
                f"{event.start} (event id {event.event_id})."
            )

            result = self._detect_existing_registration(
                client, event.event_id, context="preflight"
            )
            if result is None:
                try:
                    result = client.register(event.event_id)
                    print(
                        f"POST /event → registrationId={result.registration_id} "
                        f"status={result.status or 'unknown'} "
                        f"needs_complete={result.needs_complete}"
                    )
                except LifetimeAPIError:
                    result = self._detect_existing_registration(
                        client, event.event_id, context="post-error check"
                    )
                    if result is None:
                        raise
                    print(
                        "POST /event failed, but follow-up registration info "
                        "shows the class is already reserved."
                    )

            if result.needs_complete:
                documents = result.required_documents or self._fetch_required_documents(
                    client, event.event_id
                )
                client.complete_registration(
                    result.registration_id,
                    accepted_documents=documents,
                )
                print(
                    f"PUT /complete succeeded "
                    f"(accepted documents: {documents or []})."
                )
        except Exception as exc:
            self._report_failure(exc, class_details, phase="reservation")
            raise

        subject, body = self._describe_outcome(result, class_details)
        self.send_notification(subject, body)
        return True

    # -- Notifications -------------------------------------------------------

    def send_notification(self, subject: str, message: str) -> None:
        method = self.config.notification_method
        if method in {"email", "both"}:
            if self.email_service.send(subject, message):
                print(f"Notification sent via email: {subject}")
            else:
                print(f"Failed to send email notification: {subject}")
        if method in {"sms", "both"}:
            if self.sms_service.send(subject, message):
                print(f"Notification sent via SMS: {subject}")
            else:
                print(f"Failed to send SMS notification: {subject}")

    def _login_and_extract_tokens(self) -> SessionTokens:
        direct_error: Exception | None = None
        if self.config.auth_mode in {"auto", "direct"}:
            try:
                return self._login_via_api()
            except Exception as exc:
                direct_error = exc
                print(f"Direct API auth failed: {exc}")
                if self.config.auth_mode == "direct":
                    raise

        if self.config.auth_mode in {"auto", "browser"}:
            try:
                return self._login_and_extract_tokens_via_browser()
            except Exception as exc:
                if direct_error is None:
                    raise
                raise LifetimeAPIError(
                    "Both auth flows failed. "
                    f"Direct API auth: {direct_error}. Browser auth: {exc}."
                ) from exc

        raise LifetimeAPIError(f"Unsupported AUTH_MODE {self.config.auth_mode!r}")

    # -- Direct API auth ----------------------------------------------------

    def _login_via_api(self) -> SessionTokens:
        session = requests.Session()
        self.api_session = None
        login_response = session.post(
            DIRECT_LOGIN_URL,
            headers=self._direct_auth_headers(),
            json={
                "username": self.config.username,
                "password": self.config.password,
            },
            timeout=30,
        )
        payload = self._json_or_error(login_response, context="auth/v2/login")
        if str(payload.get("status", "")) != "0" or payload.get("message") != "Success":
            raise LifetimeAPIError(
                "Direct member login was rejected: "
                f"{payload.get('message') or login_response.text[:300]}"
            )

        auth_token = str(payload.get("token") or "").strip()
        ssoid = str(payload.get("ssoId") or payload.get("ssoid") or "").strip()
        if not auth_token or not ssoid:
            raise LifetimeAPIError(
                "Direct member login did not return the expected token and ssoId"
            )

        profile_response = session.get(
            PROFILE_URL,
            headers=self._direct_auth_headers(auth_token=auth_token, ssoid=ssoid),
            timeout=30,
        )
        profile_payload = self._json_or_error(
            profile_response, context="user-profile/profile"
        )
        member_details = profile_payload.get("memberDetails") or {}
        member_id = member_details.get("memberId")
        if member_id is None:
            raise LifetimeAPIError(
                "Profile API did not return memberDetails.memberId after login"
            )

        self.api_session = session
        print("Authenticated via direct API login.")
        return SessionTokens(
            jwe=auth_token,
            profile=str(profile_payload.get("jwt") or ""),
            ssoid=ssoid,
            member_id_override=int(member_id),
        )

    def _direct_auth_headers(
        self, *, auth_token: str | None = None, ssoid: str | None = None
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
            "Origin": "https://my.lifetime.life",
            "Referer": self.config.login_url,
            "User-Agent": "Mozilla/5.0",
        }
        if auth_token:
            headers["Authorization"] = auth_token
            headers["X-LTF-JWE"] = auth_token
        if ssoid:
            headers["X-LTF-SSOID"] = ssoid
        return headers

    def _json_or_error(
        self, response: requests.Response, *, context: str
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise LifetimeAPIError(
                f"{context} returned non-JSON response: {response.text[:300]}"
            ) from exc
        if not response.ok:
            raise LifetimeAPIError(
                f"{context} returned {response.status_code}: {response.text[:300]}"
            )
        if not isinstance(payload, dict):
            raise LifetimeAPIError(f"{context} returned unexpected payload: {payload!r}")
        return payload

    # -- Selenium phase ------------------------------------------------------

    def _login_and_extract_tokens_via_browser(self) -> SessionTokens:
        self.api_session = None
        self.driver, self.wait = create_driver(headless=self.config.headless)
        try:
            self.login()
            return self._extract_tokens()
        finally:
            try:
                if self.driver is not None:
                    self.driver.quit()
            except Exception as exc:
                print(f"Error closing Selenium session: {exc}")
            finally:
                self.driver = None
                self.wait = None

    def login(self) -> None:
        """Complete the Azure B2C login flow.

        Life Time has shipped both the legacy Azure B2C field ids
        (``signInName`` / ``password``) and the newer first-party login
        ids (``account-username`` / ``account-password``). Support both so
        the browser fallback survives markup flips.
        """
        assert self.driver is not None and self.wait is not None
        self.driver.get(self.config.login_url)
        self._find_login_input("signInName", "account-username").send_keys(
            self.config.username
        )
        self._find_login_input("password", "account-password").send_keys(
            self.config.password + Keys.RETURN
        )

        def _login_complete(driver: WebDriver) -> bool:
            url = driver.current_url.lower()
            return (
                "my.lifetime.life" in url
                and "/login.html" not in url
                and "b2clogin.com" not in url
            )

        self.wait.until(_login_complete)
        time.sleep(2)
        print(f"Logged in successfully. Landed on: {self.driver.current_url}")

    def _find_login_input(self, *candidate_ids: str):
        assert self.driver is not None and self.wait is not None

        def _locate(driver: WebDriver):
            for candidate_id in candidate_ids:
                elements = driver.find_elements(By.ID, candidate_id)
                if elements:
                    return elements[0]
            return False

        return self.wait.until(_locate)

    def _extract_tokens(self, *, attempts: int = 3) -> SessionTokens:
        """Lift x-ltf-jwe / x-ltf-profile / x-ltf-ssoid from the live session.

        The SPA fires authenticated calls to api.lifetimefitness.com on
        almost every page load. We navigate to a known-authenticated page
        and then mine the Chrome performance log for the first such
        request, reading its headers verbatim.
        """
        assert self.driver is not None
        for attempt in range(1, attempts + 1):
            try:
                self.driver.get(TOKEN_TRIGGER_URL)
            except Exception as exc:
                print(f"Attempt {attempt}: error navigating to trigger page: {exc}")
            time.sleep(3)

            headers = self._find_lifetime_api_headers()
            missing = [h for h in REQUIRED_HEADERS if not headers.get(h)]
            if not missing:
                return SessionTokens(
                    jwe=headers["x-ltf-jwe"],
                    profile=headers["x-ltf-profile"],
                    ssoid=headers["x-ltf-ssoid"],
                )
            print(
                f"Attempt {attempt}/{attempts}: missing headers {missing} "
                f"(saw {sorted(headers.keys())})"
            )
            time.sleep(2)

        raise LifetimeAPIError(
            "Could not extract session tokens from browser after "
            f"{attempts} attempts. The SPA may have changed its auth flow."
        )

    def _find_lifetime_api_headers(self) -> dict[str, str]:
        assert self.driver is not None
        try:
            entries = self.driver.get_log("performance")
        except Exception as exc:
            print(f"Could not read performance log: {exc}")
            return {}

        best: dict[str, str] = {}
        for entry in reversed(entries):
            try:
                msg = json.loads(entry["message"])["message"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if msg.get("method") != "Network.requestWillBeSent":
                continue
            request = msg.get("params", {}).get("request", {})
            url = request.get("url", "")
            if TOKEN_SEARCH_HOST not in url:
                continue
            headers = {k.lower(): v for k, v in (request.get("headers") or {}).items()}
            if all(h in headers for h in REQUIRED_HEADERS):
                return headers
            # Keep the best partial match as a fallback for diagnostics.
            if len(headers) > len(best):
                best = headers
        return best

    # -- API phase -----------------------------------------------------------

    def _find_target_event(
        self, client: LifetimeAPIClient, target_date: str
    ) -> ClassEvent | None:
        tc = self.config.target_class
        try:
            day = datetime.fromisoformat(target_date)
        except ValueError as exc:
            raise LifetimeAPIError(
                f"TARGET_DATE must be YYYY-MM-DD, got {target_date!r}"
            ) from exc

        week_start = day - timedelta(days=(day.weekday() + 1) % 7)
        week_end = week_start + timedelta(days=7)
        classes = client.list_classes(
            location=self.config.club.name,
            start=week_start,
            end=week_end,
        )
        print(f"Schedule API returned {len(classes)} classes for {target_date}.")
        match = match_class(
            classes,
            name_contains=tc.name,
            instructor_contains=tc.instructor,
            start_time_local=tc.start_time,
            end_time_local=tc.end_time,
            date_iso=target_date,
        )
        if match is not None or not tc.instructor:
            return match

        fallback = match_class(
            classes,
            name_contains=tc.name,
            instructor_contains="",
            start_time_local=tc.start_time,
            end_time_local=tc.end_time,
            date_iso=target_date,
        )
        if fallback is not None and not fallback.instructor.strip():
            print(
                "Matched a class with no listed instructor; "
                f"ignoring configured instructor filter {tc.instructor!r}."
            )
            return fallback
        return None

    def _fetch_required_documents(
        self, client: LifetimeAPIClient, event_id: str
    ) -> list[int] | None:
        try:
            info = client.get_registration_info(event_id)
        except LifetimeAPIError as exc:
            print(f"Could not fetch registration info for required docs: {exc}")
            return None
        return _extract_required_doc_ids(info)

    def _detect_existing_registration(
        self, client: LifetimeAPIClient, event_id: str, *, context: str
    ) -> RegistrationResult | None:
        try:
            info = client.get_registration_info(event_id)
        except LifetimeAPIError as exc:
            print(f"Could not fetch registration info during {context}: {exc}")
            return None

        member = _find_registered_member(info, client.member_id)
        if member is None:
            return None

        member_name = str(member.get("name") or "Current member")
        print(
            f"Registration info ({context}) shows {member_name} "
            f"({client.member_id}) is already reserved for event {event_id}."
        )
        return RegistrationResult(
            registration_id=0,
            status="already_reserved",
            needs_complete=False,
            required_documents=None,
            raw=info,
        )

    # -- Reporting helpers ---------------------------------------------------

    def _get_target_date(self) -> str:
        return get_target_date(
            self.config.run_on_schedule,
            self.config.target_class.date,
        )

    def _get_class_details(self, target_date: str) -> str:
        tc = self.config.target_class
        instructor = tc.instructor or "(ignored)"
        return (
            f"Class: {tc.name}\n"
            f"Instructor: {instructor}\n"
            f"Date: {target_date}\n"
            f"Time: {tc.start_time} - {tc.end_time}\n"
            f"Club: {self.config.club.name}"
        )

    def _describe_outcome(
        self, result: RegistrationResult, class_details: str
    ) -> tuple[str, str]:
        if result.was_already_reserved:
            return (
                "Lifetime Bot - Already Reserved",
                "This class was already on your account, so no new reservation "
                f"was submitted.\n\n{class_details}",
            )
        if result.was_waitlisted:
            return (
                "Lifetime Bot - Added to Waitlist",
                f"The class was full — you were added to the waitlist.\n\n{class_details}",
            )
        if result.was_reserved or not result.needs_complete:
            return (
                "Lifetime Bot - Reserved",
                f"Your class was successfully reserved!\n\n{class_details}",
            )
        status = result.status or "unknown"
        return (
            f"Lifetime Bot - Registered ({status})",
            f"Registration completed (status: {status}).\n\n{class_details}",
        )

    def _report_failure(
        self, exc: BaseException, class_details: str, *, phase: str
    ) -> None:
        error_type = type(exc).__name__
        print(f"{phase.title()} failed ({error_type}): {exc}")
        print(traceback.format_exc())
        subject = (
            "Lifetime Bot - Login Failed"
            if phase == "login"
            else "Lifetime Bot - Failure"
        )
        self.send_notification(
            subject,
            f"{phase.title()} failed:\n\n{class_details}\n\n"
            f"Error ({error_type}): {exc!s}",
        )


def _extract_required_doc_ids(info: dict[str, Any]) -> list[int] | None:
    """Pull waiver/document ids out of an /events/{id}/registration response."""
    for key in ("requiredDocuments", "documents", "waivers", "acceptedDocuments"):
        value = info.get(key)
        if not isinstance(value, list):
            continue
        ids: list[int] = []
        for doc in value:
            if isinstance(doc, int):
                ids.append(doc)
            elif isinstance(doc, dict):
                doc_id = doc.get("id")
                if isinstance(doc_id, int):
                    ids.append(doc_id)
        if ids:
            return ids
    agreement = info.get("agreement")
    if isinstance(agreement, dict):
        agreement_id = agreement.get("agreementId")
        if isinstance(agreement_id, int):
            return [agreement_id]
        if isinstance(agreement_id, str) and agreement_id.isdigit():
            return [int(agreement_id)]
    return None


def _find_registered_member(
    info: dict[str, Any], member_id: int
) -> dict[str, Any] | None:
    registered = info.get("registeredMembers")
    if not isinstance(registered, list):
        return None

    for member in registered:
        if not isinstance(member, dict):
            continue
        current_id = member.get("id")
        try:
            if current_id is not None and int(current_id) == member_id:
                return member
        except (TypeError, ValueError):
            continue
    return None
