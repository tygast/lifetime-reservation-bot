"""Runtime wiring for the production reservation bot."""

from __future__ import annotations

import os

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import AuthenticatedSession, DirectAPIAuthenticator
from lifetime_bot.config import BotConfig, NotificationConfig
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.notifier import NotificationCoordinator
from lifetime_bot.orchestrator import ReservationOrchestrator
from lifetime_bot.reservations import ReservationService

HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_NOTIFICATION_TIMEOUT_SECONDS = 300.0


def create_bot(config: BotConfig | None = None) -> ReservationOrchestrator:
    """Build a production-ready reservation bot with concrete collaborators."""

    config = config or BotConfig.from_env()
    return ReservationOrchestrator(
        config=config,
        authenticator=DirectAPIAuthenticator(timeout=HTTP_TIMEOUT_SECONDS),
        notifier=create_notifier(config.notifications),
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


def create_notifier(config: NotificationConfig) -> NotificationCoordinator:
    """Create the notification coordinator for the configured channels."""

    return NotificationCoordinator(
        email_service=EmailNotificationService(config.email),
        sms_service=SMSNotificationService(config.sms),
        timeout_seconds=_get_timeout_seconds(
            "NOTIFICATION_TIMEOUT_SECONDS",
            DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
        ),
    )


def _get_timeout_seconds(env_name: str, default: float) -> float:
    raw_value = os.getenv(env_name)
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        print(
            f"Invalid {env_name} value {raw_value!r}; using default {default:.1f}s."
        )
        return default
