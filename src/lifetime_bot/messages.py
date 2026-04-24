"""User-facing message formatting for reservation outcomes and failures."""

from __future__ import annotations

from lifetime_bot.config import BotConfig
from lifetime_bot.models import RegistrationResult


def format_class_details(config: BotConfig, target_date: str) -> str:
    tc = config.target_class
    instructor = tc.instructor or "(ignored)"
    return (
        f"Class: {tc.name}\n"
        f"Instructor: {instructor}\n"
        f"Date: {target_date}\n"
        f"Time: {tc.start_time} - {tc.end_time}\n"
        f"Club: {config.club.name}"
    )


def describe_outcome(
    result: RegistrationResult, class_details: str
) -> tuple[str, str]:
    if result.was_already_reserved:
        return (
            "Lifetime Bot - Already Reserved",
            "This class was already on your account, so no new reservation "
            f"was submitted.\n\n{class_details}",
        )
    if result.was_waitlisted:
        return (
            "Lifetime Bot - Added to Waitlist",
            f"The class was full — you were added to the waitlist.\n\n{class_details}",
        )
    if result.was_reserved:
        return (
            "Lifetime Bot - Reserved",
            f"Your class was successfully reserved!\n\n{class_details}",
        )
    status = result.display_status
    return (
        f"Lifetime Bot - Registered ({status})",
        f"Registration completed (status: {status}).\n\n{class_details}",
    )


def describe_failure(
    exc: BaseException,
    *,
    class_details: str,
    phase: str,
) -> tuple[str, str]:
    error_type = type(exc).__name__
    subject = (
        "Lifetime Bot - Login Failed"
        if phase == "login"
        else "Lifetime Bot - Failure"
    )
    body = (
        f"{phase.title()} failed:\n\n{class_details}\n\n"
        f"Error ({error_type}): {exc!s}"
    )
    return subject, body
