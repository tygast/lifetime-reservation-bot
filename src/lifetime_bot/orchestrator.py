"""Application orchestrator for the Life Time reservation bot."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from typing import Protocol

from lifetime_bot.auth import AuthenticatedSession
from lifetime_bot.config import BotConfig, ClassConfig, NotificationMethod
from lifetime_bot.errors import LifetimeAPIError, ReservationAttemptError
from lifetime_bot.messages import describe_failure, describe_outcome, format_class_details
from lifetime_bot.models import ClassEvent, RegistrationResult
from lifetime_bot.notifier import NotificationDispatchResult
from lifetime_bot.utils.timing import get_target_date


class Authenticator(Protocol):
    """Boundary for member authentication."""

    def login(self, username: str, password: str) -> AuthenticatedSession: ...


class Notifier(Protocol):
    """Boundary for fan-out notification delivery."""

    def send(
        self,
        subject: str,
        message: str,
        *,
        method: NotificationMethod,
    ) -> NotificationDispatchResult: ...


class ReservationServiceLike(Protocol):
    """Boundary for class lookup and reservation lifecycle operations."""

    def find_target_event(
        self,
        *,
        club_name: str,
        target_class: ClassConfig,
        target_date: str,
    ) -> ClassEvent | None: ...

    def reserve_event(self, event_id: str) -> RegistrationResult: ...


ReservationServiceFactory = Callable[[AuthenticatedSession], ReservationServiceLike]


class ReservationOrchestrator:
    """Orchestrates direct auth, schedule lookup, reservation, and notification."""

    def __init__(
        self,
        config: BotConfig,
        *,
        authenticator: Authenticator,
        notifier: Notifier,
        reservation_service_factory: ReservationServiceFactory,
    ) -> None:
        self.config = config
        self.authenticator = authenticator
        self.notifier = notifier
        self.reservation_service_factory = reservation_service_factory

    def reserve_class(self) -> RegistrationResult:
        """Run the full auth → find class → reserve flow. Raises on failure."""
        started = time.perf_counter()
        target_date = self._get_target_date()
        class_details = format_class_details(self.config, target_date)

        try:
            auth_started = time.perf_counter()
            authenticated = self.authenticator.login(
                self.config.username,
                self.config.password,
            )
            print(f"Auth completed in {time.perf_counter() - auth_started:.2f}s.")
        except Exception as exc:
            self._log_failure(exc, phase="login")
            raise ReservationAttemptError("login", exc) from exc

        reservation_service = self.reservation_service_factory(authenticated)
        try:
            lookup_started = time.perf_counter()
            event = reservation_service.find_target_event(
                club_name=self.config.club.name,
                target_class=self.config.target_class,
                target_date=target_date,
            )
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
            result = reservation_service.reserve_event(event.event_id)
            print(
                "Reservation API phase completed in "
                f"{time.perf_counter() - registration_started:.2f}s."
            )
        except Exception as exc:
            self._log_failure(exc, phase="reservation")
            raise ReservationAttemptError("reservation", exc) from exc

        subject, _ = describe_outcome(result, class_details)
        print(f"Reservation outcome: {subject.removeprefix('Lifetime Bot - ')}.")
        print(
            f"Reservation flow core completed in {time.perf_counter() - started:.2f}s."
        )
        return result

    def build_outcome_notification(
        self, result: RegistrationResult
    ) -> tuple[str, str]:
        class_details = self._class_details()
        return describe_outcome(result, class_details)

    def build_failure_notification(self, exc: BaseException) -> tuple[str, str]:
        class_details = self._class_details()
        phase = "reservation"
        root_exc = exc
        if isinstance(exc, ReservationAttemptError):
            phase = exc.phase
            root_exc = exc.cause
        return describe_failure(root_exc, class_details=class_details, phase=phase)

    def send_notification(
        self, subject: str, message: str
    ) -> NotificationDispatchResult:
        return self.notifier.send(
            subject,
            message,
            method=self.config.notification_method,
        )

    def _get_target_date(self) -> str:
        return get_target_date(
            self.config.run_on_schedule,
            self.config.target_class.date,
        )

    def _class_details(self) -> str:
        return format_class_details(self.config, self._get_target_date())

    def _log_failure(self, exc: BaseException, *, phase: str) -> None:
        error_type = type(exc).__name__
        print(f"{phase.title()} failed ({error_type}): {exc}")
        print(traceback.format_exc())
