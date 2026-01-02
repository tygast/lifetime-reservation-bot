"""Unit tests for the notifications module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.config import EmailConfig, SMSConfig
from lifetime_bot.notifications import (
    EmailNotificationService,
    NotificationService,
    SMSNotificationService,
)


class TestNotificationService:
    """Tests for the NotificationService abstract base class."""

    def test_is_abstract(self) -> None:
        """Test that NotificationService cannot be instantiated."""
        with pytest.raises(TypeError):
            NotificationService()  # type: ignore


class TestEmailNotificationService:
    """Tests for EmailNotificationService."""

    def test_init(self, email_config: EmailConfig) -> None:
        """Test EmailNotificationService initialization."""
        service = EmailNotificationService(email_config)
        assert service.config == email_config

    def test_is_configured_true(self, email_config: EmailConfig) -> None:
        """Test is_configured returns True for valid config."""
        service = EmailNotificationService(email_config)
        assert service.is_configured() is True

    def test_is_configured_false(self) -> None:
        """Test is_configured returns False for invalid config."""
        config = EmailConfig(sender="", password="", receiver="")
        service = EmailNotificationService(config)
        assert service.is_configured() is False

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_send_success(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test successful email send."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        service = EmailNotificationService(email_config)
        result = service.send("Test Subject", "Test Message")

        assert result is True
        mock_smtp.assert_called_once_with(
            email_config.smtp_server, email_config.smtp_port
        )
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(
            email_config.sender, email_config.password
        )
        mock_server.send_message.assert_called_once()

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_send_failure(
        self, mock_smtp: MagicMock, email_config: EmailConfig
    ) -> None:
        """Test email send failure."""
        mock_smtp.return_value.__enter__.side_effect = Exception("SMTP Error")

        service = EmailNotificationService(email_config)
        result = service.send("Test Subject", "Test Message")

        assert result is False

    def test_send_not_configured(self) -> None:
        """Test send returns False when not configured."""
        config = EmailConfig(sender="", password="", receiver="")
        service = EmailNotificationService(config)
        result = service.send("Test Subject", "Test Message")
        assert result is False


class TestSMSNotificationService:
    """Tests for SMSNotificationService."""

    def test_init(self, sms_config: SMSConfig) -> None:
        """Test SMSNotificationService initialization."""
        service = SMSNotificationService(sms_config)
        assert service.sms_config == sms_config

    def test_is_configured_true(self, sms_config: SMSConfig) -> None:
        """Test is_configured returns True for valid config."""
        service = SMSNotificationService(sms_config)
        assert service.is_configured() is True

    def test_is_configured_false_missing_account_sid(self) -> None:
        """Test is_configured returns False when account_sid is missing."""
        sms_config = SMSConfig(
            account_sid="",
            auth_token="token",
            from_number="+15551234567",
            to_number="+15559876543",
        )
        service = SMSNotificationService(sms_config)
        assert service.is_configured() is False

    def test_is_configured_false_missing_to_number(self) -> None:
        """Test is_configured returns False when to_number is missing."""
        sms_config = SMSConfig(
            account_sid="ACtest123",
            auth_token="token",
            from_number="+15551234567",
            to_number="",
        )
        service = SMSNotificationService(sms_config)
        assert service.is_configured() is False

    @patch("lifetime_bot.notifications.sms.Client")
    def test_send_success(
        self,
        mock_client_class: MagicMock,
        sms_config: SMSConfig,
    ) -> None:
        """Test successful SMS send via Twilio."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        service = SMSNotificationService(sms_config)
        result = service.send("Test Subject", "Test Message")

        assert result is True
        mock_client_class.assert_called_once_with(
            sms_config.account_sid, sms_config.auth_token
        )
        mock_client.messages.create.assert_called_once_with(
            body="Test Subject: Test Message",
            from_=sms_config.from_number,
            to=sms_config.to_number,
        )

    @patch("lifetime_bot.notifications.sms.Client")
    def test_send_failure(
        self,
        mock_client_class: MagicMock,
        sms_config: SMSConfig,
    ) -> None:
        """Test SMS send failure."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("Twilio Error")

        service = SMSNotificationService(sms_config)
        result = service.send("Test Subject", "Test Message")

        assert result is False

    def test_send_not_configured(self) -> None:
        """Test send returns False when not configured."""
        sms_config = SMSConfig(
            account_sid="",
            auth_token="",
            from_number="",
            to_number="",
        )
        service = SMSNotificationService(sms_config)
        result = service.send("Test Subject", "Test Message")
        assert result is False

    @patch("lifetime_bot.notifications.sms.Client")
    def test_send_message_format(
        self,
        mock_client_class: MagicMock,
        sms_config: SMSConfig,
    ) -> None:
        """Test SMS message is formatted correctly."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        service = SMSNotificationService(sms_config)
        service.send("Subject", "Message body")

        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["body"] == "Subject: Message body"
        assert call_args.kwargs["from_"] == sms_config.from_number
        assert call_args.kwargs["to"] == sms_config.to_number
