"""Integration tests for notification services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.config import EmailConfig, SMSConfig
from lifetime_bot.notifications import (
    EmailNotificationService,
    SMSNotificationService,
)


class TestEmailNotificationIntegration:
    """Integration tests for EmailNotificationService."""

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_email_service_full_flow(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test complete email notification flow."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        service = EmailNotificationService(email_config)

        # Verify service is configured
        assert service.is_configured() is True

        # Send notification
        result = service.send(
            subject="Test Notification",
            message="This is a test message with multiple lines.\n\nLine 2.",
        )

        # Verify success
        assert result is True

        # Verify SMTP interactions
        mock_smtp.assert_called_once_with(
            email_config.smtp_server, email_config.smtp_port
        )
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(
            email_config.sender, email_config.password
        )
        mock_server.send_message.assert_called_once()

        # Verify email content
        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Subject"] == "Test Notification"
        assert sent_message["From"] == email_config.sender
        assert sent_message["To"] == email_config.receiver


class TestSMSNotificationIntegration:
    """Integration tests for SMSNotificationService."""

    @patch("lifetime_bot.notifications.sms.Client")
    def test_sms_service_full_flow(
        self, mock_client_class: MagicMock, sms_config: SMSConfig
    ) -> None:
        """Test complete SMS notification flow via Twilio."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        service = SMSNotificationService(sms_config)

        # Verify service is configured
        assert service.is_configured() is True

        # Send notification
        result = service.send(
            subject="Test SMS",
            message="Short SMS message",
        )

        # Verify success
        assert result is True

        # Verify Twilio client was created with correct credentials
        mock_client_class.assert_called_once_with(
            sms_config.account_sid, sms_config.auth_token
        )

        # Verify message was sent correctly
        mock_client.messages.create.assert_called_once_with(
            body="Test SMS: Short SMS message",
            from_=sms_config.from_number,
            to=sms_config.to_number,
        )

    @patch("lifetime_bot.notifications.sms.Client")
    def test_sms_service_with_different_configs(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test SMS notifications with various configurations."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        test_configs = [
            {
                "account_sid": "AC111111111111111111111111111111",
                "auth_token": "token1",
                "from_number": "+15551111111",
                "to_number": "+15552222222",
            },
            {
                "account_sid": "AC222222222222222222222222222222",
                "auth_token": "token2",
                "from_number": "+15553333333",
                "to_number": "+15554444444",
            },
        ]

        for config_data in test_configs:
            mock_client_class.reset_mock()
            mock_client.reset_mock()

            sms_config = SMSConfig(**config_data)
            service = SMSNotificationService(sms_config)

            result = service.send("Test", "Message")

            assert result is True
            mock_client_class.assert_called_once_with(
                config_data["account_sid"], config_data["auth_token"]
            )
            mock_client.messages.create.assert_called_once_with(
                body="Test: Message",
                from_=config_data["from_number"],
                to=config_data["to_number"],
            )


class TestNotificationServiceInteraction:
    """Integration tests for notification service interaction patterns."""

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_email_service_can_send_independently(
        self,
        mock_smtp: MagicMock,
        email_config: EmailConfig,
    ) -> None:
        """Test that email service can send independently."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        email_service = EmailNotificationService(email_config)
        result = email_service.send("Test Subject", "Test Message")

        assert result is True
        mock_server.send_message.assert_called_once()

    @patch("lifetime_bot.notifications.sms.Client")
    def test_sms_service_can_send_independently(
        self,
        mock_client_class: MagicMock,
        sms_config: SMSConfig,
    ) -> None:
        """Test that SMS service can send independently."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        sms_service = SMSNotificationService(sms_config)
        result = sms_service.send("Test Subject", "Test Message")

        assert result is True
        mock_client.messages.create.assert_called_once()

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_service_handles_connection_failure(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test that service handles connection failures gracefully."""
        mock_smtp.return_value.__enter__.side_effect = ConnectionRefusedError(
            "Connection refused"
        )

        service = EmailNotificationService(email_config)
        result = service.send("Test", "Message")

        assert result is False

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_service_handles_auth_failure(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test that service handles authentication failures gracefully."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        mock_server.login.side_effect = Exception("Authentication failed")

        service = EmailNotificationService(email_config)
        result = service.send("Test", "Message")

        assert result is False

    @patch("lifetime_bot.notifications.sms.Client")
    def test_sms_service_handles_twilio_error(
        self,
        mock_client_class: MagicMock,
        sms_config: SMSConfig,
    ) -> None:
        """Test that SMS service handles Twilio errors gracefully."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("Twilio API error")

        sms_service = SMSNotificationService(sms_config)
        result = sms_service.send("Test Subject", "Test Message")

        assert result is False
