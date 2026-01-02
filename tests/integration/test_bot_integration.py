"""Integration tests for the bot module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig


class TestBotInitialization:
    """Integration tests for bot initialization."""

    @patch("lifetime_bot.bot.create_driver")
    @patch("lifetime_bot.config.load_dotenv")
    def test_bot_initializes_from_env(
        self, mock_load_dotenv: MagicMock, mock_create_driver: MagicMock, env_vars: dict[str, str]
    ) -> None:
        """Test that bot initializes correctly from environment variables."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        with patch.dict(os.environ, env_vars, clear=True):
            bot = LifetimeReservationBot(config=BotConfig.from_env(reload_env=False))

            # Verify config was loaded correctly
            assert bot.config.username == "test@example.com"
            assert bot.config.password == "testpassword"
            assert bot.config.club.name == "San Antonio 281"
            assert bot.config.target_class.name == "Pickleball"

            # Verify webdriver was created
            assert bot.driver == mock_driver
            assert bot.wait == mock_wait

            # Verify notification services were created
            assert bot.email_service is not None
            assert bot.sms_service is not None

    @patch("lifetime_bot.bot.create_driver")
    def test_bot_with_explicit_config(
        self, mock_create_driver: MagicMock, bot_config: BotConfig
    ) -> None:
        """Test bot initialization with explicit configuration."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        bot = LifetimeReservationBot(config=bot_config)

        assert bot.config == bot_config
        mock_create_driver.assert_called_once_with(headless=bot_config.headless)


class TestBotNotificationIntegration:
    """Integration tests for bot notification functionality."""

    @patch("lifetime_bot.notifications.email.smtplib.SMTP")
    @patch("lifetime_bot.bot.create_driver")
    def test_bot_sends_email_notification(
        self,
        mock_create_driver: MagicMock,
        mock_smtp: MagicMock,
        bot_config: BotConfig,
    ) -> None:
        """Test bot sends email notifications correctly."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        bot_config.notification_method = "email"
        bot = LifetimeReservationBot(config=bot_config)

        bot.send_notification("Test Subject", "Test Message")

        # Verify email was sent
        mock_server.send_message.assert_called_once()
        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Subject"] == "Test Subject"

    @patch("lifetime_bot.notifications.sms.Client")
    @patch("lifetime_bot.bot.create_driver")
    def test_bot_sends_sms_notification(
        self,
        mock_create_driver: MagicMock,
        mock_client_class: MagicMock,
        bot_config: BotConfig,
    ) -> None:
        """Test bot sends SMS notifications correctly via Twilio."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        bot_config.notification_method = "sms"
        bot = LifetimeReservationBot(config=bot_config)

        bot.send_notification("Test Subject", "Test Message")

        # Verify SMS was sent via Twilio
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["body"] == "Test Subject: Test Message"
        assert call_kwargs["from_"] == bot_config.sms.from_number
        assert call_kwargs["to"] == bot_config.sms.to_number

    @patch("lifetime_bot.bot.create_driver")
    def test_bot_sends_both_notifications(
        self,
        mock_create_driver: MagicMock,
        bot_config: BotConfig,
    ) -> None:
        """Test bot sends both email and SMS notifications."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        bot_config.notification_method = "both"
        bot = LifetimeReservationBot(config=bot_config)

        # Mock the service send methods directly
        bot.email_service.send = MagicMock(return_value=True)
        bot.sms_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        # Verify both services were called
        bot.email_service.send.assert_called_once_with("Test Subject", "Test Message")
        bot.sms_service.send.assert_called_once_with("Test Subject", "Test Message")


class TestBotClassDetails:
    """Integration tests for class details generation."""

    @patch("lifetime_bot.bot.create_driver")
    def test_class_details_formatting(
        self, mock_create_driver: MagicMock, bot_config: BotConfig
    ) -> None:
        """Test that class details are formatted correctly."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        bot = LifetimeReservationBot(config=bot_config)
        details = bot._get_class_details("2026-01-20")

        # Verify all class information is included
        assert "Class: Pickleball" in details
        assert "Instructor: John D" in details
        assert "Date: 2026-01-20" in details
        assert "Time: 9:00 AM - 10:00 AM" in details


class TestBotUrlGeneration:
    """Integration tests for URL generation."""

    @patch("lifetime_bot.bot.create_driver")
    def test_schedule_url_generation(
        self, mock_create_driver: MagicMock, bot_config: BotConfig
    ) -> None:
        """Test that schedule URL is generated correctly."""
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock_create_driver.return_value = (mock_driver, mock_wait)

        bot = LifetimeReservationBot(config=bot_config)

        # Navigate to schedule (will fail on wait but URL should be correct)
        mock_wait.until.side_effect = Exception("Timeout")
        bot.navigate_to_schedule("2026-01-20")

        # Verify URL was constructed correctly
        called_url = mock_driver.get.call_args[0][0]
        assert "san-antonio-281" in called_url
        assert "selectedDate=2026-01-20" in called_url
        assert "location=San+Antonio+281" in called_url
        assert "tx" in called_url.lower()
