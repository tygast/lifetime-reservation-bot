"""Unit tests for LifetimeReservationBot orchestration."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from lifetime_bot.auth import AuthenticatedSession
from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import RegistrationOutcome, RegistrationResult, SessionTokens
from lifetime_bot.notifier import NotificationDispatchResult


def _profile_jwt(member_id: int = 110137193) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"memberId": member_id}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


SAMPLE_TOKENS = SessionTokens(
    jwe="jwe-blob",
    profile=_profile_jwt(),
    ssoid="C_abc",
)


@dataclass
class BotHarness:
    bot: LifetimeReservationBot
    authenticator: MagicMock
    notifier: MagicMock
    reservation_service: MagicMock
    reservation_service_factory: MagicMock


def _result(
    outcome: RegistrationOutcome,
    *,
    raw_status: str | None = None,
    needs_complete: bool = False,
    required_documents: tuple[int, ...] | None = None,
) -> RegistrationResult:
    return RegistrationResult(
        registration_id=1,
        outcome=outcome,
        raw_status=raw_status or outcome.value,
        needs_complete=needs_complete,
        required_documents=required_documents,
        raw={},
    )


def _build_harness(bot_config: BotConfig) -> BotHarness:
    authenticated = AuthenticatedSession(
        tokens=SAMPLE_TOKENS,
        session=MagicMock(),
    )
    authenticator = MagicMock()
    authenticator.login.return_value = authenticated
    notifier = MagicMock()
    notifier.send.return_value = NotificationDispatchResult(
        subject="subject",
        attempts=(),
    )
    reservation_service = MagicMock()
    reservation_service_factory = MagicMock(return_value=reservation_service)
    bot = LifetimeReservationBot(
        bot_config,
        authenticator=authenticator,
        notifier=notifier,
        reservation_service_factory=reservation_service_factory,
    )
    return BotHarness(
        bot=bot,
        authenticator=authenticator,
        notifier=notifier,
        reservation_service=reservation_service,
        reservation_service_factory=reservation_service_factory,
    )


@pytest.fixture
def harness(bot_config: BotConfig) -> BotHarness:
    return _build_harness(bot_config)


class TestSendNotification:
    def test_email_only(self, harness: BotHarness) -> None:
        harness.bot.config.notification_method = "email"

        harness.bot.send_notification("subject", "body")

        harness.notifier.send.assert_called_once_with(
            "subject", "body", method="email"
        )

    def test_sms_only(self, harness: BotHarness) -> None:
        harness.bot.config.notification_method = "sms"

        harness.bot.send_notification("subject", "body")

        harness.notifier.send.assert_called_once_with("subject", "body", method="sms")

    def test_both(self, harness: BotHarness) -> None:
        harness.bot.config.notification_method = "both"

        harness.bot.send_notification("subject", "body")

        harness.notifier.send.assert_called_once_with(
            "subject", "body", method="both"
        )


class TestReserveClass:
    def test_end_to_end_reserved(self, harness: BotHarness) -> None:
        event = MagicMock(
            event_id="ZXhlcnA6ZXZ0",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        )
        harness.reservation_service.find_target_event.return_value = event
        harness.reservation_service.reserve_event.return_value = _result(
            RegistrationOutcome.RESERVED,
            raw_status="reserved",
        )

        harness.bot.config.target_class.date = "2026-04-29"
        harness.bot.config.run_on_schedule = False

        result = harness.bot.reserve_class()

        assert result.outcome is RegistrationOutcome.RESERVED
        harness.authenticator.login.assert_called_once_with(
            harness.bot.config.username,
            harness.bot.config.password,
        )
        harness.reservation_service_factory.assert_called_once()
        harness.reservation_service.find_target_event.assert_called_once_with(
            club_name="San Antonio 281",
            target_class=harness.bot.config.target_class,
            target_date="2026-04-29",
        )
        harness.reservation_service.reserve_event.assert_called_once_with("ZXhlcnA6ZXZ0")
        harness.notifier.send.assert_called_once()
        assert harness.notifier.send.call_args.args[0] == "Lifetime Bot - Reserved"

    def test_logs_reservation_outcome_before_notification_phase(
        self,
        harness: BotHarness,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = MagicMock(
            event_id="ZXhlcnA6ZXZ0",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        )
        harness.reservation_service.find_target_event.return_value = event
        harness.reservation_service.reserve_event.return_value = _result(
            RegistrationOutcome.RESERVED,
            raw_status="reserved",
        )

        harness.bot.config.target_class.date = "2026-04-29"
        harness.bot.config.run_on_schedule = False

        harness.bot.reserve_class()

        captured = capsys.readouterr().out
        assert "Reservation outcome: Reserved." in captured
        assert captured.index("Reservation outcome: Reserved.") < captured.index(
            "Reservation flow finished"
        )


class TestReserveClassFailures:
    def test_notifies_on_login_failure(self, harness: BotHarness) -> None:
        harness.authenticator.login.side_effect = RuntimeError("login broke")

        with pytest.raises(RuntimeError):
            harness.bot.reserve_class()

        harness.notifier.send.assert_called_once()
        assert harness.notifier.send.call_args.args[0] == "Lifetime Bot - Login Failed"

    def test_notifies_on_missing_class(self, harness: BotHarness) -> None:
        harness.reservation_service.find_target_event.return_value = None
        harness.bot.config.target_class.date = "2026-04-29"
        harness.bot.config.run_on_schedule = False

        with pytest.raises(LifetimeAPIError):
            harness.bot.reserve_class()

        harness.reservation_service.reserve_event.assert_not_called()
        assert harness.notifier.send.call_args.args[0] == "Lifetime Bot - Failure"
