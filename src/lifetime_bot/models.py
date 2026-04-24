"""Core domain models shared across auth, scheduling, and reservation flows."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from lifetime_bot.errors import LifetimeAPIError


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
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * padding))
        except (UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
            raise LifetimeAPIError(
                "x-ltf-profile is not a valid JWT payload"
            ) from exc
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


class RegistrationOutcome(str, Enum):
    """Explicit reservation outcomes used throughout the bot."""

    RESERVED = "reserved"
    WAITLISTED = "waitlisted"
    ALREADY_RESERVED = "already_reserved"
    PENDING_COMPLETION = "pending_completion"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of POST /sys/registrations/V3/ux/event."""

    registration_id: int | None
    outcome: RegistrationOutcome
    raw_status: str
    needs_complete: bool
    raw: dict[str, Any] = field(repr=False)
    required_documents: tuple[int, ...] | None = None

    @property
    def was_waitlisted(self) -> bool:
        return self.outcome is RegistrationOutcome.WAITLISTED

    @property
    def was_already_reserved(self) -> bool:
        return self.outcome is RegistrationOutcome.ALREADY_RESERVED

    @property
    def was_reserved(self) -> bool:
        return self.outcome is RegistrationOutcome.RESERVED

    @property
    def is_terminal(self) -> bool:
        return self.outcome in {
            RegistrationOutcome.RESERVED,
            RegistrationOutcome.ALREADY_RESERVED,
            RegistrationOutcome.WAITLISTED,
        }

    @property
    def display_status(self) -> str:
        return self.raw_status or self.outcome.value

    @classmethod
    def already_reserved(cls, raw: dict[str, Any]) -> RegistrationResult:
        return cls(
            registration_id=None,
            outcome=RegistrationOutcome.ALREADY_RESERVED,
            raw_status="already_reserved",
            needs_complete=False,
            required_documents=None,
            raw=raw,
        )

    def completed(self) -> RegistrationResult:
        return RegistrationResult(
            registration_id=self.registration_id,
            outcome=RegistrationOutcome.RESERVED,
            raw_status="complete",
            needs_complete=False,
            required_documents=self.required_documents,
            raw=self.raw,
        )
