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

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_sms_service_full_flow(
        self, mock_smtp: MagicMock, sms_config: SMSConfig, email_config: EmailConfig
    ) -> None:
        """Test complete SMS notification flow."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        service = SMSNotificationService(sms_config, email_config)

        # Verify service is configured
        assert service.is_configured() is True

        # Send notification
        result = service.send(
            subject="Test SMS",
            message="Short SMS message",
        )

        # Verify success
        assert result is True

        # Verify email was sent to correct SMS gateway
        sent_message = mock_server.send_message.call_args[0][0]
        expected_gateway = sms_config.get_gateway_email()
        assert sent_message["To"] == expected_gateway

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_sms_service_all_carriers(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test SMS notifications for all supported carriers."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        # Use actual carriers from SMS_GATEWAYS
        carriers_and_gateways = {
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

        for carrier, gateway in carriers_and_gateways.items():
            mock_smtp.reset_mock()
            mock_server.reset_mock()

            sms_config = SMSConfig(number="5551234567", carrier=carrier)
            service = SMSNotificationService(sms_config, email_config)

            result = service.send("Test", "Message")

            assert result is True, f"Failed for carrier: {carrier}"
            sent_message = mock_server.send_message.call_args[0][0]
            assert sent_message["To"] == f"5551234567@{gateway}", f"Wrong gateway for {carrier}"


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

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_sms_service_can_send_independently(
        self,
        mock_smtp: MagicMock,
        email_config: EmailConfig,
        sms_config: SMSConfig,
    ) -> None:
        """Test that SMS service can send independently."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        sms_service = SMSNotificationService(sms_config, email_config)
        result = sms_service.send("Test Subject", "Test Message")

        assert result is True
        mock_server.send_message.assert_called_once()

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
