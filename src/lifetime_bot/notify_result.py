"""CLI entrypoint for sending a precomputed final notification payload."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lifetime_bot.bootstrap import create_notifier
from lifetime_bot.config import NotificationConfig
from lifetime_bot.notifier import NotificationDispatchResult


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    summary_only = False
    if args[:1] == ["--summary-only"]:
        summary_only = True
        args = args[1:]
    if len(args) != 1:
        print(
            "Usage: python -m lifetime_bot.notify_result "
            "[--summary-only] <payload.json>"
        )
        return 2

    payload_path = Path(args[0])
    payload = json.loads(payload_path.read_text())
    _log_result_payload(payload)
    subject = str(payload["subject"])
    body = str(payload["body"])
    if summary_only:
        return 0

    config = NotificationConfig.from_env()
    notifier = create_notifier(config)
    dispatch = notifier.send(subject, body, method=config.method)
    _log_notification_delivery(dispatch)
    return 0 if _dispatch_succeeded(dispatch) else 1


def _log_result_payload(payload: dict[str, object]) -> None:
    success = bool(payload.get("success"))
    subject = str(payload.get("subject") or "<missing>")
    summary_lines = (
        "Final result payload summary:",
        f"  success: {success}",
        f"  outcome: {_payload_field(payload, 'outcome')}",
        f"  error_phase: {_payload_field(payload, 'error_phase')}",
        f"  error_type: {_payload_field(payload, 'error_type')}",
        f"  subject: {subject}",
    )
    for line in summary_lines:
        print(line)
    _append_step_summary(
        "Reservation Result",
        (
            f"- Success: {success}",
            f"- Outcome: {_payload_field(payload, 'outcome')}",
            f"- Error phase: {_payload_field(payload, 'error_phase')}",
            f"- Error type: {_payload_field(payload, 'error_type')}",
            f"- Subject: {subject}",
        ),
    )


def _log_notification_delivery(dispatch: NotificationDispatchResult) -> None:
    lines: list[str] = []
    for attempt in dispatch.attempts:
        if not attempt.completed:
            status = "timed out"
        elif attempt.succeeded:
            status = "succeeded"
        elif attempt.error:
            status = f"failed ({attempt.error})"
        else:
            status = "reported failure"
        lines.append(f"  {attempt.channel}: {status}")
    print("Notification delivery summary:")
    for line in lines:
        print(line)
    _append_step_summary(
        "Notification Delivery",
        tuple(f"- {line.strip()}" for line in lines),
    )


def _dispatch_succeeded(dispatch: NotificationDispatchResult) -> bool:
    return bool(dispatch.attempts) and all(
        attempt.completed and attempt.succeeded for attempt in dispatch.attempts
    )


def _payload_field(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if value in {None, ""}:
        return "n/a"
    return str(value)


def _append_step_summary(title: str, lines: tuple[str, ...]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    rendered = [f"## {title}", *lines, ""]
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(rendered))


if __name__ == "__main__":
    raise SystemExit(main())
