"""Top-level orchestrator for the Life Time reservation bot."""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import requests

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import DirectAPIAuthenticator
from lifetime_bot.config import BotConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationResult, SessionTokens
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.reservations import ReservationService
from lifetime_bot.utils.timing import get_target_date

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
        self.authenticator = DirectAPIAuthenticator(timeout=HTTP_TIMEOUT_SECONDS)
        self.api_session: requests.Session | None = None

    # -- Public entry point --------------------------------------------------

    def reserve_class(self) -> RegistrationResult:
        """Run the full auth → find class → reserve flow. Raises on failure."""
        started = time.perf_counter()
        target_date = self._get_target_date()
        class_details = self._get_class_details(target_date)

        try:
            auth_started = time.perf_counter()
            tokens = self._login_via_api()
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
            result = self._reserve_event(client, event.event_id)
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
        return result

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

    # -- Direct API auth ----------------------------------------------------

    def _login_via_api(self) -> SessionTokens:
        authenticated = self.authenticator.login(
            self.config.username,
            self.config.password,
        )
        self.api_session = authenticated.session
        return authenticated.tokens

    # -- API phase -----------------------------------------------------------

    def _find_target_event(
        self, client: LifetimeAPIClient, target_date: str
    ) -> ClassEvent | None:
        return self._reservation_service(client).find_target_event(
            club_name=self.config.club.name,
            target_class=self.config.target_class,
            target_date=target_date,
        )

    def _reserve_event(
        self, client: LifetimeAPIClient, event_id: str
    ) -> RegistrationResult:
        return self._reservation_service(client).reserve_event(event_id)

    def _fetch_required_documents(
        self, client: LifetimeAPIClient, event_id: str
    ) -> list[int] | None:
        return self._reservation_service(client).fetch_required_documents(event_id)

    def _detect_existing_registration(
        self, client: LifetimeAPIClient, event_id: str, *, context: str
    ) -> RegistrationResult | None:
        return self._reservation_service(client).detect_existing_registration(
            event_id,
            context=context,
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
        if result.was_reserved:
            return (
                "Lifetime Bot - Reserved",
                f"Your class was successfully reserved!\n\n{class_details}",
            )
        status = result.display_status
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

    def _reservation_service(self, client: LifetimeAPIClient) -> ReservationService:
        return ReservationService(client)


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
