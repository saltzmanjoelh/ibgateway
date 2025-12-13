import io
import json
import os
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace

from ibgateway.screenshot_server import ScreenshotServer


class _Handler(ScreenshotServer):
    """Test-friendly handler: no sockets, captures outputs."""

    def __init__(self, path: str, *, screenshot_dir: str, screenshot_handler=None):
        # BaseHTTPRequestHandler normally expects a socket; we bypass it.
        self.path = path
        self.screenshot_dir = screenshot_dir
        self.screenshot_handler = screenshot_handler
        self.server = SimpleNamespace(server_port=8080)
        self.wfile = io.BytesIO()
        self.status = None
        self.error_message = None
        self.headers = []

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.headers.append((key, value))

    def end_headers(self):
        pass

    def send_error(self, code, message=None):
        self.status = code
        self.error_message = message


class TestScreenshotServer(unittest.TestCase):
    def test_root_serves_index(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 200)
            self.assertIn(b"Screenshot Service", h.wfile.getvalue())

    def test_screenshot_endpoint_requires_handler(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/screenshot", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 500)

    def test_screenshot_endpoint_returns_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "screenshot_1.png")

            class _Fake:
                def take_screenshot(self):
                    with open(out, "wb") as f:
                        f.write(b"png")
                    return out

            h = _Handler("/screenshot", screenshot_dir=td, screenshot_handler=_Fake())
            h.do_GET()
            self.assertEqual(h.status, 200)
            payload = json.loads(h.wfile.getvalue().decode())
            self.assertTrue(payload["success"])
            self.assertEqual(payload["filename"], "screenshot_1.png")
            self.assertEqual(payload["url"], "/screenshots/screenshot_1.png")

    def test_latest_endpoint_404_when_no_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/screenshot/latest", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 404)

    def test_latest_endpoint_returns_latest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "screenshot_1.png")
            b = os.path.join(td, "screenshot_2.png")
            with open(a, "wb") as f:
                f.write(b"a")
            with open(b, "wb") as f:
                f.write(b"b")

            # Ensure deterministic "latest" by patching getctime.
            def fake_getctime(path):
                return 1 if path.endswith("screenshot_1.png") else 2

            with unittest.mock.patch("ibgateway.screenshot_server.os.path.getctime", side_effect=fake_getctime):
                h = _Handler("/screenshot/latest", screenshot_dir=td, screenshot_handler=None)
                h.do_GET()

            self.assertEqual(h.status, 200)
            payload = json.loads(h.wfile.getvalue().decode())
            self.assertEqual(payload["filename"], "screenshot_2.png")

    def test_list_endpoint_returns_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "screenshot_1.png")
            b = os.path.join(td, "screenshot_2.png")
            with open(a, "wb") as f:
                f.write(b"a" * 10)
            with open(b, "wb") as f:
                f.write(b"b" * 20)

            def fake_getctime(path):
                return 1 if path.endswith("screenshot_1.png") else 2

            with unittest.mock.patch("ibgateway.screenshot_server.os.path.getctime", side_effect=fake_getctime):
                h = _Handler("/screenshots", screenshot_dir=td, screenshot_handler=None)
                h.do_GET()

            self.assertEqual(h.status, 200)
            payload = json.loads(h.wfile.getvalue().decode())
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["screenshots"][0]["filename"], "screenshot_2.png")

    def test_serve_screenshot_file_security_checks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # traversal
            h = _Handler("/screenshots/../x.png", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 400)

            # non-png
            h2 = _Handler("/screenshots/x.jpg", screenshot_dir=td, screenshot_handler=None)
            h2.do_GET()
            self.assertEqual(h2.status, 400)

    def test_serve_screenshot_file_404_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/screenshots/missing.png", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 404)

    def test_serve_screenshot_file_200_when_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ok.png")
            with open(p, "wb") as f:
                f.write(b"pngdata")
            h = _Handler("/screenshots/ok.png", screenshot_dir=td, screenshot_handler=None)
            h.do_GET()
            self.assertEqual(h.status, 200)
            self.assertEqual(h.wfile.getvalue(), b"pngdata")
