"""Integration tests for the bot module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig


class TestBotInitialization:
    """Integration tests for bot initialization."""

    @patch("lifetime_bot.config.load_dotenv")
    def test_bot_initializes_from_env(
        self, _mock_load_dotenv: MagicMock, env_vars: dict[str, str]
    ) -> None:
        """Bot loads its config from the environment without side effects."""
        with patch.dict(os.environ, env_vars, clear=True):
            bot = LifetimeReservationBot(config=BotConfig.from_env(reload_env=False))

            assert bot.config.username == "test@example.com"
            assert bot.config.password == "testpassword"
            assert bot.config.club.name == "San Antonio 281"
            assert bot.config.target_class.name == "Pickleball"

            assert bot.email_service is not None
            assert bot.sms_service is not None

    def test_bot_with_explicit_config(self, bot_config: BotConfig) -> None:
        """Bot stores the explicit config without side effects."""
        bot = LifetimeReservationBot(config=bot_config)
        assert bot.config is bot_config


class TestBotNotificationIntegration:
    """Integration tests for bot notification functionality."""

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    def test_bot_sends_email_notification(
        self, mock_smtp: MagicMock, bot_config: BotConfig
    ) -> None:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        bot_config.notification_method = "email"
        bot = LifetimeReservationBot(config=bot_config)

        bot.send_notification("Test Subject", "Test Message")

        mock_server.send_message.assert_called_once()
        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Subject"] == "Test Subject"

    @patch("lifetime_bot.notifications.sms.Client")
    def test_bot_sends_sms_notification(
        self, mock_client_class: MagicMock, bot_config: BotConfig
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        bot_config.notification_method = "sms"
        bot = LifetimeReservationBot(config=bot_config)

        bot.send_notification("Test Subject", "Test Message")

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["body"] == "Test Subject: Test Message"
        assert kwargs["from_"] == bot_config.sms.from_number
        assert kwargs["to"] == bot_config.sms.to_number

    def test_bot_sends_both_notifications(self, bot_config: BotConfig) -> None:
        bot_config.notification_method = "both"
        bot = LifetimeReservationBot(config=bot_config)
        bot.email_service.send = MagicMock(return_value=True)
        bot.sms_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        bot.email_service.send.assert_called_once_with("Test Subject", "Test Message")
        bot.sms_service.send.assert_called_once_with("Test Subject", "Test Message")


class TestBotClassDetails:
    """Integration tests for class details generation."""

    def test_class_details_formatting(self, bot_config: BotConfig) -> None:
        bot = LifetimeReservationBot(config=bot_config)
        details = bot._get_class_details("2026-01-20")

        assert "Class: Pickleball" in details
        assert "Instructor: John D" in details
        assert "Date: 2026-01-20" in details
        assert "Time: 9:00 AM - 10:00 AM" in details
        assert "Club: San Antonio 281" in details
