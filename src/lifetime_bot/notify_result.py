"""CLI entrypoint for sending a precomputed final notification payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lifetime_bot.bootstrap import create_notifier
from lifetime_bot.config import NotificationConfig


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m lifetime_bot.notify_result <payload.json>")
        return 2

    payload_path = Path(args[0])
    payload = json.loads(payload_path.read_text())
    subject = str(payload["subject"])
    body = str(payload["body"])

    config = NotificationConfig.from_env()
    notifier = create_notifier(config)
    notifier.send(subject, body, method=config.method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
