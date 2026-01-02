"""SMS notification service using Twilio."""

from __future__ import annotations

from twilio.rest import Client

from lifetime_bot.config import SMSConfig
from lifetime_bot.notifications.base import NotificationService


class SMSNotificationService(NotificationService):
    """SMS notification service using Twilio."""

    def __init__(self, sms_config: SMSConfig) -> None:
        """Initialize the SMS notification service.

        Args:
            sms_config: SMS configuration containing Twilio credentials.
        """
        self.sms_config = sms_config

    def is_configured(self) -> bool:
        """Check if SMS configuration is valid."""
        return self.sms_config.is_valid()

    def send(self, subject: str, message: str) -> bool:
        """Send an SMS notification via Twilio.

        Args:
            subject: Message subject (prefixed to the message).
            message: Message body content.

        Returns:
            True if SMS was sent successfully, False otherwise.
        """
        if not self.is_configured():
            error_msg = "SMS configuration incomplete. Check Twilio credentials."
            print(f"{error_msg}")
            return False

        try:
            sms_message = f"{subject}: {message}"

            client = Client(self.sms_config.account_sid, self.sms_config.auth_token)
            client.messages.create(
                body=sms_message,
                from_=self.sms_config.from_number,
                to=self.sms_config.to_number,
            )

            return True
        except Exception as e:
            print(f"Failed to send SMS: {e}")
            return False
