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

    def test_init(
        self, sms_config: SMSConfig, email_config: EmailConfig
    ) -> None:
        """Test SMSNotificationService initialization."""
        service = SMSNotificationService(sms_config, email_config)
        assert service.sms_config == sms_config
        assert service.email_config == email_config

    def test_is_configured_true(
        self, sms_config: SMSConfig, email_config: EmailConfig
    ) -> None:
        """Test is_configured returns True for valid config."""
        service = SMSNotificationService(sms_config, email_config)
        assert service.is_configured() is True

    def test_is_configured_false_invalid_sms(
        self, email_config: EmailConfig
    ) -> None:
        """Test is_configured returns False for invalid SMS config."""
        sms_config = SMSConfig(number="", carrier="")
        service = SMSNotificationService(sms_config, email_config)
        assert service.is_configured() is False

    def test_is_configured_false_invalid_email(
        self, sms_config: SMSConfig
    ) -> None:
        """Test is_configured returns False for invalid email config."""
        email_config = EmailConfig(sender="", password="", receiver="")
        service = SMSNotificationService(sms_config, email_config)
        assert service.is_configured() is False

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_send_success(
        self,
        mock_smtp: MagicMock,
        sms_config: SMSConfig,
        email_config: EmailConfig,
    ) -> None:
        """Test successful SMS send."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        service = SMSNotificationService(sms_config, email_config)
        result = service.send("Test Subject", "Test Message")

        assert result is True
        mock_smtp.assert_called_once_with(
            email_config.smtp_server, email_config.smtp_port
        )
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_send_failure(
        self,
        mock_smtp: MagicMock,
        sms_config: SMSConfig,
        email_config: EmailConfig,
    ) -> None:
        """Test SMS send failure."""
        mock_smtp.return_value.__enter__.side_effect = Exception("SMTP Error")

        service = SMSNotificationService(sms_config, email_config)
        result = service.send("Test Subject", "Test Message")

        assert result is False

    def test_send_not_configured(self, email_config: EmailConfig) -> None:
        """Test send returns False when not configured."""
        sms_config = SMSConfig(number="", carrier="")
        service = SMSNotificationService(sms_config, email_config)
        result = service.send("Test Subject", "Test Message")
        assert result is False

    @patch("lifetime_bot.notifications.sms.smtplib.SMTP")
    def test_send_uses_correct_gateway(
        self,
        mock_smtp: MagicMock,
        email_config: EmailConfig,
    ) -> None:
        """Test SMS is sent to correct carrier gateway."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        sms_config = SMSConfig(number="5551234567", carrier="verizon")
        service = SMSNotificationService(sms_config, email_config)
        service.send("Test", "Message")

        # Verify the message was sent to the correct gateway
        call_args = mock_server.send_message.call_args
        msg = call_args[0][0]
        assert msg["To"] == "5551234567@vtext.com"
