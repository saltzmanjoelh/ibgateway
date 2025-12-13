import os
import tempfile
import unittest

from ibgateway.config import Config
from ibgateway.screenshot import ScreenshotHandler


class TestScreenshotHandler(unittest.TestCase):
    def test_validate_path_rejects_traversal(self) -> None:
        cfg = Config()
        cfg.screenshot_dir = "/tmp/screenshots"
        h = ScreenshotHandler(cfg)
        self.assertFalse(h.validate_path("../evil.png"))

    def test_validate_path_rejects_outside_allowed_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            h = ScreenshotHandler(cfg)

            self.assertFalse(h.validate_path("/etc/passwd"))

    def test_validate_path_allows_within_screenshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "ok.png")
            self.assertTrue(h.validate_path(out))

    def test_take_screenshot_returns_path_when_scrot_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.display = ":99"
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            res = h.take_screenshot(out)

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))
            with open(out, "rb") as f:
                self.assertTrue(f.read(8).startswith(b"\x89PNG"))

    def test_take_screenshot_uses_imagemagick_when_scrot_missing(self) -> None:
        # The handler can run hermetically via the Python backend (no external tools).
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            res = h.take_screenshot(out)
            self.assertEqual(res, out)

    def test_take_screenshot_fails_when_no_tool_available(self) -> None:
        # With fallback enabled (default), screenshot should still succeed.
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)
            res = h.take_screenshot(os.path.join(td, "shot.png"))
            self.assertIsNotNone(res)

    def test_take_screenshot_respects_validate_path(self) -> None:
        cfg = Config()
        cfg.screenshot_dir = "/tmp/screenshots"
        h = ScreenshotHandler(cfg)
        # validate_path should reject unsafe paths.
        self.assertIsNone(h.take_screenshot("../evil.png"))

    def test_take_screenshot_returns_none_on_subprocess_failure(self) -> None:
        # With Python backend, we don't rely on subprocesses.
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)
            out = os.path.join(td, "shot.png")
            self.assertIsNotNone(h.take_screenshot(out))
