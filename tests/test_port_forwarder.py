import unittest
import socket
import socketserver
import threading
import time

from ibgateway.config import Config
from ibgateway.port_forwarder import PortForwarder


class _Echo(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request.recv(1024)
        if data:
            self.request.sendall(b"echo:" + data)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestPortForwarder(unittest.TestCase):
    def test_check_port_listening(self) -> None:
        port = _free_port()
        pf = PortForwarder(Config())

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            s.listen(1)
            self.assertTrue(pf.check_port_listening(port))

        self.assertFalse(pf.check_port_listening(port))

    def test_wait_for_ports_returns_true_when_ready(self) -> None:
        live = _free_port()
        paper = _free_port()

        cfg = Config()
        cfg.ib_live_port = live
        cfg.ib_paper_port = paper
        cfg.sleep_scale = 0  # fast
        pf = PortForwarder(cfg)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
            s1.bind(("127.0.0.1", live))
            s1.listen(1)
            s2.bind(("127.0.0.1", paper))
            s2.listen(1)
            self.assertTrue(pf.wait_for_ports(timeout=1))

    def test_start_forwarding_launches_processes_and_cleans_up(self) -> None:
        live = _free_port()
        paper = _free_port()
        f_live = _free_port()
        f_paper = _free_port()

        cfg = Config()
        cfg.ib_live_port = live
        cfg.ib_paper_port = paper
        cfg.forward_live_port = f_live
        cfg.forward_paper_port = f_paper
        cfg.sleep_scale = 0
        pf = PortForwarder(cfg)

        # Upstream echo servers.
        s_live = socketserver.TCPServer(("127.0.0.1", live), _Echo)
        s_paper = socketserver.TCPServer(("127.0.0.1", paper), _Echo)
        t1 = threading.Thread(target=s_live.serve_forever, daemon=True)
        t2 = threading.Thread(target=s_paper.serve_forever, daemon=True)
        t1.start()
        t2.start()

        # Run forwarder in background so we can exercise it.
        rc_box = {"rc": None}

        def _run():
            rc_box["rc"] = pf.start_forwarding(run_seconds=1)

        ft = threading.Thread(target=_run, daemon=True)
        ft.start()

        # Wait briefly for listeners.
        deadline = time.time() + 2
        while time.time() < deadline:
            if pf.check_port_listening(f_live) and pf.check_port_listening(f_paper):
                break
            time.sleep(0.01)

        with socket.create_connection(("127.0.0.1", f_live), timeout=1) as c:
            c.sendall(b"hi")
            self.assertEqual(c.recv(64), b"echo:hi")

        ft.join(timeout=3)
        self.assertEqual(rc_box["rc"], 0)

        s_live.shutdown()
        s_paper.shutdown()
        s_live.server_close()
        s_paper.server_close()
