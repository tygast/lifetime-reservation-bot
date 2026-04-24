"""Unit tests for the CLI entry point."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from lifetime_bot import __main__ as main_module


class TestMain:
    @patch("lifetime_bot.__main__.run_bot", return_value=True)
    def test_main_runs_immediately_when_schedule_disabled(
        self, run_bot: MagicMock
    ) -> None:
        with patch.dict(os.environ, {"RUN_ON_SCHEDULE": "false"}, clear=False):
            assert main_module.main() == 0

        run_bot.assert_called_once_with()
