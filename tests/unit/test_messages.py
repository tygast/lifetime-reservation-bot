"""Unit tests for user-facing message formatting."""

from __future__ import annotations

from lifetime_bot.config import BotConfig
from lifetime_bot.messages import describe_failure, describe_outcome, format_class_details
from lifetime_bot.models import RegistrationOutcome, RegistrationResult


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


class TestFormatClassDetails:
    def test_includes_config_fields(self, bot_config: BotConfig) -> None:
        details = format_class_details(bot_config, "2026-04-29")
        assert "Class: Pickleball" in details
        assert "Instructor: John D" in details
        assert "Date: 2026-04-29" in details
        assert "Time: 9:00 AM - 10:00 AM" in details
        assert "Club: San Antonio 281" in details


class TestDescribeOutcome:
    def test_reserved_outcome(self) -> None:
        subject, body = describe_outcome(
            _result(RegistrationOutcome.RESERVED),
            "details",
        )
        assert subject == "Lifetime Bot - Reserved"
        assert "successfully reserved" in body
        assert "details" in body

    def test_waitlisted_outcome(self) -> None:
        subject, body = describe_outcome(
            _result(RegistrationOutcome.WAITLISTED),
            "details",
        )
        assert subject == "Lifetime Bot - Added to Waitlist"
        assert "waitlist" in body.lower()

    def test_already_reserved_outcome(self) -> None:
        subject, body = describe_outcome(
            _result(RegistrationOutcome.ALREADY_RESERVED),
            "details",
        )
        assert subject == "Lifetime Bot - Already Reserved"
        assert "already on your account" in body

    def test_unknown_status_falls_back(self) -> None:
        subject, body = describe_outcome(
            _result(
                RegistrationOutcome.PENDING_COMPLETION,
                raw_status="pending",
                needs_complete=True,
            ),
            "details",
        )
        assert "Registered" in subject
        assert "pending" in body


class TestDescribeFailure:
    def test_login_failure(self) -> None:
        subject, body = describe_failure(
            RuntimeError("login broke"),
            class_details="details",
            phase="login",
        )
        assert subject == "Lifetime Bot - Login Failed"
        assert "RuntimeError" in body
        assert "details" in body

    def test_reservation_failure(self) -> None:
        subject, body = describe_failure(
            ValueError("bad target"),
            class_details="details",
            phase="reservation",
        )
        assert subject == "Lifetime Bot - Failure"
        assert "ValueError" in body
        assert "details" in body
