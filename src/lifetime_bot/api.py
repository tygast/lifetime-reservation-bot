"""HTTP client for Life Time Fitness's internal API.

The reservation APIs accept Life Time's static APIM key plus per-member auth
headers. Those auth values can come from either:
    - the browser SPA after Azure B2C login, or
    - the direct ``auth/v2/login`` member-login API.

The client adapts its auth headers to the bootstrap path:
    - browser sessions keep the legacy ``x-ltf-*`` headers
    - direct member-login sessions also use the browser-style ``x-ltf-*``
      headers because ``/sys/registrations`` rejects ``Authorization`` on
      some event flows even when the same token is otherwise valid
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

SUBSCRIPTION_KEY = "924c03ce573d473793e184219a6a19bd"
API_BASE = "https://api.lifetimefitness.com"


class LifetimeAPIError(Exception):
    """Raised when a Life Time API call returns an unexpected response."""


@dataclass(frozen=True)
class SessionTokens:
    """Credentials minted by Life Time's auth flow."""

    jwe: str
    profile: str
    ssoid: str
    member_id_override: int | None = None

    @property
    def is_direct_auth(self) -> bool:
        return self.member_id_override is not None

    @property
    def member_id(self) -> int:
        if self.member_id_override is not None:
            return self.member_id_override
        if not self.profile:
            raise LifetimeAPIError(
                "No member id was available in the current session tokens"
            )
        try:
            _, payload, _ = self.profile.split(".")
        except ValueError as exc:
            raise LifetimeAPIError(
                "x-ltf-profile is not a valid JWT (expected 3 dot-separated segments)"
            ) from exc

        padding = (-len(payload)) % 4
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * padding))
        if "memberId" not in claims:
            raise LifetimeAPIError("x-ltf-profile claims did not include memberId")
        return int(claims["memberId"])


@dataclass(frozen=True)
class ClassEvent:
    """A single class instance returned by the schedules API."""

    event_id: str
    name: str
    instructor: str
    start: datetime | None
    end: datetime | None
    location: str
    spots_available: int | None
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of POST /sys/registrations/V3/ux/event.

    ``status`` values observed so far: "reserved", "waitlisted", "pending".
    ``needs_complete`` means the caller should PUT .../complete to finalize.
    """

    registration_id: int
    status: str
    needs_complete: bool
    required_documents: list[int] | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def was_waitlisted(self) -> bool:
        return "wait" in self.status.lower()

    @property
    def was_already_reserved(self) -> bool:
        return self.status.lower().replace(" ", "_") == "already_reserved"

    @property
    def was_reserved(self) -> bool:
        return self.status.lower() in {"reserved", "confirmed", "registered", "complete"}


class LifetimeAPIClient:
    """Thin wrapper around the Life Time reservation endpoints."""

    def __init__(
        self,
        tokens: SessionTokens,
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.tokens = tokens
        self.timeout = timeout
        self._member_id: int | None = None
        self.session = session or requests.Session()
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "origin": "https://my.lifetime.life",
            "referer": "https://my.lifetime.life/",
        }
        if tokens.is_direct_auth:
            headers["X-LTF-CT"] = tokens.jwe
            headers["X-LTF-JWE"] = tokens.jwe
            if tokens.profile:
                headers["X-LTF-PROFILE"] = tokens.profile
            if tokens.ssoid:
                headers["X-LTF-SSOID"] = tokens.ssoid
        else:
            headers["Authorization"] = tokens.jwe
            headers["X-LTF-JWE"] = tokens.jwe
            if tokens.profile:
                headers["X-LTF-PROFILE"] = tokens.profile
            if tokens.ssoid:
                headers["X-LTF-SSOID"] = tokens.ssoid
        self.session.headers.update(headers)

    @property
    def member_id(self) -> int:
        if self._member_id is None:
            self._member_id = self.tokens.member_id
        return self._member_id

    def list_classes(
        self,
        *,
        location: str,
        start: datetime,
        end: datetime,
        interests: list[str] | None = None,
    ) -> list[ClassEvent]:
        """Fetch classes at ``location`` between ``start`` and ``end`` (inclusive).

        ``start``/``end`` are passed as m/d/YYYY — the SPA uses the same format.
        ``interests`` filter to specific class categories (e.g. ``["Pickleball Open Play"]``);
        omit to return every class.
        """
        base_params: list[tuple[str, str]] = [
            ("start", _short_date(start)),
            ("end", _short_date(end)),
            ("locations", location),
            ("isFree", "false"),
        ]
        for interest in interests or []:
            base_params.append(("tags", f"interest:{interest}"))

        events: list[ClassEvent] = []
        page = 1
        while True:
            params = [*base_params, ("page", str(page)), ("pageSize", "750")]
            response = self._request(
                "GET",
                f"{API_BASE}/ux/web-schedules/v2/schedules/classes",
                params=params,
            )
            payload = response.json()
            events.extend(_parse_class_events(payload))

            if page >= _extract_total_pages(response):
                return events
            page += 1

    def get_registration_info(self, event_id: str) -> dict[str, Any]:
        """GET /events/{eventId}/registration — spot counts, required waivers, etc."""
        response = self._request(
            "GET",
            f"{API_BASE}/ux/web-schedules/v2/events/{event_id}/registration",
        )
        return response.json()

    def register(
        self,
        event_id: str,
        *,
        member_ids: list[int] | None = None,
    ) -> RegistrationResult:
        """POST /sys/registrations/V3/ux/event. Reserves or waitlists depending on capacity."""
        body = {
            "eventId": event_id,
            "memberId": list(member_ids or [self.member_id]),
        }
        response = self._request(
            "POST",
            f"{API_BASE}/sys/registrations/V3/ux/event",
            json=body,
        )
        return _parse_registration_result(response.json())

    def complete_registration(
        self,
        registration_id: int,
        *,
        accepted_documents: list[int] | None = None,
        member_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """PUT /sys/registrations/V3/ux/event/{id}/complete — finalizes a pending reservation."""
        body = {
            "memberId": list(member_ids or [self.member_id]),
            "acceptedDocuments": list(accepted_documents or []),
        }
        response = self._request(
            "PUT",
            f"{API_BASE}/sys/registrations/V3/ux/event/{registration_id}/complete",
            json=body,
        )
        if not response.text.strip():
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def cancel_registration(self, registration_id: int) -> None:
        """DELETE a registration. Useful for CI cleanup after smoke tests."""
        self._request(
            "DELETE",
            f"{API_BASE}/sys/registrations/V3/ux/event/{registration_id}",
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("x-timestamp", _timestamp())
        response = self.session.request(
            method, url, headers=headers, timeout=self.timeout, **kwargs
        )
        if not response.ok:
            raise LifetimeAPIError(
                f"{method} {url} returned {response.status_code}: "
                f"{response.text[:300]}"
            )
        return response


def match_class(
    classes: list[ClassEvent],
    *,
    name_contains: str,
    instructor_contains: str = "",
    start_time_local: str | None = None,
    end_time_local: str | None = None,
    date_iso: str | None = None,
) -> ClassEvent | None:
    """Find the first ClassEvent matching all provided criteria.

    Matching rules mirror the pre-rewrite scraping logic so existing .env
    values keep working: class name and instructor are case-insensitive
    substring matches; start/end times compare the rendered "h:MM AM/PM"
    string against the parsed datetime; date is an exact ISO date match.
    """
    name_key = name_contains.strip().lower()
    instructor_key = instructor_contains.strip().lower()
    for event in classes:
        if name_key and name_key not in event.name.lower():
            continue
        if instructor_key and instructor_key not in event.instructor.lower():
            continue
        if date_iso and (event.start is None or event.start.date().isoformat() != date_iso):
            continue
        if start_time_local and _format_time(event.start) != start_time_local.strip():
            continue
        if end_time_local and _format_time(event.end) != end_time_local.strip():
            continue
        return event
    return None


def _timestamp() -> str:
    now = datetime.now(tz=timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _short_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"


def _format_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {suffix}"


def _extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "items", "classes", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _parse_class_events(payload: Any) -> list[ClassEvent]:
    schedule_activities = _extract_schedule_activities(payload)
    if schedule_activities:
        return [_parse_class_event(item) for item in schedule_activities]
    return [_parse_class_event(item) for item in _extract_list(payload)]


def _parse_class_event(item: dict[str, Any]) -> ClassEvent:
    return ClassEvent(
        event_id=str(item.get("id") or item.get("eventId") or ""),
        name=_first_str(item, "name", "displayName", "title") or "",
        instructor=_extract_instructor(item),
        start=_parse_datetime(_first_str(item, "start", "startDate", "startTime")),
        end=_parse_datetime(_first_str(item, "end", "endDate", "endTime")),
        location=_extract_location(item),
        spots_available=_extract_spots(item),
        raw=item,
    )


def _first_str(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_instructor(item: dict[str, Any]) -> str:
    instructors = item.get("instructors")
    if isinstance(instructors, list):
        names = [
            str(instructor.get("name") or "").strip()
            for instructor in instructors
            if isinstance(instructor, dict)
        ]
        names = [name for name in names if name]
        if names:
            return ", ".join(names)
    leader = item.get("leader")
    if isinstance(leader, dict):
        name = leader.get("name")
        if isinstance(name, dict):
            return name.get("displayname") or name.get("displayName") or ""
        if isinstance(name, str):
            return name
    instructor = item.get("instructor")
    if isinstance(instructor, str):
        return instructor
    if isinstance(instructor, dict):
        return instructor.get("displayName") or instructor.get("name") or ""
    return ""


def _extract_location(item: dict[str, Any]) -> str:
    loc = item.get("location")
    if isinstance(loc, dict):
        return loc.get("name") or loc.get("displayName") or ""
    if isinstance(loc, str):
        return loc
    return ""


def _extract_spots(item: dict[str, Any]) -> int | None:
    spots = item.get("spots") or item.get("spotsAvailable")
    if isinstance(spots, int):
        return spots
    if isinstance(spots, dict):
        available = spots.get("available")
        if isinstance(available, int):
            return available
    return None


def _extract_schedule_activities(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    activities: list[dict[str, Any]] = []
    for day in results:
        if not isinstance(day, dict):
            continue
        date_iso = day.get("day")
        if not isinstance(date_iso, str):
            continue
        for day_part in day.get("dayParts") or []:
            if not isinstance(day_part, dict):
                continue
            for start_time in day_part.get("startTimes") or []:
                if not isinstance(start_time, dict):
                    continue
                start = _combine_schedule_datetime(date_iso, start_time.get("time"))
                for activity in start_time.get("activities") or []:
                    if not isinstance(activity, dict):
                        continue
                    flattened = dict(activity)
                    if start is not None:
                        flattened.setdefault("start", start.isoformat())
                    end = _combine_schedule_datetime(date_iso, activity.get("endTime"))
                    if start is not None and end is not None and end <= start:
                        end += timedelta(days=1)
                    if end is not None:
                        flattened.setdefault("end", end.isoformat())
                    activities.append(flattened)
    return activities


def _combine_schedule_datetime(date_iso: str, time_value: Any) -> datetime | None:
    if not isinstance(time_value, str) or not time_value.strip():
        return None
    try:
        return datetime.strptime(
            f"{date_iso} {time_value.strip()}",
            "%Y-%m-%d %I:%M %p",
        )
    except ValueError:
        return None


def _extract_total_pages(response: requests.Response) -> int:
    raw = response.headers.get("x-pagination")
    if not raw:
        return 1
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return 1
    pages = payload.get("pages")
    if isinstance(pages, int) and pages > 0:
        return pages
    return 1


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_registration_result(payload: dict[str, Any]) -> RegistrationResult:
    reg_id = _first_int(payload, "regId", "id", "registrationId", "registration_id")
    if reg_id is None:
        raise LifetimeAPIError(
            f"POST /event response missing registration id: {payload!r}"
        )
    status = str(
        payload.get("status") or payload.get("regStatus") or payload.get("type") or ""
    ).lower()
    needs_complete = bool(payload.get("requiresComplete")) or status in {
        "pending",
        "incomplete",
        "",
    }
    return RegistrationResult(
        registration_id=reg_id,
        status=status,
        needs_complete=needs_complete,
        required_documents=_extract_required_documents(payload),
        raw=payload,
    )


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _extract_required_documents(payload: dict[str, Any]) -> list[int] | None:
    for key in ("requiredDocuments", "documents", "acceptedDocuments"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        ids: list[int] = []
        for doc in value:
            if isinstance(doc, int):
                ids.append(doc)
            elif isinstance(doc, dict):
                doc_id = doc.get("id")
                if isinstance(doc_id, int):
                    ids.append(doc_id)
        if ids:
            return ids
    agreement = payload.get("agreement")
    if isinstance(agreement, dict):
        agreement_id = agreement.get("agreementId")
        if isinstance(agreement_id, int):
            return [agreement_id]
        if isinstance(agreement_id, str) and agreement_id.isdigit():
            return [int(agreement_id)]
    return None
