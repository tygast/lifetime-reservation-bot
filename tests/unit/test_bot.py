"""Unit tests for the bot module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import (
    BotConfig,
    ClassConfig,
    ClubConfig,
    EmailConfig,
    SMSConfig,
)


@pytest.fixture
def mock_create_driver():
    """Mock the create_driver function."""
    with patch("lifetime_bot.bot.create_driver") as mock:
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        mock.return_value = (mock_driver, mock_wait)
        yield mock, mock_driver, mock_wait


@pytest.fixture
def bot_with_mocks(
    bot_config: BotConfig, mock_create_driver
) -> tuple[LifetimeReservationBot, MagicMock, MagicMock]:
    """Create a bot with mocked dependencies."""
    _, mock_driver, mock_wait = mock_create_driver
    bot = LifetimeReservationBot(config=bot_config)
    return bot, mock_driver, mock_wait


class TestLifetimeReservationBotInit:
    """Tests for LifetimeReservationBot initialization."""

    def test_init_with_config(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test bot initialization with explicit config."""
        bot = LifetimeReservationBot(config=bot_config)
        assert bot.config == bot_config

    @patch("lifetime_bot.bot.BotConfig.from_env")
    def test_init_without_config(
        self,
        mock_from_env: MagicMock,
        bot_config: BotConfig,
        mock_create_driver,
    ) -> None:
        """Test bot initialization loads config from environment."""
        mock_from_env.return_value = bot_config
        bot = LifetimeReservationBot()
        mock_from_env.assert_called_once()
        assert bot.config == bot_config

    def test_init_sets_already_reserved_false(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test that _already_reserved starts as False."""
        bot = LifetimeReservationBot(config=bot_config)
        assert bot._already_reserved is False

    def test_init_creates_notification_services(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test that notification services are created."""
        bot = LifetimeReservationBot(config=bot_config)
        assert bot.email_service is not None
        assert bot.sms_service is not None


class TestSendNotification:
    """Tests for send_notification method."""

    def test_send_notification_email(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test sending email notification."""
        bot, _, _ = bot_with_mocks
        bot.email_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        bot.email_service.send.assert_called_once_with("Test Subject", "Test Message")

    def test_send_notification_sms(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test sending SMS notification."""
        bot_config.notification_method = "sms"
        _, mock_driver, mock_wait = mock_create_driver
        bot = LifetimeReservationBot(config=bot_config)
        bot.sms_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        bot.sms_service.send.assert_called_once_with("Test Subject", "Test Message")

    def test_send_notification_both(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test sending both email and SMS notifications."""
        bot_config.notification_method = "both"
        _, mock_driver, mock_wait = mock_create_driver
        bot = LifetimeReservationBot(config=bot_config)
        bot.email_service.send = MagicMock(return_value=True)
        bot.sms_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        bot.email_service.send.assert_called_once_with("Test Subject", "Test Message")
        bot.sms_service.send.assert_called_once_with("Test Subject", "Test Message")

    def test_send_notification_unknown_method_defaults_to_email(
        self, bot_config: BotConfig, mock_create_driver
    ) -> None:
        """Test that unknown method defaults to email."""
        bot_config.notification_method = "unknown"
        _, mock_driver, mock_wait = mock_create_driver
        bot = LifetimeReservationBot(config=bot_config)
        bot.email_service.send = MagicMock(return_value=True)

        bot.send_notification("Test Subject", "Test Message")

        bot.email_service.send.assert_called_once()


class TestGetTargetDate:
    """Tests for _get_target_date method."""

    @patch("lifetime_bot.bot.get_target_date")
    def test_get_target_date_calls_utility(
        self,
        mock_get_target_date: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test that _get_target_date calls the utility function."""
        bot, _, _ = bot_with_mocks
        mock_get_target_date.return_value = "2026-01-23"

        result = bot._get_target_date()

        mock_get_target_date.assert_called_once_with(
            bot.config.run_on_schedule,
            bot.config.target_class.date,
        )
        assert result == "2026-01-23"


class TestGetClassDetails:
    """Tests for _get_class_details method."""

    def test_get_class_details_format(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test class details are formatted correctly."""
        bot, _, _ = bot_with_mocks

        result = bot._get_class_details("2026-01-15")

        assert "Class: Pickleball" in result
        assert "Instructor: John D" in result
        assert "Date: 2026-01-15" in result
        assert "Time: 9:00 AM - 10:00 AM" in result


class TestLogin:
    """Tests for login method."""

    @patch("lifetime_bot.bot.time.sleep")
    def test_login_enters_credentials(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test that login enters username and password."""
        bot, mock_driver, mock_wait = bot_with_mocks
        mock_element = MagicMock()
        mock_wait.until.return_value = mock_element

        bot.login()

        mock_driver.get.assert_called_once_with(bot.config.login_url)
        # Wait should be called for both username and password fields
        assert mock_wait.until.call_count == 2


class TestNavigateToSchedule:
    """Tests for navigate_to_schedule method."""

    def test_navigate_to_schedule_success(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test successful navigation to schedule."""
        bot, mock_driver, mock_wait = bot_with_mocks

        result = bot.navigate_to_schedule("2026-01-15")

        assert result is True
        mock_driver.get.assert_called_once()
        # URL should contain the club and date info
        call_url = mock_driver.get.call_args[0][0]
        assert "2026-01-15" in call_url
        assert "san-antonio-281" in call_url

    def test_navigate_to_schedule_failure(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test navigation failure when schedule doesn't load."""
        bot, mock_driver, mock_wait = bot_with_mocks
        mock_wait.until.side_effect = Exception("Timeout")

        result = bot.navigate_to_schedule("2026-01-15")

        assert result is False


class TestIsMatchingClass:
    """Tests for _is_matching_class method."""

    def test_matching_class_returns_true(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that matching class returns True."""
        bot, _, _ = bot_with_mocks
        mock_element = MagicMock()
        mock_element.text = "Pickleball\nJohn D\n9:00 to 10:00 AM"

        result = bot._is_matching_class(mock_element)

        assert result is True

    def test_non_matching_class_name_returns_false(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that non-matching class name returns False."""
        bot, _, _ = bot_with_mocks
        mock_element = MagicMock()
        mock_element.text = "Yoga\nJohn D\n9:00 to 10:00 AM"

        result = bot._is_matching_class(mock_element)

        assert result is False

    def test_non_matching_time_returns_false(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that non-matching time returns False."""
        bot, _, _ = bot_with_mocks
        mock_element = MagicMock()
        mock_element.text = "Pickleball\nJohn D\n10:00 to 11:00 AM"

        result = bot._is_matching_class(mock_element)

        assert result is False

    def test_non_matching_instructor_returns_false(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that non-matching instructor returns False."""
        bot, _, _ = bot_with_mocks
        mock_element = MagicMock()
        mock_element.text = "Pickleball\nJane S\n9:00 to 10:00 AM"

        result = bot._is_matching_class(mock_element)

        assert result is False

    def test_no_time_match_returns_false(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that class without proper time format returns False."""
        bot, _, _ = bot_with_mocks
        mock_element = MagicMock()
        mock_element.text = "Pickleball\nJohn D\nNo time info"

        result = bot._is_matching_class(mock_element)

        assert result is False


class TestFindTargetClass:
    """Tests for find_target_class method."""

    @patch("lifetime_bot.bot.time.sleep")
    def test_find_target_class_found(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test finding target class."""
        bot, mock_driver, mock_wait = bot_with_mocks

        mock_class_element = MagicMock()
        mock_class_element.text = "Pickleball\nJohn D\n9:00 to 10:00 AM"
        mock_link = MagicMock()
        mock_class_element.find_element.return_value = mock_link

        mock_wait.until.return_value = [mock_class_element]

        result = bot.find_target_class()

        assert result == mock_link

    @patch("lifetime_bot.bot.time.sleep")
    def test_find_target_class_not_found(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test when target class is not found."""
        bot, mock_driver, mock_wait = bot_with_mocks

        mock_class_element = MagicMock()
        mock_class_element.text = "Yoga\nJane S\n11:00 to 12:00 AM"

        mock_wait.until.return_value = [mock_class_element]

        result = bot.find_target_class()

        assert result is None


class TestClickReserveButton:
    """Tests for _click_reserve_button method."""

    @patch("lifetime_bot.bot.time.sleep")
    def test_click_reserve_button_success(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test clicking reserve button."""
        bot, mock_driver, _ = bot_with_mocks

        mock_button = MagicMock()
        mock_button.text = "Reserve"
        mock_driver.find_elements.return_value = [mock_button]

        result = bot._click_reserve_button()

        assert result is True
        mock_driver.execute_script.assert_called()

    @patch("lifetime_bot.bot.time.sleep")
    def test_click_reserve_button_already_reserved(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test when class is already reserved."""
        bot, mock_driver, _ = bot_with_mocks
        bot.send_notification = MagicMock()

        mock_button = MagicMock()
        mock_button.text = "Cancel Reservation"
        mock_driver.find_elements.return_value = [mock_button]

        result = bot._click_reserve_button()

        assert result is False
        assert bot._already_reserved is True

    @patch("lifetime_bot.bot.time.sleep")
    def test_click_reserve_button_add_to_waitlist(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test clicking add to waitlist button."""
        bot, mock_driver, _ = bot_with_mocks

        mock_button = MagicMock()
        mock_button.text = "Add to Waitlist"
        mock_driver.find_elements.return_value = [mock_button]

        result = bot._click_reserve_button()

        assert result is True

    @patch("lifetime_bot.bot.time.sleep")
    def test_click_reserve_button_no_button_found(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test when no button is found."""
        bot, mock_driver, _ = bot_with_mocks
        mock_driver.find_elements.return_value = []

        with pytest.raises(RuntimeError, match="No reserve/waitlist/cancel button found"):
            bot._click_reserve_button()


class TestHandleWaiver:
    """Tests for _handle_waiver method."""

    @patch("lifetime_bot.bot.time.sleep")
    def test_handle_waiver_clicks_checkbox(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test handling waiver checkbox."""
        bot, mock_driver, mock_wait = bot_with_mocks

        mock_label = MagicMock()
        mock_wait.until.return_value = mock_label

        mock_checkbox = MagicMock()
        mock_checkbox.is_selected.return_value = True
        mock_driver.find_element.return_value = mock_checkbox

        bot._handle_waiver()

        mock_label.click.assert_called_once()


class TestClickFinish:
    """Tests for _click_finish method."""

    def test_click_finish_clicks_button(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test clicking finish button."""
        bot, _, mock_wait = bot_with_mocks

        mock_button = MagicMock()
        mock_wait.until.return_value = mock_button

        bot._click_finish()

        mock_button.click.assert_called_once()


class TestVerifyConfirmation:
    """Tests for _verify_confirmation method."""

    def test_verify_confirmation_success(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test successful confirmation verification."""
        bot, _, mock_wait = bot_with_mocks
        mock_wait.until.return_value = MagicMock()

        result = bot._verify_confirmation()

        assert result is True

    def test_verify_confirmation_failure(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test failed confirmation verification."""
        bot, _, mock_wait = bot_with_mocks
        mock_wait.until.side_effect = Exception("Timeout")

        result = bot._verify_confirmation()

        assert result is False


class TestCompleteReservation:
    """Tests for _complete_reservation method."""

    @patch("lifetime_bot.bot.time.sleep")
    def test_complete_reservation_success(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test successful reservation completion."""
        bot, mock_driver, mock_wait = bot_with_mocks
        mock_driver.find_elements.return_value = []  # No waiver elements

        bot._click_reserve_button = MagicMock(return_value=True)
        bot._click_finish = MagicMock()
        bot._verify_confirmation = MagicMock(return_value=True)

        result = bot._complete_reservation()

        assert result is True
        bot._click_reserve_button.assert_called_once()
        bot._click_finish.assert_called_once()
        bot._verify_confirmation.assert_called_once()

    @patch("lifetime_bot.bot.time.sleep")
    def test_complete_reservation_already_reserved(
        self,
        mock_sleep: MagicMock,
        bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock],
    ) -> None:
        """Test when class is already reserved."""
        bot, _, _ = bot_with_mocks

        bot._click_reserve_button = MagicMock(return_value=False)

        result = bot._complete_reservation()

        assert result is True
        bot._click_reserve_button.assert_called_once()


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_clears_browser_data(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that cleanup clears browser data."""
        bot, mock_driver, _ = bot_with_mocks

        bot.cleanup()

        mock_driver.delete_all_cookies.assert_called_once()
        # Should call localStorage and sessionStorage clear
        assert mock_driver.execute_script.call_count == 2

    def test_cleanup_handles_errors(
        self, bot_with_mocks: tuple[LifetimeReservationBot, MagicMock, MagicMock]
    ) -> None:
        """Test that cleanup handles errors gracefully."""
        bot, mock_driver, _ = bot_with_mocks
        mock_driver.delete_all_cookies.side_effect = Exception("Error")

        # Should not raise an exception
        bot.cleanup()
