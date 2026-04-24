"""Notification orchestration for reservation outcomes and failures."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from lifetime_bot.config import NotificationMethod
from lifetime_bot.notifications import NotificationService


@dataclass(frozen=True)
class TimedAttemptResult:
    """Outcome of a bounded callback execution."""

    completed: bool
    succeeded: bool
    error: str | None = None


@dataclass(frozen=True)
class NotificationAttempt:
    """One notification channel attempt."""

    channel: str
    completed: bool
    succeeded: bool
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class NotificationDispatchResult:
    """Aggregate result for a notification fan-out."""

    subject: str
    attempts: tuple[NotificationAttempt, ...]


class NotificationCoordinator:
    """Coordinate notification delivery across configured channels."""

    def __init__(
        self,
        *,
        email_service: NotificationService,
        sms_service: NotificationService,
        timeout_seconds: float,
    ) -> None:
        self.email_service = email_service
        self.sms_service = sms_service
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        subject: str,
        message: str,
        *,
        method: NotificationMethod,
    ) -> NotificationDispatchResult:
        print(f"Notification phase started: {subject}")
        attempts: list[NotificationAttempt] = []
        if method in {"email", "both"}:
            attempts.append(
                self._send_via_channel(
                    channel="email",
                    service=self.email_service,
                    subject=subject,
                    message=message,
                )
            )
        if method in {"sms", "both"}:
            attempts.append(
                self._send_via_channel(
                    channel="sms",
                    service=self.sms_service,
                    subject=subject,
                    message=message,
                )
            )
        return NotificationDispatchResult(subject=subject, attempts=tuple(attempts))

    def _send_via_channel(
        self,
        *,
        channel: str,
        service: NotificationService,
        subject: str,
        message: str,
    ) -> NotificationAttempt:
        started = time.perf_counter()
        result = _run_with_timeout(
            lambda: service.send(subject, message),
            timeout_seconds=self.timeout_seconds,
        )
        elapsed = time.perf_counter() - started
        label = channel.upper() if channel == "sms" else channel.title()
        if not result.completed:
            print(
                f"{label} notification timed out after "
                f"{self.timeout_seconds:.2f}s: {subject}"
            )
        elif result.error:
            print(f"{label} notification failed: {result.error}")
        elif result.succeeded:
            print(f"Notification sent via {channel}: {subject}")
        else:
            print(f"{label} notification service reported failure: {subject}")
        print(
            f"{label} notification attempt completed in "
            f"{elapsed:.2f}s."
        )
        return NotificationAttempt(
            channel=channel,
            completed=result.completed,
            succeeded=result.succeeded,
            elapsed_seconds=elapsed,
            error=result.error,
        )


def _run_with_timeout(
    callback: Callable[[], bool], *, timeout_seconds: float
) -> TimedAttemptResult:
    result: dict[str, Any] = {"done": False, "value": False, "error": None}

    def _target() -> None:
        try:
            result["value"] = bool(callback())
        except Exception as exc:  # pragma: no cover - exercised through caller logs
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["value"] = False
        finally:
            result["done"] = True

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if not result["done"]:
        return TimedAttemptResult(completed=False, succeeded=False)
    return TimedAttemptResult(
        completed=True,
        succeeded=bool(result["value"]),
        error=result["error"],
    )
