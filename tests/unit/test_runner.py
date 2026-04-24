"""Unit tests for retry-aware reservation execution."""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from lifetime_bot import runner
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
    def test_stops_after_first_success(self) -> None:
        bot = MagicMock()
        bot.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)

        assert (
            runner.run_bot(
                bot_factory=lambda: bot,
                max_retries=1,
            )
            is True
        )

        bot.reserve_class.assert_called_once_with()
        bot.send_notification.assert_not_called()

    def test_retries_after_failure_then_succeeds(self) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bots = iter([first, second])
        sleep = MagicMock()

        assert (
            runner.run_bot(
                bot_factory=lambda: next(bots),
                max_retries=3,
                retry_delay=5.0,
                sleep=sleep,
            )
            is True
        )

        assert first.reserve_class.call_count == 1
        assert second.reserve_class.call_count == 1
        sleep.assert_called_once_with(5.0)

    def test_non_terminal_result_is_treated_as_failure_and_retried(self) -> None:
        first = MagicMock()
        first.reserve_class.return_value = _result(
            RegistrationOutcome.PENDING_COMPLETION
        )
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bots = iter([first, second])
        sleep = MagicMock()

        assert (
            runner.run_bot(
                bot_factory=lambda: next(bots),
                max_retries=3,
                retry_delay=2.0,
                sleep=sleep,
            )
            is True
        )

        assert first.reserve_class.call_count == 1
        assert second.reserve_class.call_count == 1
        sleep.assert_called_once_with(2.0)

    def test_sends_terminal_notification_after_all_failures(self) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.side_effect = requests.Timeout("still boom")
        bots = iter([first, second])
        sleep = MagicMock()

        assert (
            runner.run_bot(
                bot_factory=lambda: next(bots),
                max_retries=2,
                retry_delay=1.0,
                sleep=sleep,
            )
            is False
        )

        sleep.assert_called_once_with(1.0)
        second.send_notification.assert_called_once()
        subject, body = second.send_notification.call_args.args
        assert subject == "Lifetime Bot - All Attempts Failed"
        assert "still boom" in body

    def test_does_not_retry_non_retryable_api_errors(self) -> None:
        bot = MagicMock()
        bot.reserve_class.side_effect = LifetimeAPIError(
            "bad target date", status_code=400
        )
        sleep = MagicMock()

        assert (
            runner.run_bot(
                bot_factory=lambda: bot,
                max_retries=3,
                retry_delay=5.0,
                sleep=sleep,
            )
            is False
        )

        bot.reserve_class.assert_called_once_with()
        sleep.assert_not_called()
        bot.send_notification.assert_called_once()
