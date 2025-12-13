import os
import tempfile
import unittest
from pathlib import Path

from ibgateway.automation import AutomationHandler
from ibgateway.config import Config


class TestAutomationFlow(unittest.TestCase):
    def test_run_xdotool_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ok = os.path.join(td, "xdotool_ok")
            bad = os.path.join(td, "xdotool_bad")
            slow = os.path.join(td, "xdotool_slow")

            _write_exe(ok, "#!/usr/bin/env bash\necho '123'\nexit 0\n")
            _write_exe(bad, "#!/usr/bin/env bash\nexit 1\n")
            _write_exe(slow, "#!/usr/bin/env bash\nsleep 0.2\necho 'late'\nexit 0\n")

            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = ok
                os.environ["XDOTOOL_TIMEOUT"] = "1"
                cfg = Config()
                h = AutomationHandler(cfg)
                self.assertEqual(h.run_xdotool("search", "--name", "IBKR"), "123")

                os.environ["XDOTOOL_BIN"] = bad
                cfg2 = Config()
                h2 = AutomationHandler(cfg2)
                self.assertIsNone(h2.run_xdotool("search", "--name", "IBKR"))

                os.environ["XDOTOOL_BIN"] = slow
                os.environ["XDOTOOL_TIMEOUT"] = "0.05"
                cfg3 = Config()
                h3 = AutomationHandler(cfg3)
                self.assertIsNone(h3.run_xdotool("search"))
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_find_ibgateway_window_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(
                xdotool,
                "#!/usr/bin/env bash\n"
                "if [[ \"$1\" == \"search\" ]]; then echo '999'; exit 0; fi\n"
                "exit 0\n",
            )
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                cfg = Config()
                h = AutomationHandler(cfg)
                self.assertEqual(h.find_ibgateway_window(timeout=1), "999")
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_find_ibgateway_window_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(xdotool, "#!/usr/bin/env bash\nexit 0\n")
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                cfg = Config()
                h = AutomationHandler(cfg)
                self.assertIsNone(h.find_ibgateway_window(timeout=1))
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_click_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "log.txt")
            xdotool = os.path.join(td, "xdotool")
            _write_exe(
                xdotool,
                "#!/usr/bin/env bash\n"
                "echo \"$@\" >> \"$XDOTOOL_LOG\"\n"
                "exit 0\n",
            )
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["XDOTOOL_LOG"] = log
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                cfg = Config()
                cfg.api_type = "FIX"
                cfg.trading_mode = "LIVE"
                h = AutomationHandler(cfg)
                h.click_api_type_button("wid")
                h.click_trading_mode_button("wid")
            finally:
                os.environ.clear()
                os.environ.update(old_env)

            contents = Path(log).read_text(encoding="utf-8")
            self.assertIn("mousemove", contents)
            self.assertGreaterEqual(contents.count("click"), 4)

    def test_list_all_windows_no_windows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(xdotool, "#!/usr/bin/env bash\nexit 0\n")
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                cfg = Config()
                h = AutomationHandler(cfg)
                h.list_all_windows()
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_list_all_windows_with_windows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(
                xdotool,
                "#!/usr/bin/env bash\n"
                "cmd=\"$1\"; shift || true\n"
                "if [[ \"$cmd\" == \"search\" ]]; then echo -e '1\\n2'; exit 0; fi\n"
                "if [[ \"$cmd\" == \"getwindowname\" ]]; then echo 'name'; exit 0; fi\n"
                "if [[ \"$cmd\" == \"getwindowclassname\" ]]; then echo 'class'; exit 0; fi\n"
                "exit 0\n",
            )
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                cfg = Config()
                h = AutomationHandler(cfg)
                h.list_all_windows()
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_move_window(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "log.txt")
            xdotool = os.path.join(td, "xdotool")
            _write_exe(
                xdotool,
                "#!/usr/bin/env bash\n"
                "echo \"$@\" >> \"$XDOTOOL_LOG\"\n"
                "exit 0\n",
            )
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["XDOTOOL_LOG"] = log
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                cfg = Config()
                h = AutomationHandler(cfg)
                h.move_window_to_top_left("123")
            finally:
                os.environ.clear()
                os.environ.update(old_env)
            self.assertIn("windowmove 123 0 0", Path(log).read_text(encoding="utf-8"))

    def test_automate_returns_1_when_window_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(xdotool, "#!/usr/bin/env bash\nexit 0\n")
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                os.environ["IBGATEWAY_WINDOW_TIMEOUT"] = "1"
                cfg = Config()
                h = AutomationHandler(cfg)
                self.assertEqual(h.automate(), 1)
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_automate_skips_verification_when_no_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            _write_exe(
                xdotool,
                "#!/usr/bin/env bash\n"
                "if [[ \"$1\" == \"search\" && \"$2\" == \"--name\" ]]; then echo '1'; exit 0; fi\n"
                "exit 0\n",
            )
            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                os.environ["IBGATEWAY_WINDOW_TIMEOUT"] = "1"
                cfg = Config()
                cfg.username = ""
                cfg.password = ""
                h = AutomationHandler(cfg)
                self.assertEqual(h.automate(), 0)
            finally:
                os.environ.clear()
                os.environ.update(old_env)


def _write_exe(path: str, contents: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(contents)
    os.chmod(path, 0o755)
