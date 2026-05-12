"""Tests for ServiceOrchestrator._log_capture_enabled().

Both log-streaming pipelines (ApiTrafficCapture, ApiLogTailer) surface
gateway-internal state to CloudWatch. In live trading mode that would
include real account balances, real order IDs, and SMS-MFA token
suffixes — leakage we don't want enabled by default. This test guards
the default-off-in-live behaviour and the env-var override.
"""
from __future__ import annotations

import os
import unittest
import unittest.mock

from ibgateway_manager.config import Config
from ibgateway_manager.orchestrator import ServiceOrchestrator


class _FakeConfig:
    """Minimal stand-in so we don't need a real env to construct
    ServiceOrchestrator (Config.__init__ loads dotenv and validates
    creds, which is overkill for these tests)."""

    def __init__(self, trading_mode: str = "PAPER") -> None:
        self.trading_mode = trading_mode
        # Other fields aren't read by _log_capture_enabled but
        # ServiceOrchestrator.__init__ touches them.
        self.username = ""
        self.password = ""
        self.api_type = "IB_API"
        self.display = ":99"
        self.resolution = "1024x768"
        self.screenshot_dir = "/tmp/screenshots"
        self.screenshot_port = 8080
        self.mcp_port = 8090
        self.mcp_host = "127.0.0.1"


def _make_orch(trading_mode: str) -> ServiceOrchestrator:
    """ServiceOrchestrator instantiates a bunch of service managers in
    __init__; we don't care for these tests, so we mock them out."""
    cfg = _FakeConfig(trading_mode=trading_mode)
    with (
        unittest.mock.patch("ibgateway_manager.orchestrator.XvfbManager"),
        unittest.mock.patch("ibgateway_manager.orchestrator.VNCManager"),
        unittest.mock.patch("ibgateway_manager.orchestrator.NoVNCManager"),
        unittest.mock.patch("ibgateway_manager.orchestrator.WindowManager"),
        unittest.mock.patch("ibgateway_manager.orchestrator.signal.signal"),
    ):
        return ServiceOrchestrator(cfg)  # type: ignore[arg-type]


class TestLogCaptureGate(unittest.TestCase):
    # ---- defaults (no env var) -----------------------------------------

    def test_paper_mode_default_is_enabled(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IBGATEWAY_LOG_CAPTURE", None)
            self.assertTrue(_make_orch("PAPER")._log_capture_enabled())

    def test_live_mode_default_is_disabled(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IBGATEWAY_LOG_CAPTURE", None)
            self.assertFalse(_make_orch("LIVE")._log_capture_enabled())

    # ---- explicit env var force ----------------------------------------

    def test_env_var_true_forces_enable_in_live(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_LOG_CAPTURE": "true"},
        ):
            self.assertTrue(_make_orch("LIVE")._log_capture_enabled())

    def test_env_var_false_forces_disable_in_paper(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_LOG_CAPTURE": "false"},
        ):
            self.assertFalse(_make_orch("PAPER")._log_capture_enabled())

    def test_env_var_paper_only_is_explicit_default(self) -> None:
        """The literal string ``paper-only`` is the documented default;
        passing it explicitly must behave the same as the absence of
        the env var."""
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_LOG_CAPTURE": "paper-only"},
        ):
            self.assertTrue(_make_orch("PAPER")._log_capture_enabled())
            self.assertFalse(_make_orch("LIVE")._log_capture_enabled())

    # ---- robustness ----------------------------------------------------

    def test_env_var_unknown_value_falls_back_to_paper_only(self) -> None:
        """Unknown values shouldn't crash; they should behave like the
        default (paper-only)."""
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_LOG_CAPTURE": "maybe"},
        ):
            self.assertTrue(_make_orch("PAPER")._log_capture_enabled())
            self.assertFalse(_make_orch("LIVE")._log_capture_enabled())

    def test_env_var_case_insensitive(self) -> None:
        for value in ("TRUE", "True", "tRuE"):
            with unittest.mock.patch.dict(
                os.environ, {"IBGATEWAY_LOG_CAPTURE": value},
            ):
                self.assertTrue(
                    _make_orch("LIVE")._log_capture_enabled(),
                    f"value={value!r}",
                )

    def test_env_var_whitespace_tolerated(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_LOG_CAPTURE": "  true  "},
        ):
            self.assertTrue(_make_orch("LIVE")._log_capture_enabled())


if __name__ == "__main__":
    unittest.main()
