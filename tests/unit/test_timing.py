"""Unit tests for the timing utilities module."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.utils.timing import (
    get_target_date,
    get_target_utc_time,
    is_valid_day,
    wait_until_utc,
)


class TestGetTargetDate:
    """Tests for get_target_date function."""

    @patch("lifetime_bot.utils.timing.datetime")
    def test_run_on_schedule_returns_8_days_from_now(
        self, mock_datetime: MagicMock
    ) -> None:
        """Test that run_on_schedule=True returns date 8 days from now."""
        mock_now = datetime.datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta

        result = get_target_date(run_on_schedule=True)

        assert result == "2026-01-23"

    @patch("lifetime_bot.utils.timing.datetime")
    def test_not_on_schedule_with_target_date(
        self, mock_datetime: MagicMock
    ) -> None:
        """Test that explicit target_date is returned when not on schedule."""
        result = get_target_date(run_on_schedule=False, target_date="2026-02-01")

        assert result == "2026-02-01"

    @patch("lifetime_bot.utils.timing.datetime")
    def test_not_on_schedule_without_target_date(
        self, mock_datetime: MagicMock
    ) -> None:
        """Test that today's date is returned when no target_date provided."""
        mock_now = datetime.datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        result = get_target_date(run_on_schedule=False, target_date=None)

        assert result == "2026-01-15"

    @patch("lifetime_bot.utils.timing.datetime")
    def test_not_on_schedule_with_empty_target_date(
        self, mock_datetime: MagicMock
    ) -> None:
        """Test that today's date is returned when target_date is empty string."""
        mock_now = datetime.datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        result = get_target_date(run_on_schedule=False, target_date="")

        assert result == "2026-01-15"


class TestGetTargetUtcTime:
    """Tests for get_target_utc_time function."""

    @patch("lifetime_bot.utils.timing.datetime")
    def test_cst_to_utc_standard_time(self, mock_datetime: MagicMock) -> None:
        """Test conversion from CST (standard time) to UTC.

        CST is UTC-6, so 10:00 AM CST = 16:00 UTC.
        """
        # January is standard time (CST, UTC-6)
        mock_now = datetime.datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.datetime.combine = datetime.datetime.combine
        mock_datetime.timezone = datetime.timezone

        result = get_target_utc_time("10:00:00", "America/Chicago")

        assert result == "16:00:00"

    @patch("lifetime_bot.utils.timing.datetime")
    def test_cdt_to_utc_daylight_time(self, mock_datetime: MagicMock) -> None:
        """Test conversion from CDT (daylight time) to UTC.

        CDT is UTC-5, so 10:00 AM CDT = 15:00 UTC.
        """
        # July is daylight saving time (CDT, UTC-5)
        mock_now = datetime.datetime(2026, 7, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.datetime.combine = datetime.datetime.combine
        mock_datetime.timezone = datetime.timezone

        result = get_target_utc_time("10:00:00", "America/Chicago")

        assert result == "15:00:00"

    @patch("lifetime_bot.utils.timing.datetime")
    def test_different_timezone(self, mock_datetime: MagicMock) -> None:
        """Test conversion from different timezone (PST) to UTC.

        PST is UTC-8, so 10:00 AM PST = 18:00 UTC.
        """
        # January is standard time
        mock_now = datetime.datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.datetime.combine = datetime.datetime.combine
        mock_datetime.timezone = datetime.timezone

        result = get_target_utc_time("10:00:00", "America/Los_Angeles")

        assert result == "18:00:00"


class TestIsValidDay:
    """Tests for is_valid_day function."""

    @patch("lifetime_bot.utils.timing.datetime")
    def test_monday_is_valid(self, mock_datetime: MagicMock) -> None:
        """Test that Monday is a valid day."""
        # Monday is weekday 0
        mock_datetime.datetime.today.return_value.weekday.return_value = 0
        assert is_valid_day() is True

    @patch("lifetime_bot.utils.timing.datetime")
    def test_tuesday_is_valid(self, mock_datetime: MagicMock) -> None:
        """Test that Tuesday is a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 1
        assert is_valid_day() is True

    @patch("lifetime_bot.utils.timing.datetime")
    def test_wednesday_is_valid(self, mock_datetime: MagicMock) -> None:
        """Test that Wednesday is a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 2
        assert is_valid_day() is True

    @patch("lifetime_bot.utils.timing.datetime")
    def test_thursday_is_valid(self, mock_datetime: MagicMock) -> None:
        """Test that Thursday is a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 3
        assert is_valid_day() is True

    @patch("lifetime_bot.utils.timing.datetime")
    def test_friday_is_invalid(self, mock_datetime: MagicMock) -> None:
        """Test that Friday is not a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 4
        assert is_valid_day() is False

    @patch("lifetime_bot.utils.timing.datetime")
    def test_saturday_is_invalid(self, mock_datetime: MagicMock) -> None:
        """Test that Saturday is not a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 5
        assert is_valid_day() is False

    @patch("lifetime_bot.utils.timing.datetime")
    def test_sunday_is_valid(self, mock_datetime: MagicMock) -> None:
        """Test that Sunday is a valid day."""
        mock_datetime.datetime.today.return_value.weekday.return_value = 6
        assert is_valid_day() is True


class TestWaitUntilUtc:
    """Tests for wait_until_utc function."""

    @patch("lifetime_bot.utils.timing.time.sleep")
    @patch("lifetime_bot.utils.timing.datetime")
    def test_runs_immediately_when_past_target(
        self, mock_datetime: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Test callback runs immediately when current time is past target."""
        # Current time is 17:00 UTC, target is 16:00 UTC
        mock_now = datetime.datetime(
            2026, 1, 15, 17, 0, 0, tzinfo=datetime.timezone.utc
        )
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime.return_value = datetime.datetime(
            1900, 1, 1, 16, 0, 0
        )
        mock_datetime.datetime.combine.return_value = datetime.datetime(
            2026, 1, 15, 16, 0, 0
        )
        mock_datetime.timezone = datetime.timezone

        callback = MagicMock()
        wait_until_utc("16:00:00", callback)

        mock_sleep.assert_not_called()
        callback.assert_called_once()

    @patch("lifetime_bot.utils.timing.time.sleep")
    @patch("lifetime_bot.utils.timing.datetime")
    def test_sleeps_until_target_time(
        self, mock_datetime: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Test that function sleeps until target time."""
        # Current time is 15:00 UTC, target is 16:00 UTC (1 hour = 3600 seconds)
        mock_now = datetime.datetime(
            2026, 1, 15, 15, 0, 0, tzinfo=datetime.timezone.utc
        )
        mock_target = datetime.datetime(
            2026, 1, 15, 16, 0, 0, tzinfo=datetime.timezone.utc
        )
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime.return_value = datetime.datetime(
            1900, 1, 1, 16, 0, 0
        )
        mock_datetime.datetime.combine.return_value.replace.return_value = mock_target
        mock_datetime.timezone = datetime.timezone

        callback = MagicMock()
        wait_until_utc("16:00:00", callback)

        mock_sleep.assert_called_once_with(3600.0)
        callback.assert_called_once()

    @patch("lifetime_bot.utils.timing.time.sleep")
    @patch("lifetime_bot.utils.timing.datetime")
    def test_callback_is_executed(
        self, mock_datetime: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Test that callback is always executed."""
        mock_now = datetime.datetime(
            2026, 1, 15, 18, 0, 0, tzinfo=datetime.timezone.utc
        )
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.strptime.return_value = datetime.datetime(
            1900, 1, 1, 16, 0, 0
        )
        mock_datetime.datetime.combine.return_value = datetime.datetime(
            2026, 1, 15, 16, 0, 0
        )
        mock_datetime.timezone = datetime.timezone

        callback = MagicMock()
        wait_until_utc("16:00:00", callback)

        callback.assert_called_once()
