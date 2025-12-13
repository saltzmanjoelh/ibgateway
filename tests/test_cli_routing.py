import unittest
from unittest.mock import patch

from ibgateway.cli import IBGatewayCLI


class TestCLIRouting(unittest.TestCase):
    def test_no_command_prints_help_and_returns_1(self) -> None:
        cli = IBGatewayCLI()
        with patch.object(cli.parser, "print_help") as ph:
            rc = cli.run([])
        self.assertEqual(rc, 1)
        ph.assert_called_once()

    def test_run_automate_routes_to_automation_handler(self) -> None:
        cli = IBGatewayCLI()
        with patch("ibgateway.cli.AutomationHandler") as AH:
            AH.return_value.automate.return_value = 0
            rc = cli.run(["automate"])
        self.assertEqual(rc, 0)

    def test_run_screenshot_routes_to_screenshot_handler(self) -> None:
        cli = IBGatewayCLI()
        with patch("ibgateway.cli.ScreenshotHandler") as SH:
            SH.return_value.take_screenshot.return_value = "/tmp/x.png"
            rc = cli.run(["screenshot", "--output", "/tmp/x.png"])
        self.assertEqual(rc, 0)

    def test_run_screenshot_failure_returns_1(self) -> None:
        cli = IBGatewayCLI()
        with patch("ibgateway.cli.ScreenshotHandler") as SH:
            SH.return_value.take_screenshot.return_value = None
            rc = cli.run(["screenshot"])
        self.assertEqual(rc, 1)

    def test_run_screenshot_server_routes_to_method(self) -> None:
        cli = IBGatewayCLI()
        with patch.object(cli, "_run_screenshot_server", return_value=0) as rss:
            rc = cli.run(["screenshot-server", "--port", "9999"])
        self.assertEqual(rc, 0)
        rss.assert_called_once()

    def test_run_port_forward_routes_to_port_forwarder(self) -> None:
        cli = IBGatewayCLI()
        with patch("ibgateway.cli.PortForwarder") as PF:
            PF.return_value.start_forwarding.return_value = 0
            rc = cli.run(["port-forward"])
        self.assertEqual(rc, 0)

    def test_run_compare_screenshots_routes(self) -> None:
        cli = IBGatewayCLI()
        with patch.object(cli, "_compare_screenshots", return_value=0) as cs:
            rc = cli.run(["compare-screenshots", "a.png", "b.png"])
        self.assertEqual(rc, 0)
        cs.assert_called_once()
