"""Unit tests for retry-aware reservation execution."""

from __future__ import annotations

import json
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
        bot.build_outcome_notification.return_value = (
            "Lifetime Bot - Reserved",
            "reserved body",
        )

        assert (
            runner.run_bot(
                bot_factory=lambda: bot,
                max_retries=1,
            )
            is True
        )

        bot.reserve_class.assert_called_once_with()
        bot.send_notification.assert_called_once_with(
            "Lifetime Bot - Reserved",
            "reserved body",
        )

    def test_retries_after_failure_then_succeeds(self) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        second.build_outcome_notification.return_value = (
            "Lifetime Bot - Reserved",
            "reserved body",
        )
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
        first.send_notification.assert_not_called()
        second.send_notification.assert_called_once_with(
            "Lifetime Bot - Reserved",
            "reserved body",
        )

    def test_non_terminal_result_is_treated_as_failure_and_retried(self) -> None:
        first = MagicMock()
        first.reserve_class.return_value = _result(
            RegistrationOutcome.PENDING_COMPLETION
        )
        second = MagicMock()
        second.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        second.build_outcome_notification.return_value = (
            "Lifetime Bot - Reserved",
            "reserved body",
        )
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
        first.send_notification.assert_not_called()
        second.send_notification.assert_called_once_with(
            "Lifetime Bot - Reserved",
            "reserved body",
        )

    def test_sends_terminal_notification_after_all_failures(self) -> None:
        first = MagicMock()
        first.reserve_class.side_effect = requests.Timeout("boom")
        second = MagicMock()
        second.reserve_class.side_effect = requests.Timeout("still boom")
        second.build_failure_notification.return_value = (
            "Lifetime Bot - Failure",
            "failure body",
        )
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
        first.send_notification.assert_not_called()
        second.send_notification.assert_called_once()
        subject, body = second.send_notification.call_args.args
        assert subject == "Lifetime Bot - All Attempts Failed"
        assert body == "Failed to reserve class after 2 attempts.\n\nfailure body"

    def test_does_not_retry_non_retryable_api_errors(self) -> None:
        bot = MagicMock()
        bot.reserve_class.side_effect = LifetimeAPIError(
            "bad target date", status_code=400
        )
        bot.build_failure_notification.return_value = (
            "Lifetime Bot - Failure",
            "failure body",
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
        bot.send_notification.assert_called_once_with(
            "Lifetime Bot - All Attempts Failed",
            "Failed to reserve class after 3 attempts.\n\nfailure body",
        )

    def test_writes_success_result_payload(
        self, tmp_path, monkeypatch
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bot.build_outcome_notification.return_value = (
            "Lifetime Bot - Reserved",
            "reserved body",
        )
        result_path = tmp_path / "result.json"
        monkeypatch.setenv(runner.RESULT_PATH_ENV, str(result_path))

        assert runner.run_bot(bot_factory=lambda: bot, max_retries=1) is True

        payload = json.loads(result_path.read_text())
        assert payload == {
            "body": "reserved body",
            "outcome": "reserved",
            "subject": "Lifetime Bot - Reserved",
            "success": True,
        }

    def test_skips_inline_notifications_when_disabled(
        self, tmp_path, monkeypatch
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.return_value = _result(RegistrationOutcome.RESERVED)
        bot.build_outcome_notification.return_value = (
            "Lifetime Bot - Reserved",
            "reserved body",
        )
        result_path = tmp_path / "result.json"
        monkeypatch.setenv(runner.RESULT_PATH_ENV, str(result_path))
        monkeypatch.setenv(runner.INLINE_NOTIFICATIONS_ENV, "false")

        assert runner.run_bot(bot_factory=lambda: bot, max_retries=1) is True

        bot.send_notification.assert_not_called()
        payload = json.loads(result_path.read_text())
        assert payload["subject"] == "Lifetime Bot - Reserved"

    def test_writes_failure_result_payload_when_notifications_disabled(
        self, tmp_path, monkeypatch
    ) -> None:
        bot = MagicMock()
        bot.reserve_class.side_effect = LifetimeAPIError("boom", status_code=500)
        bot.build_failure_notification.return_value = (
            "Lifetime Bot - Failure",
            "failure body",
        )
        result_path = tmp_path / "result.json"
        monkeypatch.setenv(runner.RESULT_PATH_ENV, str(result_path))
        monkeypatch.setenv(runner.INLINE_NOTIFICATIONS_ENV, "false")

        assert runner.run_bot(bot_factory=lambda: bot, max_retries=1) is False

        bot.send_notification.assert_not_called()
        payload = json.loads(result_path.read_text())
        assert payload == {
            "body": "Failed to reserve class after 1 attempts.\n\nfailure body",
            "subject": "Lifetime Bot - All Attempts Failed",
            "success": False,
        }
