"""Email notification service."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from lifetime_bot.config import EmailConfig
from lifetime_bot.notifications.base import NotificationService

DEFAULT_SMTP_TIMEOUT_SECONDS = 300.0


class EmailNotificationService(NotificationService):
    """Email notification service using SMTP."""

    def __init__(self, config: EmailConfig) -> None:
        """Initialize the email notification service.

        Args:
            config: Email configuration containing SMTP settings.
        """
        self.config = config

    def is_configured(self) -> bool:
        """Check if email configuration is valid."""
        return self.config.is_valid()

    def send(self, subject: str, message: str) -> bool:
        """Send an email notification.

        Args:
            subject: Email subject line.
            message: Email body content.

        Returns:
            True if email was sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("Email configuration is incomplete")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.config.sender
            msg["To"] = self.config.receiver
            msg["Subject"] = subject
            msg.attach(MIMEText(message, "plain"))

            with smtplib.SMTP(
                self.config.smtp_server,
                self.config.smtp_port,
                timeout=_get_smtp_timeout_seconds(),
            ) as server:
                server.starttls()
                server.login(self.config.sender, self.config.password)
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False


def _get_smtp_timeout_seconds() -> float:
    raw_value = os.getenv("SMTP_TIMEOUT_SECONDS")
    if not raw_value:
        return DEFAULT_SMTP_TIMEOUT_SECONDS
    try:
        return float(raw_value)
    except ValueError:
        print(
            "Invalid SMTP_TIMEOUT_SECONDS value "
            f"{raw_value!r}; using default {DEFAULT_SMTP_TIMEOUT_SECONDS:.1f}s."
        )
        return DEFAULT_SMTP_TIMEOUT_SECONDS
