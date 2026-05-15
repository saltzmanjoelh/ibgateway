"""Tests for AutomationHandler.retry_login_after_failure.

Recovery flow for any partially-completed IB Gateway login dialog state
(e.g. the case observed in prod where xdotool typed the username then
got interrupted before typing the password). The flow is xdotool-heavy
and untestable end-to-end without a live Xvfb + IB Gateway; what we can
pin down with unit tests is the *sequence* of xdotool invocations and
the early-exit branches.

Strategy: patch ``run_xdotool`` to collect every (args) tuple, and
``find_ibgateway_window`` to inject a stable window id. Then walk the
collected calls and assert the documented sequence is what fires.
"""
from __future__ import annotations

import unittest
import unittest.mock as mock

from ibgateway_manager.automate_ibgateway import AutomationHandler


class _FakeConfig:
    """Minimal stand-in for Config so AutomationHandler() can construct
    without dotenv / validation overhead."""

    def __init__(
        self,
        username: str = "test_user",
        password: str = "test_pass",
    ) -> None:
        self.username = username
        self.password = password
        self.api_type = "IB_API"
        self.trading_mode = "PAPER"
        self.display = ":99"
        self.resolution = "1024x768"
        self.screenshot_dir = "/tmp/screenshots"
        self.screenshot_port = 8080
        self.mcp_port = 8090
        self.mcp_host = "127.0.0.1"

    def print_config(self) -> None:
        pass


class TestRetryLoginAfterFailure(unittest.TestCase):
    def _new_handler(self, **cfg_kw) -> tuple[AutomationHandler, list]:
        """Return (handler, calls) where calls is a list of xdotool argv
        tuples populated as the handler's run_xdotool is invoked. Also
        stubs ``time.sleep`` to a no-op so the test doesn't actually
        block."""
        cfg = _FakeConfig(**cfg_kw)
        handler = AutomationHandler(cfg, verbose=False)
        calls: list = []
        # Stable fake window id; find_ibgateway_window returns it.
        handler.find_ibgateway_window = mock.MagicMock(return_value="0xdeadbeef")
        # Capture every xdotool call.
        handler.run_xdotool = mock.MagicMock(
            side_effect=lambda *args: calls.append(args) or ""
        )
        return handler, calls

    # ─── Happy path ────────────────────────────────────────────────────

    def test_returns_0_on_success(self) -> None:
        handler, _ = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            self.assertEqual(handler.retry_login_after_failure(), 0)

    def test_finds_ibgateway_window(self) -> None:
        handler, _ = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        handler.find_ibgateway_window.assert_called_once()

    def test_starts_with_escape_to_clear_modal(self) -> None:
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        # First call should be Escape (clears any stray modal).
        self.assertEqual(calls[0], ("key", "Escape"))

    def test_activates_window_after_escape(self) -> None:
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        # Find the windowactivate call; should come after Escape, before
        # any field manipulation.
        activate_idx = next(
            i for i, c in enumerate(calls)
            if c[0] == "windowactivate" and "0xdeadbeef" in c
        )
        self.assertGreater(activate_idx, 0, "windowactivate should not be the first call")

    def test_shift_tabs_back_to_username_field(self) -> None:
        """Five Shift+Tabs after window activation — walks focus back to
        the topmost editable widget (username) regardless of starting
        position."""
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        shift_tabs = [c for c in calls if c == ("key", "shift+Tab")]
        self.assertEqual(len(shift_tabs), 5)

    def test_clears_username_with_ctrl_a_delete(self) -> None:
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        # At least one ctrl+a and one Delete should fire (for username + password,
        # but the order matters: the first ctrl+a comes BEFORE typing the username).
        first_ctrl_a = next(i for i, c in enumerate(calls) if c == ("key", "ctrl+a"))
        first_delete = next(i for i, c in enumerate(calls) if c == ("key", "Delete"))
        # type username comes after the first ctrl+a + Delete pair
        first_type_username = next(
            i for i, c in enumerate(calls)
            if c[0] == "type" and "test_user" in c
        )
        self.assertLess(first_ctrl_a, first_type_username)
        self.assertLess(first_delete, first_type_username)
        self.assertLess(first_ctrl_a, first_delete)

    def test_types_username_then_password_with_tab_between(self) -> None:
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        type_username_idx = next(
            i for i, c in enumerate(calls)
            if c[0] == "type" and "test_user" in c
        )
        type_password_idx = next(
            i for i, c in enumerate(calls)
            if c[0] == "type" and "test_pass" in c
        )
        # Find the Tab between them
        tab_between = [
            i for i, c in enumerate(calls)
            if c == ("key", "Tab")
            and type_username_idx < i < type_password_idx
        ]
        self.assertEqual(len(tab_between), 1)

    def test_submits_with_Return_at_end(self) -> None:
        handler, calls = self._new_handler()
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        # The very last call should be Return to submit.
        self.assertEqual(calls[-1], ("key", "Return"))

    # ─── Edge cases ────────────────────────────────────────────────────

    def test_returns_1_when_username_missing(self) -> None:
        handler, _ = self._new_handler(username="")
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            self.assertEqual(handler.retry_login_after_failure(), 1)
        # No xdotool calls should fire if creds aren't configured.
        handler.run_xdotool.assert_not_called()
        handler.find_ibgateway_window.assert_not_called()

    def test_returns_1_when_password_missing(self) -> None:
        handler, _ = self._new_handler(password="")
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            self.assertEqual(handler.retry_login_after_failure(), 1)
        handler.run_xdotool.assert_not_called()

    def test_returns_1_when_gateway_window_not_found(self) -> None:
        cfg = _FakeConfig()
        handler = AutomationHandler(cfg, verbose=False)
        handler.find_ibgateway_window = mock.MagicMock(return_value=None)
        handler.run_xdotool = mock.MagicMock(return_value="")
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            self.assertEqual(handler.retry_login_after_failure(), 1)
        # Escape should still have fired (step 1 — clears stray modal),
        # but nothing past the window-not-found check.
        types = [c for c in handler.run_xdotool.call_args_list if c.args[0] == "type"]
        self.assertEqual(types, [])

    def test_credentials_are_not_logged(self) -> None:
        """Sanity: the handler's log method should never receive the
        password as a substring. Catches a naive ``self.log(password)``
        regression."""
        cfg = _FakeConfig(password="hunter2-secret-value")
        handler = AutomationHandler(cfg, verbose=False)
        handler.find_ibgateway_window = mock.MagicMock(return_value="0xdeadbeef")
        handler.run_xdotool = mock.MagicMock(return_value="")
        logged: list = []
        handler.log = mock.MagicMock(side_effect=logged.append)
        with mock.patch("ibgateway_manager.automate_ibgateway.time.sleep"):
            handler.retry_login_after_failure()
        for line in logged:
            self.assertNotIn(
                "hunter2-secret-value", line,
                f"Password leaked to log: {line!r}",
            )


if __name__ == "__main__":
    unittest.main()
