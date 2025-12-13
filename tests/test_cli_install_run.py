import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ibgateway.cli import IBGatewayCLI


class _P:
    def __init__(self):
        self.terminated = False

    def wait(self):
        return 0

    def terminate(self):
        self.terminated = True


class TestCLIInstallAndRun(unittest.TestCase):
    def test_install_ibgateway_success(self) -> None:
        cli = IBGatewayCLI()

        # curl + installer invocation
        with patch("ibgateway.cli.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            with patch("ibgateway.cli.os.chmod"):
                self.assertEqual(cli._install_ibgateway(verbose=False, use_latest=False), 0)

    def test_install_ibgateway_calledprocesserror_returns_1(self) -> None:
        import subprocess

        cli = IBGatewayCLI()
        with patch(
            "ibgateway.cli.subprocess.run",
            side_effect=subprocess.CalledProcessError(returncode=1, cmd=["curl"]),
        ):
            self.assertEqual(cli._install_ibgateway(verbose=False, use_latest=False), 1)

    def test_run_ibgateway_normal_exit(self) -> None:
        cli = IBGatewayCLI()

        xvfb = _P()
        ib = _P()

        with patch("ibgateway.cli.subprocess.Popen", side_effect=[xvfb, ib]):
            with patch("ibgateway.cli.time.sleep"):
                self.assertEqual(cli._run_ibgateway(verbose=False), 0)

    def test_run_ibgateway_keyboardinterrupt_terminates(self) -> None:
        cli = IBGatewayCLI()

        class _PI:
            def __init__(self):
                self.terminated = False

            def wait(self):
                raise KeyboardInterrupt()

            def terminate(self):
                self.terminated = True

        xvfb = _PI()
        ib = _PI()

        with patch("ibgateway.cli.subprocess.Popen", side_effect=[xvfb, ib]):
            with patch("ibgateway.cli.time.sleep"):
                self.assertEqual(cli._run_ibgateway(verbose=False), 0)

        self.assertTrue(xvfb.terminated)
        self.assertTrue(ib.terminated)
