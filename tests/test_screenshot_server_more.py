import io
import os
import tempfile
import unittest
from types import SimpleNamespace

from ibgateway.screenshot_server import ScreenshotServer


class _Handler(ScreenshotServer):
    def __init__(self, path: str, *, screenshot_dir: str, screenshot_handler=None):
        self.path = path
        self.screenshot_dir = screenshot_dir
        self.screenshot_handler = screenshot_handler
        self.server = SimpleNamespace(server_port=8080)
        self.wfile = io.BytesIO()
        self.status = None
        self.error_message = None

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass

    def send_error(self, code, message=None):
        self.status = code
        self.error_message = message


class TestScreenshotServerMore(unittest.TestCase):
    def test_unknown_path_404(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/nope", screenshot_dir=td)
            h.do_GET()
            self.assertEqual(h.status, 404)

    def test_serve_file_access_denied_via_realpath(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h = _Handler("/screenshots/ok.png", screenshot_dir=td)

            # Create a symlink that resolves outside the screenshot_dir.
            link_path = os.path.join(td, "ok.png")
            os.symlink("/etc/passwd", link_path)
            h.do_GET()

            self.assertEqual(h.status, 403)

    def test_take_screenshot_returns_500_when_take_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            class _Fake:
                def take_screenshot(self):
                    return None

            h = _Handler("/screenshot", screenshot_dir=td, screenshot_handler=_Fake())
            h.do_GET()
            self.assertEqual(h.status, 500)

    def test_take_screenshot_returns_500_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            class _Fake:
                def take_screenshot(self):
                    raise RuntimeError("boom")

            h = _Handler("/screenshot", screenshot_dir=td, screenshot_handler=_Fake())
            h.do_GET()
            self.assertEqual(h.status, 500)
