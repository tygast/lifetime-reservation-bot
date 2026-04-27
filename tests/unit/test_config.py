"""Unit tests for the config module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from lifetime_bot.config import (
    BotConfig,
    ClassConfig,
    ClubConfig,
    EmailConfig,
    NotificationConfig,
    SMSConfig,
)


class TestEmailConfig:
    """Tests for EmailConfig."""

    def test_init(self, email_config: EmailConfig) -> None:
        """Test EmailConfig initialization."""
        assert email_config.sender == "test@gmail.com"
        assert email_config.password == "testpassword123"
        assert email_config.receiver == "receiver@gmail.com"
        assert email_config.smtp_server == "smtp.gmail.com"
        assert email_config.smtp_port == 587

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        """Test creating EmailConfig from environment variables."""
        assert mock_env
        config = EmailConfig.from_env()
        assert config.sender == "test@gmail.com"
        assert config.password == "testpassword123"
        assert config.receiver == "receiver@gmail.com"
        assert config.smtp_server == "smtp.gmail.com"
        assert config.smtp_port == 587

    def test_from_env_defaults(self) -> None:
        """Test EmailConfig defaults when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = EmailConfig.from_env()
            assert config.sender == ""
            assert config.password == ""
            assert config.receiver == ""
            assert config.smtp_server == "smtp.gmail.com"
            assert config.smtp_port == 587

    def test_is_valid_true(self, email_config: EmailConfig) -> None:
        """Test is_valid returns True when all required fields are set."""
        assert email_config.is_valid() is True

    def test_is_valid_false_missing_sender(self) -> None:
        """Test is_valid returns False when sender is missing."""
        config = EmailConfig(
            sender="",
            password="password",
            receiver="receiver@gmail.com",
        )
        assert config.is_valid() is False

    def test_is_valid_false_missing_password(self) -> None:
        """Test is_valid returns False when password is missing."""
        config = EmailConfig(
            sender="sender@gmail.com",
            password="",
            receiver="receiver@gmail.com",
        )
        assert config.is_valid() is False

    def test_is_valid_false_missing_receiver(self) -> None:
        """Test is_valid returns False when receiver is missing."""
        config = EmailConfig(
            sender="sender@gmail.com",
            password="password",
            receiver="",
        )
        assert config.is_valid() is False


class TestSMSConfig:
    """Tests for SMSConfig."""

    def test_init(self, sms_config: SMSConfig) -> None:
        """Test SMSConfig initialization."""
        assert sms_config.account_sid == "ACtest123456789"
        assert sms_config.auth_token == "test_auth_token"
        assert sms_config.from_number == "+15551234567"
        assert sms_config.to_number == "+15559876543"

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        """Test creating SMSConfig from environment variables."""
        assert mock_env
        config = SMSConfig.from_env()
        assert config.account_sid == "ACtest123456789"
        assert config.auth_token == "test_auth_token"
        assert config.from_number == "+15551234567"
        assert config.to_number == "+15559876543"

    def test_from_env_defaults(self) -> None:
        """Test SMSConfig defaults when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = SMSConfig.from_env()
            assert config.account_sid == ""
            assert config.auth_token == ""
            assert config.from_number == ""
            assert config.to_number == ""

    def test_is_valid_true(self, sms_config: SMSConfig) -> None:
        """Test is_valid returns True for valid config."""
        assert sms_config.is_valid() is True

    def test_is_valid_false_missing_account_sid(self) -> None:
        """Test is_valid returns False when account_sid is missing."""
        config = SMSConfig(
            account_sid="",
            auth_token="token",
            from_number="+15551234567",
            to_number="+15559876543",
        )
        assert config.is_valid() is False

    def test_is_valid_false_missing_auth_token(self) -> None:
        """Test is_valid returns False when auth_token is missing."""
        config = SMSConfig(
            account_sid="ACtest123",
            auth_token="",
            from_number="+15551234567",
            to_number="+15559876543",
        )
        assert config.is_valid() is False

    def test_is_valid_false_missing_from_number(self) -> None:
        """Test is_valid returns False when from_number is missing."""
        config = SMSConfig(
            account_sid="ACtest123",
            auth_token="token",
            from_number="",
            to_number="+15559876543",
        )
        assert config.is_valid() is False

    def test_is_valid_false_missing_to_number(self) -> None:
        """Test is_valid returns False when to_number is missing."""
        config = SMSConfig(
            account_sid="ACtest123",
            auth_token="token",
            from_number="+15551234567",
            to_number="",
        )
        assert config.is_valid() is False


class TestClassConfig:
    """Tests for ClassConfig."""

    def test_init(self, class_config: ClassConfig) -> None:
        """Test ClassConfig initialization."""
        assert class_config.name == "Pickleball"
        assert class_config.instructor == "John D"
        assert class_config.date == "2026-01-15"
        assert class_config.start_time == "9:00 AM"
        assert class_config.end_time == "10:00 AM"

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        """Test creating ClassConfig from environment variables."""
        assert mock_env
        config = ClassConfig.from_env()
        assert config.name == "Pickleball"
        assert config.instructor == "John D"
        assert config.date == "2026-01-15"
        assert config.start_time == "9:00 AM"
        assert config.end_time == "10:00 AM"

    def test_from_env_defaults(self) -> None:
        """Test ClassConfig defaults when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = ClassConfig.from_env()
            assert config.name == ""
            assert config.instructor == ""
            assert config.date == ""
            assert config.start_time == ""
            assert config.end_time == "10:00 AM"

    def test_from_env_normalizes_no_instructor_values(self) -> None:
        env = {
            "TARGET_CLASS": "Pickleball",
            "TARGET_INSTRUCTOR": "none",
        }
        with patch.dict(os.environ, env, clear=True):
            config = ClassConfig.from_env()
            assert config.instructor == ""


class TestClubConfig:
    """Tests for ClubConfig."""

    def test_init(self, club_config: ClubConfig) -> None:
        """Test ClubConfig initialization."""
        assert club_config.name == "San Antonio 281"

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        """Test creating ClubConfig from environment variables."""
        assert mock_env
        config = ClubConfig.from_env()
        assert config.name == "San Antonio 281"

    def test_from_env_raises_without_name(self) -> None:
        """Test from_env raises ValueError when name is missing."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(
            ValueError, match="LIFETIME_CLUB_NAME"
        ):
            ClubConfig.from_env()


class TestBotConfig:
    """Tests for BotConfig."""

    def test_init(self, bot_config: BotConfig) -> None:
        """Test BotConfig initialization."""
        assert bot_config.username == "test@example.com"
        assert bot_config.password == "testpassword"
        assert bot_config.notification_method == "email"
        assert bot_config.run_on_schedule is False

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        """Test creating BotConfig from environment variables."""
        assert mock_env
        config = BotConfig.from_env(reload_env=False)
        assert config.username == "test@example.com"
        assert config.password == "testpassword"
        assert config.club.name == "San Antonio 281"
        assert config.target_class.name == "Pickleball"
        assert config.notification_method == "email"
        assert config.run_on_schedule is False

    def test_from_env_notification_method_sms(self) -> None:
        """Test notification_method defaults to email for invalid values."""
        env = {
            "LIFETIME_USERNAME": "test@example.com",
            "LIFETIME_PASSWORD": "testpassword",
            "LIFETIME_CLUB_NAME": "Test Club",
            "NOTIFICATION_METHOD": "invalid",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)
            assert config.notification_method == "email"

    def test_from_env_notification_method_both(self) -> None:
        """Test notification_method can be 'both'."""
        env = {
            "LIFETIME_USERNAME": "test@example.com",
            "LIFETIME_PASSWORD": "testpassword",
            "LIFETIME_CLUB_NAME": "Test Club",
            "NOTIFICATION_METHOD": "both",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)
            assert config.notification_method == "both"

    def test_from_env_run_on_schedule_true(self) -> None:
        """Test run_on_schedule parses 'true' correctly."""
        env = {
            "LIFETIME_USERNAME": "test@example.com",
            "LIFETIME_PASSWORD": "testpassword",
            "LIFETIME_CLUB_NAME": "Test Club",
            "RUN_ON_SCHEDULE": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)
            assert config.run_on_schedule is True

    def test_exposes_notification_subset(self, bot_config: BotConfig) -> None:
        notification_config = bot_config.notifications

        assert notification_config.email is bot_config.email
        assert notification_config.sms is bot_config.sms
        assert notification_config.method == bot_config.notification_method


class TestNotificationConfig:
    def test_from_env(self, mock_env: dict[str, str]) -> None:
        assert mock_env
        config = NotificationConfig.from_env(reload_env=False)

        assert config.email.sender == "test@gmail.com"
        assert config.sms.account_sid == "ACtest123456789"
        assert config.method == "email"

    def test_invalid_notification_method_defaults_to_email(self) -> None:
        env = {"NOTIFICATION_METHOD": "invalid"}
        with patch.dict(os.environ, env, clear=True):
            config = NotificationConfig.from_env(reload_env=False)
            assert config.method == "email"
