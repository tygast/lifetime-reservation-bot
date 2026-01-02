"""Shared test fixtures and configuration."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.config import (
    BotConfig,
    ClassConfig,
    ClubConfig,
    EmailConfig,
    SMSConfig,
)


@pytest.fixture
def email_config() -> EmailConfig:
    """Create a test email configuration."""
    return EmailConfig(
        sender="test@gmail.com",
        password="testpassword123",
        receiver="receiver@gmail.com",
        smtp_server="smtp.gmail.com",
        smtp_port=587,
    )


@pytest.fixture
def sms_config() -> SMSConfig:
    """Create a test SMS configuration."""
    return SMSConfig(
        account_sid="ACtest123456789",
        auth_token="test_auth_token",
        from_number="+15551234567",
        to_number="+15559876543",
    )


@pytest.fixture
def class_config() -> ClassConfig:
    """Create a test class configuration."""
    return ClassConfig(
        name="Pickleball",
        instructor="John D",
        date="2026-01-15",
        start_time="9:00 AM",
        end_time="10:00 AM",
    )


@pytest.fixture
def club_config() -> ClubConfig:
    """Create a test club configuration."""
    return ClubConfig(
        name="San Antonio 281",
        state="TX",
    )


@pytest.fixture
def bot_config(
    email_config: EmailConfig,
    sms_config: SMSConfig,
    class_config: ClassConfig,
    club_config: ClubConfig,
) -> BotConfig:
    """Create a test bot configuration."""
    return BotConfig(
        username="test@example.com",
        password="testpassword",
        club=club_config,
        target_class=class_config,
        email=email_config,
        sms=sms_config,
        notification_method="email",
        run_on_schedule=False,
        headless=True,
    )


@pytest.fixture
def env_vars() -> dict[str, str]:
    """Return a dictionary of test environment variables."""
    return {
        "LIFETIME_USERNAME": "test@example.com",
        "LIFETIME_PASSWORD": "testpassword",
        "LIFETIME_CLUB_NAME": "San Antonio 281",
        "LIFETIME_CLUB_STATE": "TX",
        "TARGET_CLASS": "Pickleball",
        "TARGET_INSTRUCTOR": "John D",
        "TARGET_DATE": "2026-01-15",
        "START_TIME": "9:00 AM",
        "END_TIME": "10:00 AM",
        "EMAIL_SENDER": "test@gmail.com",
        "EMAIL_PASSWORD": "testpassword123",
        "EMAIL_RECEIVER": "receiver@gmail.com",
        "SMTP_SERVER": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "TWILIO_ACCOUNT_SID": "ACtest123456789",
        "TWILIO_AUTH_TOKEN": "test_auth_token",
        "TWILIO_FROM_NUMBER": "+15551234567",
        "SMS_NUMBER": "+15559876543",
        "NOTIFICATION_METHOD": "email",
        "RUN_ON_SCHEDULE": "false",
        "HEADLESS": "true",
    }


@pytest.fixture
def mock_env(env_vars: dict[str, str]):
    """Mock environment variables for testing."""
    with patch.dict(os.environ, env_vars, clear=True):
        yield env_vars


@pytest.fixture
def mock_webdriver():
    """Create a mock WebDriver."""
    driver = MagicMock()
    driver.current_url = "https://my.lifetime.life/test"
    driver.title = "Test Page"
    driver.find_elements.return_value = []
    driver.find_element.return_value = MagicMock()
    return driver


@pytest.fixture
def mock_wait():
    """Create a mock WebDriverWait."""
    wait = MagicMock()
    wait.until.return_value = MagicMock()
    return wait
