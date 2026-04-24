"""Unit tests for the Life Time API client."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from lifetime_bot.api import (
    API_BASE,
    SUBSCRIPTION_KEY,
    ClassEvent,
    LifetimeAPIClient,
    LifetimeAPIError,
    SessionTokens,
    match_class,
)


def _make_profile_jwt(member_id: int) -> str:
    """Build a JWS-looking x-ltf-profile value with the given memberId."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    claims = json.dumps({"memberId": member_id, "partyId": 1})
    payload = base64.urlsafe_b64encode(claims.encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.not-a-real-signature"


SAMPLE_TOKENS = SessionTokens(
    jwe="jwe-blob",
    profile=_make_profile_jwt(110137193),
    ssoid="C_abc123",
)


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: object | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)
        self.ok = 200 <= status_code < 400
        self.headers = headers or {}

    def json(self) -> object:
        return self._payload


def _client_with_mock(response: _FakeResponse) -> tuple[LifetimeAPIClient, MagicMock]:
    session = MagicMock(spec=requests.Session)
    session.headers = requests.structures.CaseInsensitiveDict()
    session.request.return_value = response
    return LifetimeAPIClient(SAMPLE_TOKENS, session=session), session.request


class TestSessionTokens:
    def test_member_id_decoded_from_profile(self) -> None:
        assert SAMPLE_TOKENS.member_id == 110137193

    def test_member_id_uses_override_when_profile_missing(self) -> None:
        tokens = SessionTokens(
            jwe="jwe-blob",
            profile="",
            ssoid="C_abc123",
            member_id_override=110137193,
        )
        assert tokens.member_id == 110137193

    def test_member_id_raises_on_malformed_profile(self) -> None:
        bad = SessionTokens(jwe="x", profile="not-a-jwt", ssoid="y")
        with pytest.raises(LifetimeAPIError):
            _ = bad.member_id

    def test_member_id_raises_when_claim_missing(self) -> None:
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"not_a_member_id":1}').rstrip(b"=").decode()
        bad = SessionTokens(jwe="x", profile=f"{header}.{payload}.sig", ssoid="y")
        with pytest.raises(LifetimeAPIError):
            _ = bad.member_id


class TestClientHeaders:
    def test_session_headers_include_all_auth_fields(self) -> None:
        client, _ = _client_with_mock(_FakeResponse(payload={"results": []}))
        headers = client.session.headers
        assert headers["ocp-apim-subscription-key"] == SUBSCRIPTION_KEY
        assert headers["authorization"] == "jwe-blob"
        assert headers["x-ltf-jwe"] == "jwe-blob"
        assert headers["x-ltf-profile"] == SAMPLE_TOKENS.profile
        assert headers["x-ltf-ssoid"] == "C_abc123"
        assert headers["origin"] == "https://my.lifetime.life"

    def test_profile_header_is_omitted_when_unavailable(self) -> None:
        tokens = SessionTokens(
            jwe="jwe-blob",
            profile="",
            ssoid="C_abc123",
            member_id_override=110137193,
        )
        session = MagicMock(spec=requests.Session)
        session.headers = requests.structures.CaseInsensitiveDict()
        LifetimeAPIClient(tokens, session=session)

        headers = session.headers
        assert headers["x-ltf-ct"] == "jwe-blob"
        assert headers["x-ltf-jwe"] == "jwe-blob"
        assert headers["x-ltf-ssoid"] == "C_abc123"
        assert "authorization" not in headers
        assert "x-ltf-profile" not in headers

    def test_direct_auth_sessions_use_browser_style_x_ltf_headers(self) -> None:
        tokens = SessionTokens(
            jwe="direct-token",
            profile="profile-jwt",
            ssoid="direct-sso",
            member_id_override=110137193,
        )
        session = MagicMock(spec=requests.Session)
        session.headers = requests.structures.CaseInsensitiveDict()
        LifetimeAPIClient(tokens, session=session)

        headers = session.headers
        assert headers["x-ltf-ct"] == "direct-token"
        assert headers["x-ltf-jwe"] == "direct-token"
        assert headers["x-ltf-profile"] == "profile-jwt"
        assert headers["x-ltf-ssoid"] == "direct-sso"
        assert "authorization" not in headers


class TestListClasses:
    def test_builds_correct_request(self) -> None:
        client, request_mock = _client_with_mock(_FakeResponse(payload={"results": []}))
        client.list_classes(
            location="San Antonio 281",
            start=datetime(2026, 4, 23),
            end=datetime(2026, 4, 30),
            interests=["Pickleball Open Play"],
        )

        method, url = request_mock.call_args.args
        params = request_mock.call_args.kwargs["params"]
        headers = request_mock.call_args.kwargs["headers"]

        assert method == "GET"
        assert url == f"{API_BASE}/ux/web-schedules/v2/schedules/classes"
        assert ("start", "4/23/2026") in params
        assert ("end", "4/30/2026") in params
        assert ("locations", "San Antonio 281") in params
        assert ("pageSize", "750") in params
        assert ("tags", "interest:Pickleball Open Play") in params
        assert "x-timestamp" in headers

    def test_parses_class_event(self) -> None:
        payload = {
            "results": [
                {
                    "id": "ZXhlcnA6aWQx",
                    "name": "Pickleball Open Play: All Levels",
                    "start": "2026-04-29T19:00:00-05:00",
                    "end": "2026-04-29T21:00:00-05:00",
                    "leader": {"name": {"displayname": "Zack W."}},
                    "location": {"name": "San Antonio 281"},
                    "spots": {"available": 6},
                }
            ]
        }
        client, _ = _client_with_mock(_FakeResponse(payload=payload))
        events = client.list_classes(
            location="San Antonio 281",
            start=datetime(2026, 4, 23),
            end=datetime(2026, 4, 30),
        )
        assert len(events) == 1
        event = events[0]
        assert event.event_id == "ZXhlcnA6aWQx"
        assert event.name == "Pickleball Open Play: All Levels"
        assert event.instructor == "Zack W."
        assert event.location == "San Antonio 281"
        assert event.spots_available == 6
        assert event.start is not None and event.start.hour == 19
        assert event.end is not None and event.end.hour == 21

    def test_parses_nested_schedule_payload(self) -> None:
        payload = {
            "results": [
                {
                    "day": "2026-04-29",
                    "dayParts": [
                        {
                            "name": "Evening",
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
                            ],
                        }
                    ],
                }
            ]
        }
        client, _ = _client_with_mock(_FakeResponse(payload=payload))

        events = client.list_classes(
            location="San Antonio 281",
            start=datetime(2026, 4, 26),
            end=datetime(2026, 5, 3),
        )

        assert len(events) == 1
        event = events[0]
        assert event.event_id == "nested-evt"
        assert event.name == "Pickleball Open Play: All Levels"
        assert event.instructor == ""
        assert event.location == "Indoor Pickleball Court 3, San Antonio 281"
        assert event.start == datetime(2026, 4, 29, 19, 0)
        assert event.end == datetime(2026, 4, 29, 21, 0)

    def test_handles_flat_list_payload(self) -> None:
        payload = [
            {
                "eventId": "abc",
                "displayName": "GTX",
                "startDate": "2026-04-30T08:00:00",
                "endDate": "2026-04-30T09:00:00",
                "location": "San Antonio 281",
            }
        ]
        client, _ = _client_with_mock(_FakeResponse(payload=payload))
        events = client.list_classes(
            location="San Antonio 281",
            start=datetime(2026, 4, 23),
            end=datetime(2026, 4, 30),
        )
        assert len(events) == 1
        assert events[0].event_id == "abc"
        assert events[0].name == "GTX"

    def test_follows_pagination(self) -> None:
        page_one = _FakeResponse(
            payload={
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
                                                "id": "page-1",
                                                "name": "Pickleball Open Play: All Levels",
                                                "location": "Court 3, San Antonio 281",
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
            },
            headers={"x-pagination": json.dumps({"pages": 2})},
        )
        page_two = _FakeResponse(
            payload={
                "results": [
                    {
                        "day": "2026-04-30",
                        "dayParts": [
                            {
                                "startTimes": [
                                    {
                                        "time": "8:00 AM",
                                        "activities": [
                                            {
                                                "id": "page-2",
                                                "name": "GTX",
                                                "location": "Studio, San Antonio 281",
                                                "endTime": "9:00 AM",
                                                "instructors": [{"name": "Coach"}],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
            headers={"x-pagination": json.dumps({"pages": 2})},
        )
        session = MagicMock(spec=requests.Session)
        session.headers = requests.structures.CaseInsensitiveDict()
        session.request.side_effect = [page_one, page_two]
        client = LifetimeAPIClient(SAMPLE_TOKENS, session=session)

        events = client.list_classes(
            location="San Antonio 281",
            start=datetime(2026, 4, 26),
            end=datetime(2026, 5, 3),
        )

        assert len(events) == 2
        assert [event.event_id for event in events] == ["page-1", "page-2"]
        assert session.request.call_count == 2

    def test_raises_on_http_error(self) -> None:
        client, _ = _client_with_mock(
            _FakeResponse(status_code=401, payload={"error": "unauthorized"}, text="unauthorized")
        )
        with pytest.raises(LifetimeAPIError) as exc:
            client.list_classes(
                location="San Antonio 281",
                start=datetime(2026, 4, 23),
                end=datetime(2026, 4, 30),
            )
        assert "401" in str(exc.value)


class TestRegister:
    def test_posts_event_and_member_id(self) -> None:
        payload = {"regId": 185592233, "status": "reserved", "requiresComplete": True}
        client, request_mock = _client_with_mock(_FakeResponse(payload=payload))

        result = client.register("ZXhlcnA6ZXZlbnQ=")

        method, url = request_mock.call_args.args
        body = request_mock.call_args.kwargs["json"]
        assert method == "POST"
        assert url == f"{API_BASE}/sys/registrations/V3/ux/event"
        assert body == {"eventId": "ZXhlcnA6ZXZlbnQ=", "memberId": [110137193]}
        assert result.registration_id == 185592233
        assert result.was_reserved is True
        assert result.was_waitlisted is False
        assert result.needs_complete is True

    def test_identifies_waitlist_status(self) -> None:
        payload = {"id": 42, "status": "waitlisted"}
        client, _ = _client_with_mock(_FakeResponse(payload=payload))
        result = client.register("evt")
        assert result.was_waitlisted is True
        assert result.was_reserved is False

    def test_parses_reg_status_and_agreement_documents(self) -> None:
        payload = {
            "regId": 185650661,
            "regStatus": "pending",
            "agreement": {"agreementId": "77"},
        }
        client, _ = _client_with_mock(_FakeResponse(payload=payload))

        result = client.register("evt")

        assert result.status == "pending"
        assert result.needs_complete is True
        assert result.required_documents == [77]

    def test_raises_when_response_missing_id(self) -> None:
        client, _ = _client_with_mock(_FakeResponse(payload={"status": "reserved"}))
        with pytest.raises(LifetimeAPIError):
            client.register("evt")


class TestCompleteRegistration:
    def test_sends_accepted_documents(self) -> None:
        client, request_mock = _client_with_mock(_FakeResponse(payload={"status": "complete"}))
        client.complete_registration(185592233, accepted_documents=[77])

        method, url = request_mock.call_args.args
        body = request_mock.call_args.kwargs["json"]
        assert method == "PUT"
        assert url == f"{API_BASE}/sys/registrations/V3/ux/event/185592233/complete"
        assert body == {"memberId": [110137193], "acceptedDocuments": [77]}

    def test_defaults_to_empty_documents_and_derived_member_id(self) -> None:
        client, request_mock = _client_with_mock(_FakeResponse(payload={"status": "complete"}))
        client.complete_registration(42)
        assert request_mock.call_args.kwargs["json"] == {
            "memberId": [110137193],
            "acceptedDocuments": [],
        }


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

    def test_name_and_instructor_are_case_insensitive_substrings(self) -> None:
        events = [
            self._event(
                name="ALPHA STRENGTH: SQUAT + PULL",
                instructor="Zack W.",
                start=datetime(2026, 5, 1, 8, 0),
                end=datetime(2026, 5, 1, 9, 0),
            )
        ]
        match = match_class(
            events,
            name_contains="alpha",
            instructor_contains="zack",
        )
        assert match is not None
