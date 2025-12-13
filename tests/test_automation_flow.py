import unittest
from unittest.mock import patch

from ibgateway.automation import AutomationHandler
from ibgateway.config import Config


class TestAutomationFlow(unittest.TestCase):
    def test_run_xdotool_success_and_failure(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)

        class _R:
            def __init__(self, returncode=0, stdout="ok", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        with patch("ibgateway.automation.subprocess.run", return_value=_R(0, "123\n")):
            self.assertEqual(h.run_xdotool("search", "--name", "IBKR"), "123")

        with patch("ibgateway.automation.subprocess.run", return_value=_R(1, "", "err")):
            self.assertIsNone(h.run_xdotool("search", "--name", "IBKR"))

        with patch("ibgateway.automation.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="x", timeout=1)):
            self.assertIsNone(h.run_xdotool("search"))

    def test_find_ibgateway_window_success(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)

        with patch.object(h, "run_xdotool", return_value="999\n"):
            with patch("ibgateway.automation.time.sleep"):
                self.assertEqual(h.find_ibgateway_window(timeout=1), "999")

    def test_find_ibgateway_window_timeout(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)

        with patch.object(h, "run_xdotool", return_value=None):
            with patch("ibgateway.automation.time.sleep"):
                self.assertIsNone(h.find_ibgateway_window(timeout=1))

    def test_click_paths(self) -> None:
        cfg = Config()
        cfg.api_type = "FIX"
        cfg.trading_mode = "LIVE"
        h = AutomationHandler(cfg)

        calls = []

        def fake_run(*args):
            calls.append(args)
            return ""

        with patch.object(h, "run_xdotool", side_effect=fake_run):
            with patch("ibgateway.automation.time.sleep"):
                h.click_api_type_button("wid")
                h.click_trading_mode_button("wid")

        # should have mousemove + click + click at least
        self.assertTrue(any(c[0] == "mousemove" for c in calls))
        self.assertTrue(sum(1 for c in calls if c[0] == "click") >= 4)

    def test_list_all_windows_no_windows(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)
        with patch.object(h, "run_xdotool", return_value=None):
            h.list_all_windows()  # should just return without error

    def test_list_all_windows_with_windows(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)

        def fake_run(cmd, *rest):
            if cmd == "search":
                return "1\n2\n"
            if cmd == "getwindowname":
                return "name"
            if cmd == "getwindowclassname":
                return "class"
            return ""

        with patch.object(h, "run_xdotool", side_effect=fake_run):
            h.list_all_windows()

    def test_move_window(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)
        with patch.object(h, "run_xdotool", return_value="") as rx:
            with patch("ibgateway.automation.time.sleep"):
                h.move_window_to_top_left("123")
        rx.assert_called()

    def test_automate_returns_1_when_window_missing(self) -> None:
        cfg = Config()
        h = AutomationHandler(cfg)
        with patch.object(h, "list_all_windows"):
            with patch.object(h, "find_ibgateway_window", return_value=None):
                self.assertEqual(h.automate(), 1)

    def test_automate_aborts_on_failed_state_verification_when_credentials_present(self) -> None:
        cfg = Config()
        cfg.username = "u"
        h = AutomationHandler(cfg)

        with patch.object(h, "list_all_windows"):
            with patch.object(h, "find_ibgateway_window", return_value="1"):
                with patch.object(h, "move_window_to_top_left"):
                    with patch("ibgateway.automation.time.sleep"):
                        with patch.object(h, "click_api_type_button"):
                            with patch.object(h, "click_trading_mode_button"):
                                with patch.object(h, "verify_target_state_before_credentials", return_value=False):
                                    self.assertEqual(h.automate(), 1)

    def test_automate_skips_verification_when_no_credentials(self) -> None:
        cfg = Config()
        cfg.username = ""
        cfg.password = ""
        h = AutomationHandler(cfg)

        with patch.object(h, "list_all_windows"):
            with patch.object(h, "find_ibgateway_window", return_value="1"):
                with patch.object(h, "move_window_to_top_left"):
                    with patch("ibgateway.automation.time.sleep"):
                        with patch.object(h, "click_api_type_button"):
                            with patch.object(h, "click_trading_mode_button"):
                                with patch.object(h, "verify_target_state_before_credentials", side_effect=AssertionError("should not call")):
                                    with patch.object(h, "type_username"):
                                        with patch.object(h, "type_password"):
                                            self.assertEqual(h.automate(), 0)
