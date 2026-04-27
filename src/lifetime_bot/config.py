"""Configuration management for the Lifetime Reservation Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

NotificationMethod = Literal["email", "sms", "both"]
NO_INSTRUCTOR_VALUES = frozenset(
    {"", "any", "ignore", "ignored", "n/a", "na", "no instructor", "none"}
)


@dataclass
class EmailConfig:
    """Email notification configuration."""

    sender: str
    password: str
    receiver: str
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587

    @classmethod
    def from_env(cls) -> EmailConfig:
        """Create EmailConfig from environment variables."""
        return cls(
            sender=os.getenv("EMAIL_SENDER", ""),
            password=os.getenv("EMAIL_PASSWORD", ""),
            receiver=os.getenv("EMAIL_RECEIVER", ""),
            smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
        )

    def is_valid(self) -> bool:
        """Check if email configuration is valid."""
        return bool(self.sender and self.password and self.receiver)


@dataclass
class SMSConfig:
    """SMS notification configuration using Twilio."""

    account_sid: str
    auth_token: str
    from_number: str
    to_number: str

    @classmethod
    def from_env(cls) -> SMSConfig:
        """Create SMSConfig from environment variables."""
        return cls(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
            to_number=os.getenv("SMS_NUMBER", ""),
        )

    def is_valid(self) -> bool:
        """Check if SMS configuration is valid."""
        return bool(
            self.account_sid and self.auth_token and self.from_number and self.to_number
        )


@dataclass
class NotificationConfig:
    """Notification-only configuration."""

    email: EmailConfig
    sms: SMSConfig
    method: NotificationMethod

    @classmethod
    def from_env(cls, reload_env: bool = True) -> NotificationConfig:
        """Create NotificationConfig from environment variables."""
        if reload_env:
            load_dotenv(override=True)
        return cls(
            email=EmailConfig.from_env(),
            sms=SMSConfig.from_env(),
            method=_notification_method_from_env(),
        )


@dataclass
class ClassConfig:
    """Target class configuration."""

    name: str
    instructor: str
    date: str
    start_time: str
    end_time: str

    @classmethod
    def from_env(cls) -> ClassConfig:
        """Create ClassConfig from environment variables."""
        return cls(
            name=os.getenv("TARGET_CLASS", ""),
            instructor=_normalize_instructor_filter(
                os.getenv("TARGET_INSTRUCTOR", "")
            ),
            date=os.getenv("TARGET_DATE", ""),
            start_time=os.getenv("START_TIME", ""),
            end_time=os.getenv("END_TIME", "10:00 AM"),
        )


@dataclass
class ClubConfig:
    """Life Time club configuration."""

    name: str

    @classmethod
    def from_env(cls) -> ClubConfig:
        """Create ClubConfig from environment variables."""
        name = os.getenv("LIFETIME_CLUB_NAME", "")
        if not name:
            raise ValueError(
                "LIFETIME_CLUB_NAME environment variable is required"
            )
        return cls(name=name)


@dataclass
class BotConfig:
    """Main bot configuration."""

    username: str
    password: str
    club: ClubConfig
    target_class: ClassConfig
    email: EmailConfig
    sms: SMSConfig
    notification_method: NotificationMethod
    run_on_schedule: bool

    @classmethod
    def from_env(cls, reload_env: bool = True) -> BotConfig:
        """Create BotConfig from environment variables.

        Args:
            reload_env: If True, clear and reload environment variables from .env file.
        """
        if reload_env:
            # Overlay .env onto the existing environment so shell-provided
            # variables like PATH remain available to the process.
            load_dotenv(override=True)

        notification_config = NotificationConfig.from_env(reload_env=False)

        return cls(
            username=os.getenv("LIFETIME_USERNAME", ""),
            password=os.getenv("LIFETIME_PASSWORD", ""),
            club=ClubConfig.from_env(),
            target_class=ClassConfig.from_env(),
            email=notification_config.email,
            sms=notification_config.sms,
            notification_method=notification_config.method,
            run_on_schedule=os.getenv("RUN_ON_SCHEDULE", "false").lower() == "true",
        )

    @property
    def notifications(self) -> NotificationConfig:
        """Expose the notification-specific subset of the bot config."""
        return NotificationConfig(
            email=self.email,
            sms=self.sms,
            method=self.notification_method,
        )


def _normalize_instructor_filter(value: str) -> str:
    cleaned = value.strip()
    if cleaned.lower() in NO_INSTRUCTOR_VALUES:
        return ""
    return cleaned


def _notification_method_from_env() -> NotificationMethod:
    notification_method = os.getenv("NOTIFICATION_METHOD", "email").lower()
    if notification_method not in ("email", "sms", "both"):
        return "email"
    return notification_method
