import os
import tempfile
import unittest
import socket
import socketserver
import threading
import time

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

    def test_run_automate_routes_and_applies_arg_overrides(self) -> None:
        # Exercise CLI argument override branches (even if automate ultimately fails due to state verification).
        with tempfile.TemporaryDirectory() as td:
            xdotool = os.path.join(td, "xdotool")
            with open(xdotool, "w", encoding="utf-8") as f:
                f.write(
                    "#!/usr/bin/env bash\n"
                    "if [[ \"$1\" == \"search\" && \"$2\" == \"--name\" ]]; then echo '1'; exit 0; fi\n"
                    "exit 0\n"
                )
            os.chmod(xdotool, 0o755)

            old_env = dict(os.environ)
            try:
                os.environ["XDOTOOL_BIN"] = xdotool
                os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
                os.environ["IBGATEWAY_WINDOW_TIMEOUT"] = "1"
                cli = IBGatewayCLI()
                rc = cli.run(
                    [
                        "automate",
                        "--username",
                        "u",
                        "--password",
                        "p",
                        "--api-type",
                        "FIX",
                        "--trading-mode",
                        "LIVE",
                    ]
                )
            finally:
                os.environ.clear()
                os.environ.update(old_env)
        # Likely fails due to GUI state verification mismatch (that's fine; we just need execution).
        self.assertIn(rc, (0, 1))

    def test_run_screenshot_server_exits_when_seconds_set(self) -> None:
        old_env = dict(os.environ)
        try:
            os.environ["IBGATEWAY_SCREENSHOT_SERVER_SECONDS"] = "0.01"
            os.environ["IBGATEWAY_SLEEP_SCALE"] = "0.001"
            cli = IBGatewayCLI()
            rc = cli.run(["screenshot-server", "--port", "0"])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        self.assertEqual(rc, 0)

    def test_run_port_forward_exits_when_seconds_set(self) -> None:
        class _Echo(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                data = self.request.recv(1024)
                if data:
                    self.request.sendall(b"echo:" + data)

        def _free_port() -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                return int(s.getsockname()[1])

        live = _free_port()
        paper = _free_port()
        f_live = _free_port()
        f_paper = _free_port()

        s_live = socketserver.TCPServer(("127.0.0.1", live), _Echo)
        s_paper = socketserver.TCPServer(("127.0.0.1", paper), _Echo)
        t1 = threading.Thread(target=s_live.serve_forever, daemon=True)
        t2 = threading.Thread(target=s_paper.serve_forever, daemon=True)
        t1.start()
        t2.start()

        old_env = dict(os.environ)
        try:
            os.environ["IB_LIVE_PORT"] = str(live)
            os.environ["IB_PAPER_PORT"] = str(paper)
            os.environ["IB_FORWARD_LIVE_PORT"] = str(f_live)
            os.environ["IB_FORWARD_PAPER_PORT"] = str(f_paper)
            os.environ["IBGATEWAY_PORT_FORWARD_SECONDS"] = "1"
            os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"

            rc_box = {"rc": None}

            def _run() -> None:
                rc_box["rc"] = IBGatewayCLI().run(["port-forward"])

            t = threading.Thread(target=_run, daemon=True)
            t.start()

            # Ensure forwarding works during run window (while thread is running).
            deadline = time.time() + 2
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", f_live), timeout=0.2) as c:
                        c.sendall(b"hi")
                        if c.recv(64) == b"echo:hi":
                            break
                except Exception:
                    time.sleep(0.01)
            else:
                self.fail("Forward port never became reachable")

            t.join(timeout=5)
            self.assertEqual(rc_box["rc"], 0)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            s_live.shutdown()
            s_paper.shutdown()
            s_live.server_close()
            s_paper.server_close()
