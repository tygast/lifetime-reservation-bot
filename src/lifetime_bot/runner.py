"""Retry-aware execution of reservation attempts."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import requests

from lifetime_bot.bootstrap import create_bot
from lifetime_bot.errors import LifetimeAPIError, ReservationAttemptError
from lifetime_bot.models import RegistrationResult


class ReservationBot(Protocol):
    """Boundary for executing a reservation attempt."""

    def reserve_class(self) -> RegistrationResult: ...

    def build_outcome_notification(
        self, result: RegistrationResult
    ) -> tuple[str, str]: ...

    def build_failure_notification(self, exc: BaseException) -> tuple[str, str]: ...

    def send_notification(self, subject: str, message: str) -> object: ...


BotFactory = Callable[[], ReservationBot]
RESULT_PATH_ENV = "LIFETIME_BOT_RESULT_PATH"
INLINE_NOTIFICATIONS_ENV = "LIFETIME_BOT_INLINE_NOTIFICATIONS"


class RetryableReservationError(RuntimeError):
    """Raised when the bot returns a retryable non-terminal outcome."""


def run_bot(
    *,
    bot_factory: BotFactory = create_bot,
    max_retries: int | None = None,
    retry_delay: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Run the reservation flow with retry handling."""

    max_retries = max_retries or max(1, int(os.getenv("MAX_RETRIES", "3")))
    retry_delay = (
        retry_delay
        if retry_delay is not None
        else float(os.getenv("RETRY_DELAY_SECONDS", "5"))
    )
    retry_count = 0
    started = time.perf_counter()

    while retry_count < max_retries:
        bot = None
        attempt_started = time.perf_counter()
        try:
            print(f"Attempt {retry_count + 1}/{max_retries} to reserve class")
            bot = bot_factory()
            result = bot.reserve_class()
            if result.is_terminal:
                subject, body = bot.build_outcome_notification(result)
                _record_final_result(
                    success=True,
                    subject=subject,
                    body=body,
                    outcome=result.outcome.value,
                )
                _send_notification(bot, subject, body, context="outcome")
                print(
                    f"Attempt {retry_count + 1}/{max_retries} succeeded in "
                    f"{time.perf_counter() - attempt_started:.2f}s"
                )
                print(f"Run completed in {time.perf_counter() - started:.2f}s")
                print(
                    "Class reservation completed with outcome: "
                    f"{result.outcome.value}."
                )
                return True
            raise RetryableReservationError(
                "Reservation attempt returned a non-terminal outcome without raising "
                "an error"
            )
        except Exception as exc:
            retry_count += 1
            print(
                f"Attempt {retry_count}/{max_retries} failed after "
                f"{time.perf_counter() - attempt_started:.2f}s with error: {exc!s}"
            )

            should_retry = retry_count < max_retries and _should_retry(exc)
            if not should_retry:
                subject, body = _build_terminal_failure_notification(
                    bot,
                    exc,
                    max_retries=max_retries,
                )
                _record_final_result(
                    success=False,
                    subject=subject,
                    body=body,
                )
                if bot is not None:
                    _send_notification(bot, subject, body, context="failure")
                break
            print(
                f"Waiting {retry_delay:g} seconds before retry "
                f"{retry_count + 1}/{max_retries}..."
            )
            sleep(retry_delay)

    print(f"Run failed after {time.perf_counter() - started:.2f}s")
    return False


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, ReservationAttemptError):
        return _should_retry(exc.cause)
    if isinstance(exc, RetryableReservationError):
        return True
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, LifetimeAPIError):
        return exc.is_retryable
    return False


def _send_notification(
    bot: ReservationBot, subject: str, body: str, *, context: str
) -> None:
    if not _inline_notifications_enabled():
        print(
            f"Inline notifications disabled; skipping {context} notification send: "
            f"{subject}"
        )
        return
    try:
        bot.send_notification(subject, body)
    except Exception as notify_error:
        print(f"Could not send {context} notification: {notify_error}")


def _build_terminal_failure_notification(
    bot: ReservationBot | None,
    exc: BaseException,
    *,
    max_retries: int,
) -> tuple[str, str]:
    if bot is None:
        return (
            "Lifetime Bot - All Attempts Failed",
            "Failed to reserve class after "
            f"{max_retries} attempts.\n\nError ({type(exc).__name__}): {exc!s}",
        )
    try:
        subject, body = bot.build_failure_notification(exc)
        summary_body = (
            f"Failed to reserve class after {max_retries} attempts.\n\n{body}"
        )
        return ("Lifetime Bot - All Attempts Failed", summary_body)
    except Exception as build_error:
        print(f"Could not build failure notification: {build_error}")
        return (
            "Lifetime Bot - All Attempts Failed",
            "Failed to reserve class after "
            f"{max_retries} attempts.\n\nError ({type(exc).__name__}): {exc!s}",
        )


def _inline_notifications_enabled() -> bool:
    raw_value = os.getenv(INLINE_NOTIFICATIONS_ENV, "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _record_final_result(
    *,
    success: bool,
    subject: str,
    body: str,
    outcome: str | None = None,
) -> None:
    result_path = os.getenv(RESULT_PATH_ENV, "").strip()
    if not result_path:
        return
    payload: dict[str, object] = {
        "success": success,
        "subject": subject,
        "body": body,
    }
    if outcome is not None:
        payload["outcome"] = outcome
    path = Path(result_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote final result payload to {path}.")
