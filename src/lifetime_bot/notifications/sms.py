"""SMS notification service using email-to-SMS gateways."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from lifetime_bot.config import EmailConfig, SMSConfig
from lifetime_bot.notifications.base import NotificationService


class SMSNotificationService(NotificationService):
    """SMS notification service using email-to-SMS gateways."""

    def __init__(self, sms_config: SMSConfig, email_config: EmailConfig) -> None:
        """Initialize the SMS notification service.

        Args:
            sms_config: SMS configuration containing carrier and number.
            email_config: Email configuration for SMTP settings.
        """
        self.sms_config = sms_config
        self.email_config = email_config

    def is_configured(self) -> bool:
        """Check if SMS configuration is valid."""
        return self.sms_config.is_valid() and self.email_config.is_valid()

    def send(self, subject: str, message: str) -> bool:
        """Send an SMS notification via email-to-SMS gateway.

        Args:
            subject: Message subject (prefixed to the message).
            message: Message body content.

        Returns:
            True if SMS was sent successfully, False otherwise.
        """
        if not self.is_configured():
            error_msg = "SMS configuration incomplete. Check SMS_NUMBER and SMS_CARRIER."
            print(f"{error_msg}")
            return False

        try:
            sms_message = f"{subject}: {message}"
            sms_email = self.sms_config.get_gateway_email()

            msg = MIMEMultipart()
            msg["From"] = self.email_config.sender
            msg["To"] = sms_email
            msg["Subject"] = "LT Bot"
            msg.attach(MIMEText(sms_message, "plain"))

            with smtplib.SMTP(self.email_config.smtp_server, self.email_config.smtp_port) as server:
                server.starttls()
                server.login(self.email_config.sender, self.email_config.password)
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"Failed to send SMS: {e}")
            return False
