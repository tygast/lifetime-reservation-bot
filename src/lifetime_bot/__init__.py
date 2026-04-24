"""Life Time Reservation Bot.

An automated bot for reserving classes at Life Time.
"""

__version__ = "1.0.0"

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import AuthenticatedSession, DirectAPIAuthenticator
from lifetime_bot.bootstrap import (
    create_api_client,
    create_bot,
    create_notifier,
    create_reservation_service,
)
from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig, EmailConfig, SMSConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.messages import describe_failure, describe_outcome, format_class_details
from lifetime_bot.models import (
    ClassEvent,
    RegistrationOutcome,
    RegistrationResult,
    SessionTokens,
)
from lifetime_bot.notifier import (
    NotificationAttempt,
    NotificationCoordinator,
    NotificationDispatchResult,
)
from lifetime_bot.reservations import ReservationService
from lifetime_bot.runner import RetryableReservationError, run_bot

__all__ = [
    "LifetimeReservationBot",
    "create_bot",
    "create_api_client",
    "create_reservation_service",
    "create_notifier",
    "AuthenticatedSession",
    "DirectAPIAuthenticator",
    "ReservationService",
    "NotificationCoordinator",
    "NotificationAttempt",
    "NotificationDispatchResult",
    "BotConfig",
    "EmailConfig",
    "SMSConfig",
    "LifetimeAPIClient",
    "run_bot",
    "RetryableReservationError",
    "LifetimeAPIError",
    "format_class_details",
    "describe_outcome",
    "describe_failure",
    "SessionTokens",
    "ClassEvent",
    "RegistrationOutcome",
    "RegistrationResult",
]
