"""Timing and scheduling utilities."""

from __future__ import annotations

import datetime
import time
from typing import Callable


def get_target_date(run_on_schedule: bool, target_date: str | None = None) -> str:
    """Calculate target date for class reservation.

    Args:
        run_on_schedule: If True, calculate date 8 days from now.
        target_date: Explicit target date to use if not running on schedule.

    Returns:
        Target date in YYYY-MM-DD format.
    """
    if run_on_schedule:
        return (datetime.datetime.now() + datetime.timedelta(days=8)).strftime("%Y-%m-%d")
    return target_date or datetime.datetime.now().strftime("%Y-%m-%d")


def is_valid_day() -> bool:
    """Check if current day is valid for scheduling.

    Valid days are: Monday (0), Tuesday (1), Wednesday (2), Thursday (3), Sunday (6).

    Returns:
        True if today is a valid scheduling day.
    """
    return datetime.datetime.today().weekday() in [0, 1, 2, 3, 6]


def wait_until_utc(target_utc_time: str, callback: Callable[[], None]) -> None:
    """Wait until the given target UTC time, then execute the callback.

    If the current time is already past the target, executes immediately.

    Args:
        target_utc_time: The UTC time to wait until (e.g., "16:00:00").
        callback: Function to call when the target time is reached.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    target = datetime.datetime.strptime(target_utc_time, "%H:%M:%S").time()
    target_datetime = datetime.datetime.combine(now.date(), target).replace(
        tzinfo=datetime.timezone.utc
    )

    if now >= target_datetime:
        print(
            f"Current time ({now.strftime('%H:%M:%S')} UTC) is past {target_utc_time}, "
            "running immediately."
        )
        callback()
        return

    sleep_seconds = (target_datetime - now).total_seconds()
    print(f"Sleeping for {sleep_seconds:.2f} seconds...")
    time.sleep(sleep_seconds)

    print(f"Reached target UTC time: {target_datetime.strftime('%H:%M:%S')} UTC")
    callback()
