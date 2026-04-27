"""Unit tests for reservation workflow services."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from lifetime_bot.config import ClassConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationOutcome, RegistrationResult
from lifetime_bot.reservations import ReservationService


def _target_class(
    *,
    name: str = "Pickleball",
    instructor: str = "John D",
    date: str = "2026-04-29",
    start_time: str = "9:00 AM",
    end_time: str = "10:00 AM",
) -> ClassConfig:
    return ClassConfig(
        name=name,
        instructor=instructor,
        date=date,
        start_time=start_time,
        end_time=end_time,
    )


class TestReservationServiceFindTargetEvent:
    def test_returns_matching_class(self) -> None:
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

        match = ReservationService(client).find_target_event(
            club_name="San Antonio 281",
            target_class=_target_class(),
            target_date="2026-04-29",
        )

        assert match is event
        _, kwargs = client.list_classes.call_args
        assert kwargs["location"] == "San Antonio 281"
        assert kwargs["start"] == datetime(2026, 4, 26)
        assert kwargs["end"] == datetime(2026, 5, 3)

    def test_rejects_invalid_date(self) -> None:
        with pytest.raises(LifetimeAPIError):
            ReservationService(MagicMock()).find_target_event(
                club_name="San Antonio 281",
                target_class=_target_class(),
                target_date="not-a-date",
            )

    def test_returns_none_when_no_match(self) -> None:
        client = MagicMock()
        client.list_classes.return_value = []

        match = ReservationService(client).find_target_event(
            club_name="San Antonio 281",
            target_class=_target_class(),
            target_date="2026-04-29",
        )

        assert match is None

    def test_ignores_bad_instructor_filter_when_event_has_no_instructor(self) -> None:
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

        match = ReservationService(client).find_target_event(
            club_name="San Antonio 281",
            target_class=_target_class(
                name="Pickleball",
                instructor="Wrong Name",
                start_time="7:00 PM",
                end_time="9:00 PM",
            ),
            target_date="2026-04-29",
        )

        assert match is event


class TestReservationServiceRegistrationDetection:
    def test_returns_none_on_registration_info_404(self) -> None:
        client = MagicMock()
        client.get_registration_info.side_effect = LifetimeAPIError(
            "not found", status_code=404
        )

        result = ReservationService(client).detect_existing_registration(
            "evt", context="preflight"
        )

        assert result is None

    def test_raises_on_registration_info_server_error(self) -> None:
        client = MagicMock()
        client.get_registration_info.side_effect = LifetimeAPIError(
            "server blew up", status_code=500
        )

        with pytest.raises(LifetimeAPIError, match="server blew up"):
            ReservationService(client).detect_existing_registration(
                "evt", context="preflight"
            )


class TestReservationServiceReserveEvent:
    def test_returns_reserved_result(self) -> None:
        client = MagicMock()
        client.get_registration_info.side_effect = LifetimeAPIError(
            "not found", status_code=404
        )
        client.register.return_value = RegistrationResult(
            registration_id=99,
            outcome=RegistrationOutcome.RESERVED,
            raw_status="reserved",
            needs_complete=False,
            required_documents=None,
            raw={},
        )

        result = ReservationService(client).reserve_event("ZXhlcnA6ZXZ0")

        assert result.outcome is RegistrationOutcome.RESERVED
        client.register.assert_called_once_with("ZXhlcnA6ZXZ0")
        client.complete_registration.assert_not_called()

    def test_fetches_required_documents_when_register_omits_them(self) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.side_effect = [
            LifetimeAPIError("not found", status_code=404),
            {"agreement": {"agreementId": 77}},
            {"registeredMembers": [{"id": 110137193, "name": "Tyler"}]},
        ]
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.PENDING_COMPLETION,
            raw_status="pending",
            needs_complete=True,
            required_documents=None,
            raw={},
        )

        result = ReservationService(client).reserve_event("evt")

        assert result.outcome is RegistrationOutcome.RESERVED
        assert result.registration_id == 101
        client.complete_registration.assert_called_once_with(
            101, accepted_documents=[77]
        )

    def test_returns_waitlisted_result_without_completion(self) -> None:
        client = MagicMock()
        client.get_registration_info.side_effect = LifetimeAPIError(
            "not found",
            status_code=404,
        )
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.WAITLISTED,
            raw_status="pending",
            needs_complete=False,
            required_documents=None,
            raw={},
        )

        result = ReservationService(client).reserve_event("evt")

        assert result.outcome is RegistrationOutcome.WAITLISTED
        client.complete_registration.assert_not_called()

    def test_completes_pending_waitlist_flow_with_empty_documents(self) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.side_effect = [
            LifetimeAPIError("not found", status_code=404),
            {
                "registeredMembers": [],
                "unregisteredMembers": [{"id": 110137193, "name": "Tyler"}],
            },
            {
                "registeredMembers": [
                    {
                        "id": 110137193,
                        "name": "Tyler",
                        "spotWaitlist": 13,
                        "cancelCtas": [{"text": "Leave Waitlist"}],
                    }
                ],
                "unregisteredMembers": [],
            },
        ]
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.PENDING_COMPLETION,
            raw_status="pending",
            needs_complete=True,
            required_documents=None,
            raw={"regId": 101, "regStatus": "pending"},
        )

        result = ReservationService(client).reserve_event("evt")

        assert result.outcome is RegistrationOutcome.WAITLISTED
        assert result.registration_id == 101
        client.complete_registration.assert_called_once_with(
            101,
            accepted_documents=[],
        )

    def test_skips_post_when_already_reserved(self) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.return_value = {
            "registeredMembers": [{"id": 110137193, "name": "Tyler"}]
        }

        result = ReservationService(client).reserve_event("evt")

        assert result.outcome is RegistrationOutcome.ALREADY_RESERVED
        client.register.assert_not_called()
        client.complete_registration.assert_not_called()

    def test_treats_duplicate_post_error_as_already_reserved(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.side_effect = [
            {"registeredMembers": []},
            {"registeredMembers": [{"id": 110137193, "name": "Tyler"}]},
        ]
        client.register.side_effect = LifetimeAPIError(
            "POST /event returned 500", status_code=500
        )

        result = ReservationService(client).reserve_event("evt")

        assert result.outcome is RegistrationOutcome.ALREADY_RESERVED
        client.register.assert_called_once_with("evt")
        client.complete_registration.assert_not_called()
        captured = capsys.readouterr().out
        assert "POST /event failed (POST /event returned 500)" in captured

    def test_raises_post_error_when_follow_up_still_not_registered(self) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.side_effect = [
            {"registeredMembers": []},
            {"registeredMembers": []},
        ]
        client.register.side_effect = LifetimeAPIError(
            "POST /event returned 500", status_code=500
        )

        with pytest.raises(LifetimeAPIError, match="POST /event returned 500"):
            ReservationService(client).reserve_event("evt")

    def test_raises_when_required_documents_cannot_be_found(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = MagicMock()
        client.member_id = 110137193
        client.get_registration_info.side_effect = [
            LifetimeAPIError("not found", status_code=404),
            {"registeredMembers": [], "unregisteredMembers": [{"agreementId": 77}]},
            {"registeredMembers": [], "unregisteredMembers": [{"id": 110137193}]},
        ]
        client.register.return_value = RegistrationResult(
            registration_id=101,
            outcome=RegistrationOutcome.PENDING_COMPLETION,
            raw_status="pending",
            needs_complete=True,
            required_documents=None,
            raw={"regId": 101, "regStatus": "pending"},
        )

        with pytest.raises(
            LifetimeAPIError,
            match="did not confirm a reserved or waitlisted outcome",
        ):
            ReservationService(client).reserve_event("evt")

        client.complete_registration.assert_called_once_with(
            101,
            accepted_documents=[],
        )
        captured = capsys.readouterr().out
        assert (
            "Registration info payload lacked recognized waiver/document ids: "
            '{"registeredMembers": [], "unregisteredMembers": [{"agreementId": 77}]}'
        ) in captured
        assert (
            "POST /event completion payload lacked recognized waiver/document ids: "
            '{"regId": 101, "regStatus": "pending"}'
        ) in captured
