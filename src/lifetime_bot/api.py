"""HTTP client for Life Time's internal API.

The reservation APIs accept Life Time's static APIM key plus per-member auth
headers. The bot now authenticates exclusively through the direct
``auth/v2/login`` member-login API, but the reservation endpoints still
expect the legacy browser-style ``x-ltf-*`` headers on mutating calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import (
    ClassEvent,
    RegistrationOutcome,
    RegistrationResult,
    SessionTokens,
)

SUBSCRIPTION_KEY = "924c03ce573d473793e184219a6a19bd"
API_BASE = "https://api.lifetimefitness.com"

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
            payload = _response_json(
                response,
                f"GET {API_BASE}/ux/web-schedules/v2/schedules/classes",
            )
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
        payload = _response_json(
            response,
            f"GET {API_BASE}/ux/web-schedules/v2/events/{event_id}/registration",
        )
        if not isinstance(payload, dict):
            raise LifetimeAPIError(
                "Registration info response was not an object",
                status_code=response.status_code,
            )
        return payload

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
        payload = _response_json(
            response,
            f"POST {API_BASE}/sys/registrations/V3/ux/event",
        )
        if not isinstance(payload, dict):
            raise LifetimeAPIError(
                "POST /event response was not an object",
                status_code=response.status_code,
            )
        return _parse_registration_result(payload)

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
        payload = _response_json(
            response,
            f"PUT {API_BASE}/sys/registrations/V3/ux/event/{registration_id}/complete",
        )
        if not isinstance(payload, dict):
            raise LifetimeAPIError(
                "PUT /complete response was not an object",
                status_code=response.status_code,
            )
        return payload

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
                f"{response.text[:300]}",
                status_code=response.status_code,
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
    outcome = _classify_registration_outcome(status, needs_complete=needs_complete)
    documents = extract_required_document_ids(payload)
    return RegistrationResult(
        registration_id=reg_id,
        outcome=outcome,
        raw_status=status,
        needs_complete=needs_complete,
        required_documents=tuple(documents) if documents is not None else None,
        raw=payload,
    )


def _response_json(response: requests.Response, context: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise LifetimeAPIError(
            f"{context} returned non-JSON response: {response.text[:300]}",
            status_code=response.status_code,
        ) from exc


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _classify_registration_outcome(
    status: str, *, needs_complete: bool
) -> RegistrationOutcome:
    normalized = status.strip().lower()
    if "wait" in normalized:
        return RegistrationOutcome.WAITLISTED
    if needs_complete:
        return RegistrationOutcome.PENDING_COMPLETION
    if normalized in {"reserved", "confirmed", "registered", "complete"}:
        return RegistrationOutcome.RESERVED
    return RegistrationOutcome.UNKNOWN


def extract_required_document_ids(payload: dict[str, Any]) -> list[int] | None:
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
