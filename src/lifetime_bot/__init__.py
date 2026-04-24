"""Life Time Reservation Bot.

An automated bot for reserving classes at Life Time.
"""

__version__ = "1.0.0"

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.auth import AuthenticatedSession, DirectAPIAuthenticator
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

__all__ = [
    "LifetimeReservationBot",
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
    "LifetimeAPIError",
    "format_class_details",
    "describe_outcome",
    "describe_failure",
    "SessionTokens",
    "ClassEvent",
    "RegistrationOutcome",
    "RegistrationResult",
]
