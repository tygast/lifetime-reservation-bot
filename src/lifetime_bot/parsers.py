"""Payload parsing and matching for Life Time schedule and registration data."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationOutcome, RegistrationResult


def match_class(
    classes: list[ClassEvent],
    *,
    name_contains: str,
    instructor_contains: str = "",
    start_time_local: str | None = None,
    end_time_local: str | None = None,
    date_iso: str | None = None,
) -> ClassEvent | None:
    """Find the first ClassEvent matching all provided criteria."""

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


def parse_class_events(payload: Any) -> list[ClassEvent]:
    schedule_activities = _extract_schedule_activities(payload)
    if schedule_activities:
        return [_parse_class_event(item) for item in schedule_activities]
    return [_parse_class_event(item) for item in _extract_list(payload)]


def parse_registration_result(payload: dict[str, Any]) -> RegistrationResult:
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
