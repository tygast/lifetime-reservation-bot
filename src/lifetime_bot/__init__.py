"""Life Time Reservation Bot.

An automated bot for reserving classes at Life Time.
"""

__version__ = "1.0.0"

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig, EmailConfig, SMSConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import (
    ClassEvent,
    RegistrationOutcome,
    RegistrationResult,
    SessionTokens,
)

__all__ = [
    "LifetimeReservationBot",
    "BotConfig",
    "EmailConfig",
    "SMSConfig",
    "LifetimeAPIClient",
    "LifetimeAPIError",
    "SessionTokens",
    "ClassEvent",
    "RegistrationOutcome",
    "RegistrationResult",
]
