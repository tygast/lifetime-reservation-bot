"""Retry-aware execution of reservation attempts."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Protocol

import requests

from lifetime_bot.bootstrap import create_bot
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import RegistrationResult


class ReservationBot(Protocol):
    """Boundary for executing a reservation attempt."""

    def reserve_class(self) -> RegistrationResult: ...

    def send_notification(self, subject: str, message: str) -> object: ...


BotFactory = Callable[[], ReservationBot]


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
                try:
                    if bot and hasattr(bot, "send_notification"):
                        bot.send_notification(
                            "Lifetime Bot - All Attempts Failed",
                            f"Failed to reserve class after {max_retries} attempts. "
                            f"Last error: {exc!s}",
                        )
                except Exception as notify_error:
                    print(f"Could not send failure notification: {notify_error}")
                break
            print(
                f"Waiting {retry_delay:g} seconds before retry "
                f"{retry_count + 1}/{max_retries}..."
            )
            sleep(retry_delay)

    print(f"Run failed after {time.perf_counter() - started:.2f}s")
    return False


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, RetryableReservationError):
        return True
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, LifetimeAPIError):
        return exc.is_retryable
    return False
