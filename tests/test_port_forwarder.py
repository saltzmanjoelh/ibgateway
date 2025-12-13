import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ibgateway.config import Config
from ibgateway.port_forwarder import PortForwarder


class _Proc:
    def __init__(self, pid=123):
        self.pid = pid
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        # start_forwarding waits without timeout; cleanup waits with timeout
        if timeout is None:
            raise KeyboardInterrupt()
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TestPortForwarder(unittest.TestCase):
    def test_check_port_listening_uses_netstat(self) -> None:
        pf = PortForwarder(Config())
        with patch(
            "ibgateway.port_forwarder.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="tcp 0 0 0.0.0.0:4003 "),
        ):
            self.assertTrue(pf.check_port_listening(4003))

    def test_check_port_listening_falls_back_to_ss(self) -> None:
        pf = PortForwarder(Config())

        def fake_run(cmd, capture_output=True, text=True):
            if cmd[0] == "netstat":
                return SimpleNamespace(returncode=1, stdout="")
            return SimpleNamespace(returncode=0, stdout="LISTEN 0 0 *:4004 ")

        with patch("ibgateway.port_forwarder.subprocess.run", side_effect=fake_run):
            self.assertTrue(pf.check_port_listening(4004))

    def test_wait_for_ports_returns_true_when_ready(self) -> None:
        pf = PortForwarder(Config())
        with patch.object(pf, "check_port_listening", return_value=True):
            with patch("ibgateway.port_forwarder.time.sleep"):
                self.assertTrue(pf.wait_for_ports(timeout=1))

    def test_wait_for_ports_returns_false_when_timeout(self) -> None:
        pf = PortForwarder(Config())
        with patch.object(pf, "check_port_listening", return_value=False):
            with patch("ibgateway.port_forwarder.time.sleep"):
                self.assertFalse(pf.wait_for_ports(timeout=1))

    def test_start_forwarding_launches_processes_and_cleans_up(self) -> None:
        pf = PortForwarder(Config())

        # Make sure verification says forwarding is active.
        def fake_check(port):
            return port in (pf.forward_live_port, pf.forward_paper_port)

        with patch.object(pf, "wait_for_ports", return_value=True):
            with patch.object(pf, "check_port_listening", side_effect=fake_check):
                with patch("ibgateway.port_forwarder.signal.signal"):
                    with patch("ibgateway.port_forwarder.subprocess.Popen", side_effect=[_Proc(1), _Proc(2)]):
                        rc = pf.start_forwarding()

        self.assertEqual(rc, 0)
        # cleanup should have been attempted
        self.assertTrue(all(p.terminated or p.killed for p in pf.processes))
