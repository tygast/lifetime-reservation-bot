"""Integration tests for configuration loading."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from lifetime_bot.config import BotConfig


class TestBotConfigIntegration:
    """Integration tests for complete BotConfig loading."""

    def test_full_config_from_env(self, env_vars: dict[str, str]) -> None:
        """Test loading complete configuration from environment variables."""
        with patch.dict(os.environ, env_vars, clear=True):
            config = BotConfig.from_env(reload_env=False)

            # Verify bot credentials
            assert config.username == "test@example.com"
            assert config.password == "testpassword"

            # Verify club config
            assert config.club.name == "San Antonio 281"
            assert config.club.state == "TX"
            assert config.club.get_url_segment() == "san-antonio-281"
            assert config.club.get_url_param() == "San+Antonio+281"

            # Verify class config
            assert config.target_class.name == "Pickleball"
            assert config.target_class.instructor == "John D"
            assert config.target_class.date == "2026-01-15"
            assert config.target_class.start_time == "9:00 AM"
            assert config.target_class.end_time == "10:00 AM"

            # Verify email config
            assert config.email.sender == "test@gmail.com"
            assert config.email.password == "testpassword123"
            assert config.email.receiver == "receiver@gmail.com"
            assert config.email.smtp_server == "smtp.gmail.com"
            assert config.email.smtp_port == 587
            assert config.email.is_valid() is True

            # Verify SMS config
            assert config.sms.number == "1234567890"
            assert config.sms.carrier == "att"
            assert config.sms.is_valid() is True
            assert config.sms.get_gateway_email() == "1234567890@mms.att.net"

            # Verify bot settings
            assert config.notification_method == "email"
            assert config.run_on_schedule is False
            assert config.headless is True

    def test_config_with_schedule_mode(self) -> None:
        """Test configuration with schedule mode enabled."""
        env = {
            "LIFETIME_USERNAME": "user@example.com",
            "LIFETIME_PASSWORD": "password",
            "LIFETIME_CLUB_NAME": "Test Club",
            "LIFETIME_CLUB_STATE": "CA",
            "RUN_ON_SCHEDULE": "true",
            "HEADLESS": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)

            assert config.run_on_schedule is True

    def test_config_with_sms_notification(self) -> None:
        """Test configuration with SMS notification method."""
        env = {
            "LIFETIME_USERNAME": "user@example.com",
            "LIFETIME_PASSWORD": "password",
            "LIFETIME_CLUB_NAME": "Test Club",
            "LIFETIME_CLUB_STATE": "CA",
            "NOTIFICATION_METHOD": "sms",
            "SMS_NUMBER": "5551234567",
            "SMS_CARRIER": "verizon",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)

            assert config.notification_method == "sms"
            assert config.sms.number == "5551234567"
            assert config.sms.carrier == "verizon"
            assert config.sms.get_gateway_email() == "5551234567@vtext.com"

    def test_config_with_both_notifications(self) -> None:
        """Test configuration with both notification methods."""
        env = {
            "LIFETIME_USERNAME": "user@example.com",
            "LIFETIME_PASSWORD": "password",
            "LIFETIME_CLUB_NAME": "Test Club",
            "LIFETIME_CLUB_STATE": "CA",
            "NOTIFICATION_METHOD": "both",
            "EMAIL_SENDER": "sender@gmail.com",
            "EMAIL_PASSWORD": "emailpass",
            "EMAIL_RECEIVER": "receiver@gmail.com",
            "SMS_NUMBER": "5551234567",
            "SMS_CARRIER": "tmobile",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(reload_env=False)

            assert config.notification_method == "both"
            assert config.email.is_valid() is True
            assert config.sms.is_valid() is True


class TestClubConfigIntegration:
    """Integration tests for club URL generation."""

    def test_various_club_names(self) -> None:
        """Test URL generation for various club name formats."""
        test_cases = [
            ("San Antonio 281", "TX", "san-antonio-281", "San+Antonio+281"),
            ("Life Time - Flower Mound", "TX", "flower-mound", "Life+Time+-+Flower+Mound"),
            ("Club at Location", "CA", "club-location", "Club+at+Location"),
            ("North Dallas", "TX", "north-dallas", "North+Dallas"),
        ]

        for name, state, expected_segment, expected_param in test_cases:
            env = {
                "LIFETIME_USERNAME": "user@example.com",
                "LIFETIME_PASSWORD": "password",
                "LIFETIME_CLUB_NAME": name,
                "LIFETIME_CLUB_STATE": state,
            }
            with patch.dict(os.environ, env, clear=True):
                config = BotConfig.from_env(reload_env=False)

                assert config.club.get_url_segment() == expected_segment, f"Failed for {name}"
                assert config.club.get_url_param() == expected_param, f"Failed for {name}"
