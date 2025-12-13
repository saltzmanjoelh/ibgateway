import os
import tempfile
import unittest

from ibgateway.cli import IBGatewayCLI


class TestCLIRouting(unittest.TestCase):
    def test_no_command_prints_help_and_returns_1(self) -> None:
        cli = IBGatewayCLI()
        rc = cli.run([])
        self.assertEqual(rc, 1)

    def test_run_screenshot_routes_to_screenshot_handler(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "x.png")
            old_env = dict(os.environ)
            os.environ["SCREENSHOT_DIR"] = td
            os.environ["SCREENSHOT_BACKEND"] = "python"
            os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
            try:
                cli = IBGatewayCLI()
                rc = cli.run(["screenshot", "--output", out])
            finally:
                os.environ.clear()
                os.environ.update(old_env)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))

    def test_run_compare_screenshots_routes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            with open(a, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
            with open(b, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
            cli = IBGatewayCLI()
            rc = cli.run(["compare-screenshots", a, b])
        # Invalid PNG content will cause comparison error and return 1.
        self.assertEqual(rc, 1)
