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
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        bot = None
        try:
            print(f"Attempt {retry_count + 1}/{max_retries} to reserve class")
            bot = LifetimeReservationBot()
            success = bot.reserve_class()
            if success:
                print("Class reservation completed successfully!")
                return True
        except Exception as e:
            retry_count += 1
            print(f"Attempt {retry_count}/{max_retries} failed with error: {e!s}")

            if bot:
                bot.cleanup()

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
                retry_delay = 30
                print(f"Waiting {retry_delay} seconds before retry {retry_count + 1}/{max_retries}...")
                time.sleep(retry_delay)

    return False


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    run_on_schedule = os.getenv("RUN_ON_SCHEDULE", "false").lower() == "true"

    if not run_on_schedule:
        print("RUN_ON_SCHEDULE is false, running immediately.")
        success = run_bot()
        return 0 if success else 1

    local_time = os.getenv("TARGET_LOCAL_TIME", "10:00:00")
    timezone = os.getenv("TIMEZONE", "America/Chicago")
    target_time = get_target_utc_time(local_time, timezone)
    print(f"Target time: {local_time} {timezone} -> {target_time} UTC")

    wait_until_utc(target_time, run_bot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
