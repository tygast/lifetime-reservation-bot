"""CLI entry point for the Lifetime Reservation Bot."""

from __future__ import annotations

import os
import sys

from lifetime_bot.runner import run_bot
from lifetime_bot.utils.timing import get_target_utc_time, wait_until_utc


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    run_on_schedule = os.getenv("RUN_ON_SCHEDULE", "false").lower() == "true"

    if not run_on_schedule:
        print("RUN_ON_SCHEDULE is false, running immediately.")
        success = run_bot()
        return 0 if success else 1

    local_time = os.getenv("TARGET_LOCAL_TIME", "10:00:00")
    timezone = os.getenv("TIMEZONE", "America/Chicago")
    target_time = get_target_utc_time(local_time, timezone)
    print(f"Target time: {local_time} {timezone} -> {target_time} UTC")

    outcome = {"success": False}

    def _scheduled() -> None:
        outcome["success"] = run_bot()

    wait_until_utc(target_time, _scheduled)
    return 0 if outcome["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
