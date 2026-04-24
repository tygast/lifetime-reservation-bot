"""Unit tests for the CLI entry point."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import requests

from lifetime_bot import __main__ as main_module
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import RegistrationOutcome, RegistrationResult


def _result(outcome: RegistrationOutcome) -> RegistrationResult:
    return RegistrationResult(
        registration_id=1,
        outcome=outcome,
        raw_status=outcome.value,
        needs_complete=False,
        required_documents=None,
        raw={},
    )


class TestRunBot:
    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_stops_after_first_success(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bot_class.return_value = bot

        with patch.dict(os.environ, {}, clear=False):
            assert main_module.run_bot() is True

        bot_class.assert_called_once_with()
        sleep_mock.assert_not_called()
        bot.send_notification.assert_not_called()

    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_retries_after_failure_then_succeeds(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bot_class.side_effect = [first, second]

        with patch.dict(
            os.environ,
            {"MAX_RETRIES": "3", "RETRY_DELAY_SECONDS": "5"},
            clear=False,
        ):
            assert main_module.run_bot() is True

        assert bot_class.call_count == 2
        sleep_mock.assert_called_once_with(5.0)

    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_non_terminal_result_is_treated_as_failure_and_retried(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        first = MagicMock()
        first.reserve_class.return_value = _result(
            RegistrationOutcome.PENDING_COMPLETION
        )
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bot_class.side_effect = [first, second]

        with patch.dict(
            os.environ,
            {"MAX_RETRIES": "3", "RETRY_DELAY_SECONDS": "2"},
            clear=False,
        ):
            assert main_module.run_bot() is True

        assert bot_class.call_count == 2
        sleep_mock.assert_called_once_with(2.0)

    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_sends_terminal_notification_after_all_failures(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.side_effect = requests.Timeout("still boom")
        bot_class.side_effect = [first, second]

        with patch.dict(
            os.environ,
            {"MAX_RETRIES": "2", "RETRY_DELAY_SECONDS": "1"},
            clear=False,
        ):
            assert main_module.run_bot() is False

        assert bot_class.call_count == 2
        sleep_mock.assert_called_once_with(1.0)
        second.send_notification.assert_called_once()
        subject, body = second.send_notification.call_args.args
        assert subject == "Lifetime Bot - All Attempts Failed"
        assert "still boom" in body

    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_does_not_retry_non_retryable_api_errors(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.side_effect = LifetimeAPIError(
            "bad target date", status_code=400
        )
        bot_class.return_value = bot

        with patch.dict(
            os.environ,
            {"MAX_RETRIES": "3", "RETRY_DELAY_SECONDS": "5"},
            clear=False,
        ):
            assert main_module.run_bot() is False

        bot_class.assert_called_once_with()
        sleep_mock.assert_not_called()
        bot.send_notification.assert_called_once()


class TestMain:
    @patch("lifetime_bot.__main__.run_bot", return_value=True)
    def test_main_runs_immediately_when_schedule_disabled(
        self, run_bot: MagicMock
    ) -> None:
        with patch.dict(os.environ, {"RUN_ON_SCHEDULE": "false"}, clear=False):
            assert main_module.main() == 0

        run_bot.assert_called_once_with()
