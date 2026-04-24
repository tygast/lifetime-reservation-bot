"""Unit tests for LifetimeReservationBot."""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import (
    ClassEvent,
    RegistrationOutcome,
    RegistrationResult,
    SessionTokens,
)


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


def _response(
    payload: dict[str, object], *, ok: bool = True, status_code: int = 200, text: str = ""
) -> MagicMock:
    response = MagicMock()
    response.ok = ok
    response.status_code = status_code
    response.text = text or json.dumps(payload)
    response.json.return_value = payload
    return response


@pytest.fixture
def bot(bot_config: BotConfig) -> LifetimeReservationBot:
    """Bot with notifications stubbed and no live HTTP session yet."""
    with patch("lifetime_bot.bot.EmailNotificationService"), patch(
        "lifetime_bot.bot.SMSNotificationService"
    ):
        instance = LifetimeReservationBot(bot_config)
    instance.email_service = MagicMock()
    instance.sms_service = MagicMock()
    instance.email_service.send.return_value = True
    instance.sms_service.send.return_value = True
    return instance


class TestSendNotification:
    def test_email_only(self, bot: LifetimeReservationBot) -> None:
        bot.config.notification_method = "email"
        bot.send_notification("subject", "body")
        bot.email_service.send.assert_called_once_with("subject", "body")
        bot.sms_service.send.assert_not_called()

    def test_sms_only(self, bot: LifetimeReservationBot) -> None:
        bot.config.notification_method = "sms"
        bot.send_notification("subject", "body")
        bot.sms_service.send.assert_called_once_with("subject", "body")
        bot.email_service.send.assert_not_called()

    def test_both(self, bot: LifetimeReservationBot) -> None:
        bot.config.notification_method = "both"
        bot.send_notification("subject", "body")
        bot.email_service.send.assert_called_once()
        bot.sms_service.send.assert_called_once()

    def test_email_timeout_does_not_block(
        self, bot: LifetimeReservationBot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bot.config.notification_method = "email"

        def _slow_send(_subject: str, _body: str) -> bool:
            time.sleep(0.05)
            return True

        bot.email_service.send.side_effect = _slow_send

        with patch("lifetime_bot.bot.NOTIFICATION_TIMEOUT_SECONDS", 0.01):
            bot.send_notification("subject", "body")

        bot.email_service.send.assert_called_once_with("subject", "body")
        bot.sms_service.send.assert_not_called()
        captured = capsys.readouterr().out
        assert "Notification phase started: subject" in captured
        assert "Email notification timed out after 0.01s: subject" in captured


class TestGetClassDetails:
    def test_includes_config_fields(self, bot: LifetimeReservationBot) -> None:
        details = bot._get_class_details("2026-04-29")
        assert "Class: Pickleball" in details
        assert "Instructor: John D" in details
        assert "Date: 2026-04-29" in details
        assert "Time: 9:00 AM - 10:00 AM" in details
        assert "Club: San Antonio 281" in details


class TestDescribeOutcome:
    def _result(
        self,
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

    def test_reserved_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(
            self._result(RegistrationOutcome.RESERVED), "details"
        )
        assert subject == "Lifetime Bot - Reserved"
        assert "successfully reserved" in body
        assert "details" in body

    def test_waitlisted_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(
            self._result(RegistrationOutcome.WAITLISTED), "details"
        )
        assert subject == "Lifetime Bot - Added to Waitlist"
        assert "waitlist" in body.lower()

    def test_already_reserved_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(
            self._result(RegistrationOutcome.ALREADY_RESERVED), "details"
        )
        assert subject == "Lifetime Bot - Already Reserved"
        assert "already on your account" in body

    def test_unknown_status_falls_back(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(
            self._result(
                RegistrationOutcome.PENDING_COMPLETION,
                raw_status="pending",
                needs_complete=True,
            ),
            "details",
        )
        assert "Registered" in subject


class TestReserveClassHappyPath:
    def test_end_to_end_reserved(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="ZXhlcnA6ZXZ0",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.list_classes.return_value = [event]
        client.register.return_value = RegistrationResult(
            registration_id=99,
            outcome=RegistrationOutcome.RESERVED,
            raw_status="reserved",
            needs_complete=True,
            required_documents=(77,),
            raw={},
        )
        client.complete_registration.return_value = {"status": "complete"}

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = "John D"
        bot.config.target_class.start_time = "9:00 AM"
        bot.config.target_class.end_time = "10:00 AM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.RESERVED
        client.register.assert_called_once_with("ZXhlcnA6ZXZ0")
        client.complete_registration.assert_called_once_with(
            99, accepted_documents=[77]
        )
        bot.email_service.send.assert_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Reserved" in subject

    def test_logs_reservation_outcome_before_notification_phase(
        self,
        bot: LifetimeReservationBot,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="ZXhlcnA6ZXZ0",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.list_classes.return_value = [event]
        client.register.return_value = RegistrationResult(
            registration_id=99,
            outcome=RegistrationOutcome.RESERVED,
            raw_status="reserved",
            needs_complete=False,
            required_documents=None,
            raw={},
        )

        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.RESERVED
        captured = capsys.readouterr().out
        assert "Reservation outcome: Reserved." in captured
        assert "Notification phase started: Lifetime Bot - Reserved" in captured
        assert captured.index("Reservation outcome: Reserved.") < captured.index(
            "Notification phase started: Lifetime Bot - Reserved"
        )

    def test_skips_complete_when_not_needed(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="e",
            name="Pickleball",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=0,
            raw={},
        )
        client = MagicMock()
        client.list_classes.return_value = [event]
        client.register.return_value = RegistrationResult(
            registration_id=1,
            outcome=RegistrationOutcome.WAITLISTED,
            raw_status="waitlisted",
            needs_complete=False,
            required_documents=None,
            raw={},
        )

        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.WAITLISTED
        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Waitlist" in subject

    def test_fetches_required_documents_when_register_omits_them(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.list_classes.return_value = [event]
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.PENDING_COMPLETION,
            raw_status="pending",
            needs_complete=True,
            required_documents=None,
            raw={},
        )
        client.get_registration_info.return_value = {"agreement": {"agreementId": 77}}

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = "John D"
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.RESERVED
        client.complete_registration.assert_called_once_with(
            101, accepted_documents=[77]
        )
        subject = bot.email_service.send.call_args.args[0]
        assert subject == "Lifetime Bot - Reserved"

    def test_skips_post_when_already_reserved(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="Indoor Pickleball Court 3, San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.member_id = 110137193
        client.list_classes.return_value = [event]
        client.get_registration_info.return_value = {
            "registeredMembers": [{"id": 110137193, "name": "Tyler"}]
        }

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = ""
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.ALREADY_RESERVED
        client.register.assert_not_called()
        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Already Reserved" in subject

    def test_treats_duplicate_post_error_as_already_reserved(
        self,
        bot: LifetimeReservationBot,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="Indoor Pickleball Court 3, San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.member_id = 110137193
        client.list_classes.return_value = [event]
        client.get_registration_info.side_effect = [
            {"registeredMembers": []},
            {"registeredMembers": [{"id": 110137193, "name": "Tyler"}]},
        ]
        client.register.side_effect = LifetimeAPIError(
            "POST /event returned 500", status_code=500
        )

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = ""
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            result = bot.reserve_class()

        assert result.outcome is RegistrationOutcome.ALREADY_RESERVED
        client.register.assert_called_once_with("evt")
        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Already Reserved" in subject
        captured = capsys.readouterr().out
        assert "POST /event failed (POST /event returned 500)" in captured

    def test_raises_post_error_when_follow_up_still_not_registered(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="Indoor Pickleball Court 3, San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.member_id = 110137193
        client.list_classes.return_value = [event]
        client.get_registration_info.side_effect = [
            {"registeredMembers": []},
            {"registeredMembers": []},
        ]
        client.register.side_effect = LifetimeAPIError(
            "POST /event returned 500", status_code=500
        )

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = ""
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client), pytest.raises(
            LifetimeAPIError, match="POST /event returned 500"
        ):
            bot.reserve_class()

    def test_raises_when_required_documents_cannot_be_found(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client = MagicMock()
        client.list_classes.return_value = [event]
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.PENDING_COMPLETION,
            raw_status="pending",
            needs_complete=True,
            required_documents=None,
            raw={},
        )
        client.get_registration_info.return_value = {}

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = "John D"
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client), pytest.raises(
            LifetimeAPIError, match="no waiver/document ids"
        ):
            bot.reserve_class()

        client.complete_registration.assert_not_called()


class TestReserveClassFailures:
    def test_notifies_on_login_failure(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail() -> SessionTokens:
            raise RuntimeError("login broke")

        monkeypatch.setattr(bot, "_login_via_api", _fail)

        with pytest.raises(RuntimeError):
            bot.reserve_class()

        bot.email_service.send.assert_called()
        assert "Login" in bot.email_service.send.call_args.args[0]

    def test_notifies_on_missing_class(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bot, "_login_via_api", lambda: SAMPLE_TOKENS)
        client = MagicMock()
        client.list_classes.return_value = []

        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch(
            "lifetime_bot.bot.LifetimeAPIClient", return_value=client
        ), pytest.raises(LifetimeAPIError):
            bot.reserve_class()

        client.register.assert_not_called()
        assert "Failure" in bot.email_service.send.call_args.args[0]

