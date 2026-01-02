"""Configuration management for the Lifetime Reservation Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

NotificationMethod = Literal["email", "sms", "both"]

SMS_GATEWAYS: dict[str, str] = {
    "att": "mms.att.net",
    "tmobile": "tmomail.net",
    "verizon": "vtext.com",
    "sprint": "messaging.sprintpcs.com",
    "boost": "sms.myboostmobile.com",
    "cricket": "sms.cricketwireless.net",
    "metro": "mymetropcs.com",
    "uscellular": "email.uscc.net",
    "virgin": "vmobl.com",
    "xfinity": "vtext.com",
    "googlefi": "msg.fi.google.com",
}


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
    """SMS notification configuration."""

    number: str
    carrier: str
    gateways: dict[str, str] = field(default_factory=lambda: SMS_GATEWAYS.copy())

    @classmethod
    def from_env(cls) -> SMSConfig:
        """Create SMSConfig from environment variables."""
        return cls(
            number=os.getenv("SMS_NUMBER", ""),
            carrier=os.getenv("SMS_CARRIER", "").lower(),
        )

    def is_valid(self) -> bool:
        """Check if SMS configuration is valid."""
        return bool(self.number and self.carrier and self.carrier in self.gateways)

    def get_gateway_email(self) -> str:
        """Get the email-to-SMS gateway address."""
        if not self.is_valid():
            raise ValueError(
                f"Invalid SMS configuration. Carrier '{self.carrier}' not in supported carriers: "
                f"{', '.join(self.gateways.keys())}"
            )
        return f"{self.number}@{self.gateways[self.carrier]}"


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
            instructor=os.getenv("TARGET_INSTRUCTOR", ""),
            date=os.getenv("TARGET_DATE", ""),
            start_time=os.getenv("START_TIME", ""),
            end_time=os.getenv("END_TIME", "10:00 AM"),
        )


@dataclass
class ClubConfig:
    """Life Time club configuration."""

    name: str
    state: str

    @classmethod
    def from_env(cls) -> ClubConfig:
        """Create ClubConfig from environment variables."""
        name = os.getenv("LIFETIME_CLUB_NAME", "")
        state = os.getenv("LIFETIME_CLUB_STATE", "")
        if not name or not state:
            raise ValueError(
                "LIFETIME_CLUB_NAME and LIFETIME_CLUB_STATE environment variables are required"
            )
        return cls(name=name, state=state)

    def get_url_segment(self) -> str:
        """Convert club name to URL-friendly format."""
        name = self.name.replace("Life Time", "").replace("LifeTime", "").strip()
        name = name.strip(" -")
        name = name.replace(" at ", "-").replace(" - ", "-")
        name = name.lower().replace(" ", "-")
        name = "".join(c for c in name if c.isalnum() or c == "-")
        return name

    def get_url_param(self) -> str:
        """Get URL parameter format for club name."""
        return self.name.replace(" ", "+")


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
    headless: bool
    login_url: str = "https://my.lifetime.life/login.html"

    @classmethod
    def from_env(cls, reload_env: bool = True) -> BotConfig:
        """Create BotConfig from environment variables.

        Args:
            reload_env: If True, clear and reload environment variables from .env file.
        """
        if reload_env:
            # Clear any cached environment variables
            for key in list(os.environ.keys()):
                del os.environ[key]
            # Load from .env file
            load_dotenv(override=True)

        notification_method = os.getenv("NOTIFICATION_METHOD", "email").lower()
        if notification_method not in ("email", "sms", "both"):
            notification_method = "email"

        return cls(
            username=os.getenv("LIFETIME_USERNAME", ""),
            password=os.getenv("LIFETIME_PASSWORD", ""),
            club=ClubConfig.from_env(),
            target_class=ClassConfig.from_env(),
            email=EmailConfig.from_env(),
            sms=SMSConfig.from_env(),
            notification_method=notification_method,  # type: ignore[arg-type]
            run_on_schedule=os.getenv("RUN_ON_SCHEDULE", "false").lower() == "true",
            headless=os.getenv("HEADLESS", "false").lower() == "true",
        )
