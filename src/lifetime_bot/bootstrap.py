"""Runtime wiring for the production reservation bot."""

from __future__ import annotations

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import AuthenticatedSession, DirectAPIAuthenticator
from lifetime_bot.config import BotConfig
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.notifier import NotificationCoordinator
from lifetime_bot.orchestrator import ReservationOrchestrator
from lifetime_bot.reservations import ReservationService

HTTP_TIMEOUT_SECONDS = 10.0
NOTIFICATION_TIMEOUT_SECONDS = 5.0


def create_bot(config: BotConfig | None = None) -> ReservationOrchestrator:
    """Build a production-ready reservation bot with concrete collaborators."""

    config = config or BotConfig.from_env()
    return ReservationOrchestrator(
        config=config,
        authenticator=DirectAPIAuthenticator(timeout=HTTP_TIMEOUT_SECONDS),
        notifier=create_notifier(config),
        reservation_service_factory=create_reservation_service,
    )


def create_api_client(authenticated: AuthenticatedSession) -> LifetimeAPIClient:
    """Create the Life Time API client for an authenticated member session."""

    return LifetimeAPIClient(
        authenticated.tokens,
        session=authenticated.session,
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def create_reservation_service(authenticated: AuthenticatedSession) -> ReservationService:
    """Create the reservation service for an authenticated member session."""

    return ReservationService(create_api_client(authenticated))


def create_notifier(config: BotConfig) -> NotificationCoordinator:
    """Create the notification coordinator for the configured channels."""

    return NotificationCoordinator(
        email_service=EmailNotificationService(config.email),
        sms_service=SMSNotificationService(config.sms),
        timeout_seconds=NOTIFICATION_TIMEOUT_SECONDS,
    )
