"""Unit tests for reservation workflow services."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from lifetime_bot.config import ClassConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent
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
