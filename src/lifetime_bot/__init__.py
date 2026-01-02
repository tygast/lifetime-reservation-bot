"""Lifetime Fitness Reservation Bot.

An automated bot for reserving classes at Life Time Fitness.
"""

__version__ = "1.0.0"

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig, EmailConfig, SMSConfig

__all__ = [
    "LifetimeReservationBot",
    "BotConfig",
    "EmailConfig",
    "SMSConfig",
]
