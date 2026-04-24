"""CLI entry point for the Lifetime Reservation Bot."""

from __future__ import annotations

import os
import sys
import time

from lifetime_bot.bot import LifetimeReservationBot
from lifetime_bot.utils.timing import get_target_utc_time, wait_until_utc


def run_bot() -> bool:
    """Run the bot with retry logic.

    Returns:
        True if reservation was successful, False otherwise.
    """
    max_retries = max(1, int(os.getenv("MAX_RETRIES", "3")))
    retry_delay = float(os.getenv("RETRY_DELAY_SECONDS", "5"))
    retry_count = 0
    started = time.perf_counter()

    while retry_count < max_retries:
        bot = None
        attempt_started = time.perf_counter()
        try:
            print(f"Attempt {retry_count + 1}/{max_retries} to reserve class")
            bot = LifetimeReservationBot()
            if bot.reserve_class():
                print(
                    f"Attempt {retry_count + 1}/{max_retries} succeeded in "
                    f"{time.perf_counter() - attempt_started:.2f}s"
                )
                print(f"Run completed in {time.perf_counter() - started:.2f}s")
                print("Class reservation completed successfully!")
                return True
            raise RuntimeError(
                "Reservation attempt returned False without raising an error"
            )
        except Exception as e:
            retry_count += 1
            print(
                f"Attempt {retry_count}/{max_retries} failed after "
                f"{time.perf_counter() - attempt_started:.2f}s with error: {e!s}"
            )

            if retry_count >= max_retries:
                try:
                    if bot and hasattr(bot, "send_notification"):
                        bot.send_notification(
                            "Lifetime Bot - All Attempts Failed",
                            f"Failed to reserve class after {max_retries} attempts. "
                            f"Last error: {e!s}",
                        )
                except Exception as notify_error:
                    print(f"Could not send failure notification: {notify_error}")
            else:
                print(
                    f"Waiting {retry_delay:g} seconds before retry "
                    f"{retry_count + 1}/{max_retries}..."
                )
                time.sleep(retry_delay)

    print(f"Run failed after {time.perf_counter() - started:.2f}s")
    return False


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
