"""Top-level orchestrator for the Life Time reservation bot."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from typing import Protocol

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import AuthenticatedSession, DirectAPIAuthenticator
from lifetime_bot.config import BotConfig, NotificationMethod
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.messages import describe_failure, describe_outcome, format_class_details
from lifetime_bot.models import RegistrationResult
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.notifier import NotificationCoordinator, NotificationDispatchResult
from lifetime_bot.reservations import ReservationService
from lifetime_bot.utils.timing import get_target_date

HTTP_TIMEOUT_SECONDS = 10.0
NOTIFICATION_TIMEOUT_SECONDS = 5.0


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


APIClientFactory = Callable[[AuthenticatedSession, float], LifetimeAPIClient]
ReservationServiceFactory = Callable[[LifetimeAPIClient], ReservationService]


class LifetimeReservationBot:
    """Orchestrates direct auth, schedule lookup, reservation, and notification."""

    def __init__(
        self,
        config: BotConfig | None = None,
        *,
        authenticator: Authenticator | None = None,
        notifier: Notifier | None = None,
        api_client_factory: APIClientFactory | None = None,
        reservation_service_factory: ReservationServiceFactory | None = None,
    ) -> None:
        self.config = config or BotConfig.from_env()
        self.authenticator = authenticator or DirectAPIAuthenticator(
            timeout=HTTP_TIMEOUT_SECONDS
        )
        self.notifier = notifier or _build_default_notifier(self.config)
        self.api_client_factory = api_client_factory or _build_api_client
        self.reservation_service_factory = (
            reservation_service_factory or ReservationService
        )

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
            self._report_failure(exc, class_details, phase="login")
            raise

        client = self.api_client_factory(authenticated, HTTP_TIMEOUT_SECONDS)
        reservation_service = self.reservation_service_factory(client)
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
            self._report_failure(exc, class_details, phase="reservation")
            raise

        subject, body = describe_outcome(result, class_details)
        print(f"Reservation outcome: {subject.removeprefix('Lifetime Bot - ')}.")
        print(
            f"Reservation flow core completed in {time.perf_counter() - started:.2f}s."
        )
        self.send_notification(subject, body)
        print(f"Reservation flow finished in {time.perf_counter() - started:.2f}s.")
        return result

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

    def _report_failure(
        self, exc: BaseException, class_details: str, *, phase: str
    ) -> None:
        error_type = type(exc).__name__
        print(f"{phase.title()} failed ({error_type}): {exc}")
        print(traceback.format_exc())
        subject, body = describe_failure(exc, class_details=class_details, phase=phase)
        self.send_notification(subject, body)


def _build_api_client(
    authenticated: AuthenticatedSession, timeout: float
) -> LifetimeAPIClient:
    return LifetimeAPIClient(
        authenticated.tokens,
        session=authenticated.session,
        timeout=timeout,
    )


def _build_default_notifier(config: BotConfig) -> NotificationCoordinator:
    return NotificationCoordinator(
        email_service=EmailNotificationService(config.email),
        sms_service=SMSNotificationService(config.sms),
        timeout_seconds=NOTIFICATION_TIMEOUT_SECONDS,
    )
