"""Top-level orchestrator for the Life Time reservation bot."""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

import requests

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

DIRECT_LOGIN_URL = f"{API_BASE}/auth/v2/login"
PROFILE_URL = f"{API_BASE}/user-profile/profile"
HTTP_TIMEOUT_SECONDS = 10.0
NOTIFICATION_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class TimedAttemptResult:
    """Outcome of a bounded callback execution."""

    completed: bool
    succeeded: bool
    error: str | None = None


class LifetimeReservationBot:
    """Orchestrates direct auth → schedule lookup → API-driven reservation."""

    def __init__(self, config: BotConfig | None = None) -> None:
        self.config = config or BotConfig.from_env()
        self.email_service = EmailNotificationService(self.config.email)
        self.sms_service = SMSNotificationService(self.config.sms)
        self.api_session: requests.Session | None = None

    # -- Public entry point --------------------------------------------------

    def reserve_class(self) -> bool:
        """Run the full login → find class → register flow. Raises on failure."""
        started = time.perf_counter()
        target_date = self._get_target_date()
        class_details = self._get_class_details(target_date)

        try:
            auth_started = time.perf_counter()
            tokens = self._login_and_extract_tokens()
            print(f"Auth completed in {time.perf_counter() - auth_started:.2f}s.")
        except Exception as exc:
            self._report_failure(exc, class_details, phase="login")
            raise

        client = LifetimeAPIClient(
            tokens,
            session=self.api_session,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        try:
            lookup_started = time.perf_counter()
            event = self._find_target_event(client, target_date)
            if event is None:
                raise LifetimeAPIError(
                    f"Target class not found in schedule for {target_date}. "
                    f"Looked for name~='{self.config.target_class.name}' "
                    f"instructor~='{self.config.target_class.instructor or '(ignored)'}' "
                    f"at {self.config.target_class.start_time}-{self.config.target_class.end_time}."
                )
            print(
                f"Schedule lookup completed in {time.perf_counter() - lookup_started:.2f}s."
            )
            print(
                f"Matched class '{event.name}' with {event.instructor} at "
                f"{event.start} (event id {event.event_id})."
            )

            registration_started = time.perf_counter()
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
            print(
                "Reservation API phase completed in "
                f"{time.perf_counter() - registration_started:.2f}s."
            )
        except Exception as exc:
            self._report_failure(exc, class_details, phase="reservation")
            raise

        subject, body = self._describe_outcome(result, class_details)
        print(f"Reservation outcome: {subject.removeprefix('Lifetime Bot - ')}.")
        print(
            f"Reservation flow core completed in {time.perf_counter() - started:.2f}s."
        )
        self.send_notification(subject, body)
        print(f"Reservation flow finished in {time.perf_counter() - started:.2f}s.")
        return True

    # -- Notifications -------------------------------------------------------

    def send_notification(self, subject: str, message: str) -> None:
        method = self.config.notification_method
        print(f"Notification phase started: {subject}")
        if method in {"email", "both"}:
            started = time.perf_counter()
            result = _run_with_timeout(
                lambda: self.email_service.send(subject, message),
                timeout_seconds=NOTIFICATION_TIMEOUT_SECONDS,
            )
            if not result.completed:
                print(
                    f"Email notification timed out after "
                    f"{NOTIFICATION_TIMEOUT_SECONDS:.2f}s: {subject}"
                )
            elif result.error:
                print(f"Email notification failed: {result.error}")
            elif result.succeeded:
                print(f"Notification sent via email: {subject}")
            else:
                print(f"Email notification service reported failure: {subject}")
            print(
                f"Email notification attempt completed in "
                f"{time.perf_counter() - started:.2f}s."
            )
        if method in {"sms", "both"}:
            started = time.perf_counter()
            result = _run_with_timeout(
                lambda: self.sms_service.send(subject, message),
                timeout_seconds=NOTIFICATION_TIMEOUT_SECONDS,
            )
            if not result.completed:
                print(
                    f"SMS notification timed out after "
                    f"{NOTIFICATION_TIMEOUT_SECONDS:.2f}s: {subject}"
                )
            elif result.error:
                print(f"SMS notification failed: {result.error}")
            elif result.succeeded:
                print(f"Notification sent via SMS: {subject}")
            else:
                print(f"SMS notification service reported failure: {subject}")
            print(
                f"SMS notification attempt completed in "
                f"{time.perf_counter() - started:.2f}s."
            )

    def _login_and_extract_tokens(self) -> SessionTokens:
        return self._login_via_api()

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
            timeout=HTTP_TIMEOUT_SECONDS,
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
            timeout=HTTP_TIMEOUT_SECONDS,
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
            "Referer": "https://my.lifetime.life/",
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

        registered = info.get("registeredMembers")
        unregistered = info.get("unregisteredMembers")
        register_cta = "yes" if info.get("registerCta") else "no"
        if isinstance(registered, list) or isinstance(unregistered, list):
            print(
                f"Registration info ({context}): "
                f"registered={len(registered) if isinstance(registered, list) else 0} "
                f"unregistered={len(unregistered) if isinstance(unregistered, list) else 0} "
                f"registerCta={register_cta}"
            )

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


def _run_with_timeout(
    callback: Callable[[], bool], *, timeout_seconds: float
) -> TimedAttemptResult:
    result: dict[str, Any] = {"done": False, "value": False, "error": None}

    def _target() -> None:
        try:
            result["value"] = bool(callback())
        except Exception as exc:  # pragma: no cover - exercised through caller logs
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["value"] = False
        finally:
            result["done"] = True

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if not result["done"]:
        return TimedAttemptResult(completed=False, succeeded=False)
    return TimedAttemptResult(
        completed=True,
        succeeded=bool(result["value"]),
        error=result["error"],
    )
