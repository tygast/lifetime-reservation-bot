"""Unit tests for LifetimeReservationBot."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from lifetime_bot.api import (
    ClassEvent,
    LifetimeAPIError,
    RegistrationResult,
    SessionTokens,
)
from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.config import BotConfig


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
    """Bot with notifications stubbed and no driver initialized yet."""
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


class TestGetClassDetails:
    def test_includes_config_fields(self, bot: LifetimeReservationBot) -> None:
        details = bot._get_class_details("2026-04-29")
        assert "Class: Pickleball" in details
        assert "Instructor: John D" in details
        assert "Date: 2026-04-29" in details
        assert "Time: 9:00 AM - 10:00 AM" in details
        assert "Club: San Antonio 281" in details


class TestDescribeOutcome:
    def _result(self, status: str, *, needs_complete: bool = False) -> RegistrationResult:
        return RegistrationResult(
            registration_id=1,
            status=status,
            needs_complete=needs_complete,
            required_documents=None,
            raw={},
        )

    def test_reserved_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(self._result("reserved"), "details")
        assert subject == "Lifetime Bot - Reserved"
        assert "successfully reserved" in body
        assert "details" in body

    def test_waitlisted_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(self._result("waitlisted"), "details")
        assert subject == "Lifetime Bot - Added to Waitlist"
        assert "waitlist" in body.lower()

    def test_already_reserved_outcome(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(self._result("already_reserved"), "details")
        assert subject == "Lifetime Bot - Already Reserved"
        assert "already on your account" in body

    def test_unknown_status_falls_back(self, bot: LifetimeReservationBot) -> None:
        subject, body = bot._describe_outcome(
            self._result("", needs_complete=True), "details"
        )
        assert "Registered" in subject


class TestFindTargetEvent:
    def test_returns_matching_class(self, bot: LifetimeReservationBot) -> None:
        client = MagicMock()
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="John D",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client.list_classes.return_value = [event]
        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = "John D"

        match = bot._find_target_event(client, "2026-04-29")

        assert match is event
        _, kwargs = client.list_classes.call_args
        assert kwargs["location"] == "San Antonio 281"
        assert kwargs["start"] == datetime(2026, 4, 26)
        assert kwargs["end"] == datetime(2026, 5, 3)

    def test_rejects_invalid_date(self, bot: LifetimeReservationBot) -> None:
        with pytest.raises(LifetimeAPIError):
            bot._find_target_event(MagicMock(), "not-a-date")

    def test_returns_none_when_no_match(self, bot: LifetimeReservationBot) -> None:
        client = MagicMock()
        client.list_classes.return_value = []
        assert bot._find_target_event(client, "2026-04-29") is None

    def test_ignores_bad_instructor_filter_when_event_has_no_instructor(
        self, bot: LifetimeReservationBot
    ) -> None:
        client = MagicMock()
        event = ClassEvent(
            event_id="evt",
            name="Pickleball Open Play: All Levels",
            instructor="",
            start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )
        client.list_classes.return_value = [event]
        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = "Wrong Name"
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"

        match = bot._find_target_event(client, "2026-04-29")

        assert match is event


class TestReserveClassHappyPath:
    def test_end_to_end_reserved(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bot, "_login_and_extract_tokens", lambda: SAMPLE_TOKENS
        )
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
            status="reserved",
            needs_complete=True,
            required_documents=[77],
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
            assert bot.reserve_class() is True

        client.register.assert_called_once_with("ZXhlcnA6ZXZ0")
        client.complete_registration.assert_called_once_with(
            99, accepted_documents=[77]
        )
        bot.email_service.send.assert_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Reserved" in subject

    def test_skips_complete_when_not_needed(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bot, "_login_and_extract_tokens", lambda: SAMPLE_TOKENS
        )
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
            status="waitlisted",
            needs_complete=False,
            required_documents=None,
            raw={},
        )

        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            assert bot.reserve_class() is True

        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Waitlist" in subject

    def test_skips_post_when_already_reserved(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bot, "_login_and_extract_tokens", lambda: SAMPLE_TOKENS
        )
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
            assert bot.reserve_class() is True

        client.register.assert_not_called()
        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Already Reserved" in subject

    def test_treats_duplicate_post_error_as_already_reserved(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bot, "_login_and_extract_tokens", lambda: SAMPLE_TOKENS
        )
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
        client.register.side_effect = LifetimeAPIError("POST /event returned 500")

        bot.config.target_class.name = "Pickleball"
        bot.config.target_class.instructor = ""
        bot.config.target_class.start_time = "7:00 PM"
        bot.config.target_class.end_time = "9:00 PM"
        bot.config.target_class.date = "2026-04-29"
        bot.config.run_on_schedule = False

        with patch("lifetime_bot.bot.LifetimeAPIClient", return_value=client):
            assert bot.reserve_class() is True

        client.register.assert_called_once_with("evt")
        client.complete_registration.assert_not_called()
        subject = bot.email_service.send.call_args.args[0]
        assert "Already Reserved" in subject


class TestReserveClassFailures:
    def test_notifies_on_login_failure(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail() -> SessionTokens:
            raise RuntimeError("login broke")

        monkeypatch.setattr(bot, "_login_and_extract_tokens", _fail)

        with pytest.raises(RuntimeError):
            bot.reserve_class()

        bot.email_service.send.assert_called()
        assert "Login" in bot.email_service.send.call_args.args[0]

    def test_notifies_on_missing_class(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bot, "_login_and_extract_tokens", lambda: SAMPLE_TOKENS
        )
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


class TestDirectAPIAuth:
    def test_login_via_api_returns_session_tokens(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = MagicMock()
        session.post.return_value = _response(
            {
                "message": "Success",
                "status": "0",
                "token": "auth-token",
                "ssoId": "sso-id",
            }
        )
        session.get.return_value = _response(
            {
                "jwt": "profile-jwt",
                "memberDetails": {
                    "memberId": 110137193,
                },
                "partyId": 1,
            }
        )
        session_factory = MagicMock(return_value=session)
        monkeypatch.setattr("lifetime_bot.bot.requests.Session", session_factory)

        tokens = bot._login_via_api()

        assert tokens.jwe == "auth-token"
        assert tokens.profile == "profile-jwt"
        assert tokens.ssoid == "sso-id"
        assert tokens.member_id == 110137193
        assert bot.api_session is session
        session.post.assert_called_once()
        session.get.assert_called_once()

    def test_auto_mode_falls_back_to_browser_when_direct_auth_fails(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot.config.auth_mode = "auto"
        monkeypatch.setattr(
            bot, "_login_via_api", MagicMock(side_effect=LifetimeAPIError("nope"))
        )
        browser = MagicMock(return_value=SAMPLE_TOKENS)
        monkeypatch.setattr(bot, "_login_and_extract_tokens_via_browser", browser)

        assert bot._login_and_extract_tokens() == SAMPLE_TOKENS
        browser.assert_called_once()

    def test_direct_mode_does_not_fallback_to_browser(
        self, bot: LifetimeReservationBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot.config.auth_mode = "direct"
        monkeypatch.setattr(
            bot, "_login_via_api", MagicMock(side_effect=LifetimeAPIError("bad auth"))
        )
        browser = MagicMock(return_value=SAMPLE_TOKENS)
        monkeypatch.setattr(bot, "_login_and_extract_tokens_via_browser", browser)

        with pytest.raises(LifetimeAPIError):
            bot._login_and_extract_tokens()

        browser.assert_not_called()


class TestExtractTokens:
    def test_returns_tokens_from_performance_log(
        self, bot: LifetimeReservationBot
    ) -> None:
        driver = MagicMock()
        bot.driver = driver
        driver.get_log.return_value = [
            {
                "message": json.dumps(
                    {
                        "message": {
                            "method": "Network.requestWillBeSent",
                            "params": {
                                "request": {
                                    "url": "https://api.lifetimefitness.com/ux/anything",
                                    "headers": {
                                        "X-Ltf-Jwe": "jwe-value",
                                        "X-Ltf-Profile": "profile-value",
                                        "X-Ltf-Ssoid": "ssoid-value",
                                    },
                                }
                            },
                        }
                    }
                )
            }
        ]
        with patch("lifetime_bot.bot.time.sleep"):
            tokens = bot._extract_tokens(attempts=1)

        assert tokens.jwe == "jwe-value"
        assert tokens.profile == "profile-value"
        assert tokens.ssoid == "ssoid-value"

    def test_raises_when_no_api_request_seen(
        self, bot: LifetimeReservationBot
    ) -> None:
        driver = MagicMock()
        bot.driver = driver
        driver.get_log.return_value = []
        with patch("lifetime_bot.bot.time.sleep"), pytest.raises(LifetimeAPIError):
            bot._extract_tokens(attempts=1)
