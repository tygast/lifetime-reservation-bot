"""Unit tests for schedule and registration payload parsers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationOutcome
from lifetime_bot.parsers import (
    extract_required_document_ids,
    match_class,
    parse_class_events,
    parse_registration_result,
)


class TestParseClassEvents:
    def test_parses_nested_schedule_payload(self) -> None:
        payload = {
            "results": [
                {
                    "day": "2026-04-29",
                    "dayParts": [
                        {
                            "startTimes": [
                                {
                                    "time": "7:00 PM",
                                    "activities": [
                                        {
                                            "id": "nested-evt",
                                            "name": "Pickleball Open Play: All Levels",
                                            "location": "Indoor Pickleball Court 3, San Antonio 281",
                                            "endTime": "9:00 PM",
                                            "instructors": [],
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        events = parse_class_events(payload)

        assert len(events) == 1
        event = events[0]
        assert event.event_id == "nested-evt"
        assert event.name == "Pickleball Open Play: All Levels"
        assert event.instructor == ""
        assert event.location == "Indoor Pickleball Court 3, San Antonio 281"
        assert event.start == datetime(2026, 4, 29, 19, 0)
        assert event.end == datetime(2026, 4, 29, 21, 0)


class TestParseRegistrationResult:
    def test_parses_pending_registration_and_documents(self) -> None:
        payload = {
            "regId": 185650661,
            "regStatus": "pending",
            "agreement": {"agreementId": "77"},
        }

        result = parse_registration_result(payload)

        assert result.outcome is RegistrationOutcome.PENDING_COMPLETION
        assert result.raw_status == "pending"
        assert result.required_documents == (77,)

    def test_parses_pending_full_waitlist_registration_as_pending_completion(self) -> None:
        payload = {
            "regId": 186195720,
            "regStatus": "pending",
            "hasWaitlist": True,
            "hasSpots": False,
            "openSpots": 0,
            "totalWaitlisted": 13,
        }

        result = parse_registration_result(payload)

        assert result.outcome is RegistrationOutcome.PENDING_COMPLETION
        assert result.raw_status == "pending"
        assert result.needs_complete is True
        assert result.required_documents is None

    def test_raises_when_response_missing_id(self) -> None:
        with pytest.raises(LifetimeAPIError):
            parse_registration_result({"status": "reserved"})


class TestExtractRequiredDocumentIds:
    def test_extracts_agreement_document_id(self) -> None:
        payload = {"agreement": {"agreementId": "77"}}
        assert extract_required_document_ids(payload) == [77]


class TestMatchClass:
    def _event(
        self,
        *,
        name: str,
        instructor: str,
        start: datetime | None,
        end: datetime | None,
    ) -> ClassEvent:
        return ClassEvent(
            event_id="x",
            name=name,
            instructor=instructor,
            start=start,
            end=end,
            location="San Antonio 281",
            spots_available=5,
            raw={},
        )

    def test_matches_by_name_and_time(self) -> None:
        events = [
            self._event(
                name="Pickleball Open Play: All Levels",
                instructor="Zack W.",
                start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
                end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            )
        ]

        match = match_class(
            events,
            name_contains="Pickleball Open Play",
            instructor_contains="",
            start_time_local="7:00 PM",
            end_time_local="9:00 PM",
            date_iso="2026-04-29",
        )

        assert match is not None

    def test_rejects_on_time_mismatch(self) -> None:
        events = [
            self._event(
                name="Pickleball Open Play: All Levels",
                instructor="",
                start=datetime(2026, 4, 29, 19, 0, tzinfo=timezone.utc),
                end=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc),
            )
        ]

        match = match_class(
            events,
            name_contains="Pickleball",
            start_time_local="8:00 PM",
            end_time_local="9:00 PM",
        )

        assert match is None
