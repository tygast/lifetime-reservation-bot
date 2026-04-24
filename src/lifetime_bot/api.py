"""HTTP client for Life Time's internal API.

The reservation APIs accept Life Time's static APIM key plus per-member auth
headers. The bot now authenticates exclusively through the direct
``auth/v2/login`` member-login API, but the reservation endpoints still
expect the legacy browser-style ``x-ltf-*`` headers on mutating calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests

from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import ClassEvent, RegistrationResult, SessionTokens
from lifetime_bot.parsers import (
    extract_required_document_ids,
    match_class,
    parse_class_events,
    parse_registration_result,
)

SUBSCRIPTION_KEY = "924c03ce573d473793e184219a6a19bd"
API_BASE = "https://api.lifetimefitness.com"
__all__ = [
    "API_BASE",
    "SUBSCRIPTION_KEY",
    "LifetimeAPIClient",
    "match_class",
    "extract_required_document_ids",
]


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
            events.extend(parse_class_events(payload))

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
        return parse_registration_result(payload)

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


def _timestamp() -> str:
    now = datetime.now(tz=timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _short_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"


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


def _response_json(response: requests.Response, context: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise LifetimeAPIError(
            f"{context} returned non-JSON response: {response.text[:300]}",
            status_code=response.status_code,
        ) from exc
