"""Unit tests for the CLI entry point."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from lifetime_bot import __main__ as main_module


class TestRunBot:
    @patch("lifetime_bot.__main__.time.sleep")
    @patch("lifetime_bot.__main__.LifetimeReservationBot")
    def test_stops_after_first_success(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.return_value = True
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
        first.reserve_class.side_effect = RuntimeError("boom")
        second = MagicMock()
        second.reserve_class.return_value = True
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
    def test_false_result_is_treated_as_failure_and_retried(
        self, bot_class: MagicMock, sleep_mock: MagicMock
    ) -> None:
        first = MagicMock()
        first.reserve_class.return_value = False
        second = MagicMock()
        second.reserve_class.return_value = True
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
        first.reserve_class.side_effect = RuntimeError("boom")
        second = MagicMock()
        second.reserve_class.side_effect = RuntimeError("still boom")
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


class TestMain:
    @patch("lifetime_bot.__main__.run_bot", return_value=True)
    def test_main_runs_immediately_when_schedule_disabled(
        self, run_bot: MagicMock
    ) -> None:
        with patch.dict(os.environ, {"RUN_ON_SCHEDULE": "false"}, clear=False):
            assert main_module.main() == 0

        run_bot.assert_called_once_with()
