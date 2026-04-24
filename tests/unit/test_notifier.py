"""Unit tests for notification orchestration."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from lifetime_bot.notifier import NotificationCoordinator


@pytest.fixture
def services() -> tuple[MagicMock, MagicMock]:
    email = MagicMock()
    sms = MagicMock()
    email.send.return_value = True
    sms.send.return_value = True
    return email, sms


class TestNotificationCoordinator:
    def test_email_only(self, services: tuple[MagicMock, MagicMock]) -> None:
        email, sms = services
        coordinator = NotificationCoordinator(
            email_service=email,
            sms_service=sms,
            timeout_seconds=0.1,
        )

        result = coordinator.send("subject", "body", method="email")

        email.send.assert_called_once_with("subject", "body")
        sms.send.assert_not_called()
        assert [attempt.channel for attempt in result.attempts] == ["email"]

    def test_sms_only(self, services: tuple[MagicMock, MagicMock]) -> None:
        email, sms = services
        coordinator = NotificationCoordinator(
            email_service=email,
            sms_service=sms,
            timeout_seconds=0.1,
        )

        result = coordinator.send("subject", "body", method="sms")

        sms.send.assert_called_once_with("subject", "body")
        email.send.assert_not_called()
        assert [attempt.channel for attempt in result.attempts] == ["sms"]

    def test_both_channels(self, services: tuple[MagicMock, MagicMock]) -> None:
        email, sms = services
        coordinator = NotificationCoordinator(
            email_service=email,
            sms_service=sms,
            timeout_seconds=0.1,
        )

        result = coordinator.send("subject", "body", method="both")

        email.send.assert_called_once_with("subject", "body")
        sms.send.assert_called_once_with("subject", "body")
        assert [attempt.channel for attempt in result.attempts] == ["email", "sms"]

    def test_timeout_does_not_block(
        self,
        services: tuple[MagicMock, MagicMock],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        email, sms = services

        def _slow_send(_subject: str, _body: str) -> bool:
            time.sleep(0.05)
            return True

        email.send.side_effect = _slow_send
        coordinator = NotificationCoordinator(
            email_service=email,
            sms_service=sms,
            timeout_seconds=0.01,
        )

        result = coordinator.send("subject", "body", method="email")

        assert len(result.attempts) == 1
        assert result.attempts[0].completed is False
        captured = capsys.readouterr().out
        assert "Notification phase started: subject" in captured
        assert "Email notification timed out after 0.01s: subject" in captured

    def test_exception_is_reported(
        self,
        services: tuple[MagicMock, MagicMock],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        email, sms = services
        email.send.side_effect = RuntimeError("smtp exploded")
        coordinator = NotificationCoordinator(
            email_service=email,
            sms_service=sms,
            timeout_seconds=0.1,
        )

        result = coordinator.send("subject", "body", method="email")

        assert result.attempts[0].error == "RuntimeError: smtp exploded"
        captured = capsys.readouterr().out
        assert "Email notification failed: RuntimeError: smtp exploded" in captured
