"""Reservation workflow services."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from lifetime_bot.api import LifetimeAPIClient
from lifetime_bot.config import ClassConfig
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationOutcome, RegistrationResult
from lifetime_bot.parsers import extract_required_document_ids, match_class


class ReservationService:
    """Encapsulates class lookup and reservation completion behavior."""

    def __init__(self, client: LifetimeAPIClient) -> None:
        self.client = client

    def find_target_event(
        self, *, club_name: str, target_class: ClassConfig, target_date: str
    ) -> ClassEvent | None:
        try:
            day = datetime.fromisoformat(target_date)
        except ValueError as exc:
            raise LifetimeAPIError(
                f"TARGET_DATE must be YYYY-MM-DD, got {target_date!r}"
            ) from exc

        week_start = day - timedelta(days=(day.weekday() + 1) % 7)
        week_end = week_start + timedelta(days=7)
        classes = self.client.list_classes(
            location=club_name,
            start=week_start,
            end=week_end,
        )
        print(f"Schedule API returned {len(classes)} classes for {target_date}.")
        match = match_class(
            classes,
            name_contains=target_class.name,
            instructor_contains=target_class.instructor,
            start_time_local=target_class.start_time,
            end_time_local=target_class.end_time,
            date_iso=target_date,
        )
        if match is not None or not target_class.instructor:
            return match

        fallback = match_class(
            classes,
            name_contains=target_class.name,
            instructor_contains="",
            start_time_local=target_class.start_time,
            end_time_local=target_class.end_time,
            date_iso=target_date,
        )
        if fallback is not None and not fallback.instructor.strip():
            print(
                "Matched a class with no listed instructor; "
                f"ignoring configured instructor filter {target_class.instructor!r}."
            )
            return fallback
        return None

    def reserve_event(self, event_id: str) -> RegistrationResult:
        result = self.detect_existing_registration(event_id, context="preflight")
        if result is None:
            try:
                result = self.client.register(event_id)
                print(
                    f"POST /event → registrationId={result.registration_id} "
                    f"status={result.display_status} "
                    f"needs_complete={result.needs_complete}"
                )
            except LifetimeAPIError as exc:
                print(
                    f"POST /event failed ({exc}); "
                    "checking registration info before treating it as fatal."
                )
                if exc.status_code not in {409, 500}:
                    raise
                result = self.detect_existing_registration(
                    event_id, context="post-error check"
                )
                if result is None:
                    raise exc
                print(
                    "POST /event returned an already-booked style error, "
                    "and follow-up registration info shows the class is already reserved."
                )

        if result.needs_complete:
            documents = result.required_documents
            if documents is None:
                documents = self.fetch_required_documents(event_id)
            if documents is None:
                raise LifetimeAPIError(
                    "Registration requires completion, but no waiver/document ids "
                    "were available."
                )
            accepted_documents = list(documents)
            self.client.complete_registration(
                result.registration_id,
                accepted_documents=accepted_documents,
            )
            result = result.completed()
            print(
                f"PUT /complete succeeded "
                f"(accepted documents: {accepted_documents})."
            )
        if result.outcome is RegistrationOutcome.UNKNOWN:
            raise LifetimeAPIError(
                "Reservation API returned an unknown terminal status: "
                f"{result.display_status or '<empty>'}"
            )
        return result

    def fetch_required_documents(self, event_id: str) -> list[int] | None:
        try:
            info = self.client.get_registration_info(event_id)
        except LifetimeAPIError as exc:
            print(f"Could not fetch registration info for required docs: {exc}")
            return None
        return extract_required_document_ids(info)

    def detect_existing_registration(
        self, event_id: str, *, context: str
    ) -> RegistrationResult | None:
        try:
            info = self.client.get_registration_info(event_id)
        except LifetimeAPIError as exc:
            print(f"Could not fetch registration info during {context}: {exc}")
            if exc.status_code == 404:
                return None
            raise

        registered = info.get("registeredMembers")
        unregistered = info.get("unregisteredMembers")
        register_cta = "yes" if info.get("registerCta") else "no"
        if isinstance(registered, list) or isinstance(unregistered, list):
            print(
                f"Registration info ({context}): "
                f"registered={len(registered) if isinstance(registered, list) else 0} "
                f"unregistered={len(unregistered) if isinstance(unregistered, list) else 0} "
                f"registerCta={register_cta}"
            )

        member = _find_registered_member(info, self.client.member_id)
        if member is None:
            return None

        member_name = str(member.get("name") or "Current member")
        print(
            f"Registration info ({context}) shows {member_name} "
            f"({self.client.member_id}) is already reserved for event {event_id}."
        )
        return RegistrationResult.already_reserved(info)


def _find_registered_member(
    info: dict[str, Any], member_id: int
) -> dict[str, Any] | None:
    registered = info.get("registeredMembers")
    if not isinstance(registered, list):
        return None

    for member in registered:
        if not isinstance(member, dict):
            continue
        current_id = member.get("id")
        try:
            if current_id is not None and int(current_id) == member_id:
                return member
        except (TypeError, ValueError):
            continue
    return None
