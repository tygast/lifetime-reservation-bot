"""Top-level orchestrator for the Life Time reservation bot.

Selenium is used only long enough to complete Azure B2C login and lift the
per-session ``x-ltf-*`` headers out of the browser's network log. Once
those tokens are in hand the browser is closed and every subsequent
action — schedule lookup, reservation, waitlist, waiver acceptance —
runs through the JSON API (:mod:`lifetime_bot.api`).
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from lifetime_bot.api import (
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


class LifetimeReservationBot:
    """Orchestrates login → token extraction → API-driven reservation."""

    def __init__(self, config: BotConfig | None = None) -> None:
        self.config = config or BotConfig.from_env()
        self.email_service = EmailNotificationService(self.config.email)
        self.sms_service = SMSNotificationService(self.config.sms)
        self.driver: WebDriver | None = None
        self.wait: WebDriverWait | None = None

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

        client = LifetimeAPIClient(tokens)
        try:
            event = self._find_target_event(client, target_date)
            if event is None:
                raise LifetimeAPIError(
                    f"Target class not found in schedule for {target_date}. "
                    f"Looked for name~='{self.config.target_class.name}' "
                    f"instructor~='{self.config.target_class.instructor}' "
                    f"at {self.config.target_class.start_time}-{self.config.target_class.end_time}."
                )
            print(
                f"Matched class '{event.name}' with {event.instructor} at "
                f"{event.start} (event id {event.event_id})."
            )

            result = client.register(event.event_id)
            print(
                f"POST /event → registrationId={result.registration_id} "
                f"status={result.status or 'unknown'} "
                f"needs_complete={result.needs_complete}"
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

    # -- Selenium phase ------------------------------------------------------

    def _login_and_extract_tokens(self) -> SessionTokens:
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

        Life Time's login form is id=localAccountForm with fields
        id=signInName and id=password. After submit, wait for the B2C
        redirect chain to settle on my.lifetime.life before returning.
        """
        assert self.driver is not None and self.wait is not None
        self.driver.get(self.config.login_url)
        self.wait.until(EC.presence_of_element_located((By.ID, "signInName"))).send_keys(
            self.config.username
        )
        self.wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(
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

        classes = client.list_classes(
            location=self.config.club.name,
            start=day,
            end=day,
        )
        print(f"Schedule API returned {len(classes)} classes for {target_date}.")
        return match_class(
            classes,
            name_contains=tc.name,
            instructor_contains=tc.instructor,
            start_time_local=tc.start_time,
            end_time_local=tc.end_time,
            date_iso=target_date,
        )

    def _fetch_required_documents(
        self, client: LifetimeAPIClient, event_id: str
    ) -> list[int] | None:
        try:
            info = client.get_registration_info(event_id)
        except LifetimeAPIError as exc:
            print(f"Could not fetch registration info for required docs: {exc}")
            return None
        return _extract_required_doc_ids(info)

    # -- Reporting helpers ---------------------------------------------------

    def _get_target_date(self) -> str:
        return get_target_date(
            self.config.run_on_schedule,
            self.config.target_class.date,
        )

    def _get_class_details(self, target_date: str) -> str:
        tc = self.config.target_class
        return (
            f"Class: {tc.name}\n"
            f"Instructor: {tc.instructor}\n"
            f"Date: {target_date}\n"
            f"Time: {tc.start_time} - {tc.end_time}\n"
            f"Club: {self.config.club.name}"
        )

    def _describe_outcome(
        self, result: RegistrationResult, class_details: str
    ) -> tuple[str, str]:
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
    return None
