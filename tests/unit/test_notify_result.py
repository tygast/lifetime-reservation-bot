"""Unit tests for the final-result notification CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from lifetime_bot.notify_result import main


class TestNotifyResult:
    def test_sends_payload_through_configured_notifier(
        self, tmp_path, monkeypatch
    ) -> None:
        payload_path = tmp_path / "result.json"
        payload_path.write_text(
            json.dumps(
                {
                    "subject": "Lifetime Bot - Reserved",
                    "body": "reserved body",
                    "success": True,
                }
        )
        )
        config = MagicMock()
        config.method = "email"
        notifier = MagicMock()

        monkeypatch.setattr(
            "lifetime_bot.notify_result.NotificationConfig.from_env",
            MagicMock(return_value=config),
        )
        monkeypatch.setattr(
            "lifetime_bot.notify_result.create_notifier",
            MagicMock(return_value=notifier),
        )

        assert main([str(payload_path)]) == 0

        notifier.send.assert_called_once_with(
            "Lifetime Bot - Reserved",
            "reserved body",
            method="email",
        )

    def test_returns_usage_error_without_path(self) -> None:
        assert main([]) == 2
