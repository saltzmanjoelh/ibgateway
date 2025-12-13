import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")

            def _fake_run(cmd, capture_output, text, env, timeout):
                # create the expected file
                with open(out, "wb") as f:
                    f.write(b"png")
                return SimpleNamespace(returncode=0, stderr="")

            with patch.object(h, "_command_exists", side_effect=lambda c: c == "scrot"):
                with patch("ibgateway.screenshot.subprocess.run", side_effect=_fake_run):
                    with patch("ibgateway.screenshot.os.path.exists", return_value=True):
                        res = h.take_screenshot(out)

            self.assertEqual(res, out)

    def test_take_screenshot_uses_imagemagick_when_scrot_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            seen = {"cmd": None}

            def _fake_run(cmd, capture_output, text, env, timeout):
                seen["cmd"] = cmd
                with open(out, "wb") as f:
                    f.write(b"png")
                return SimpleNamespace(returncode=0, stderr="")

            with patch.object(h, "_command_exists", side_effect=lambda c: c == "import"):
                with patch("ibgateway.screenshot.subprocess.run", side_effect=_fake_run):
                    with patch("ibgateway.screenshot.os.path.exists", return_value=True):
                        res = h.take_screenshot(out)

            self.assertEqual(res, out)
            self.assertIsNotNone(seen["cmd"])
            self.assertEqual(seen["cmd"][0], "import")

    def test_take_screenshot_fails_when_no_tool_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            h = ScreenshotHandler(cfg)

            with patch.object(h, "_command_exists", return_value=False):
                res = h.take_screenshot(os.path.join(td, "shot.png"))

            self.assertIsNone(res)

    def test_take_screenshot_respects_validate_path(self) -> None:
        cfg = Config()
        cfg.screenshot_dir = "/tmp/screenshots"
        h = ScreenshotHandler(cfg)

        with patch.object(h, "validate_path", return_value=False):
            res = h.take_screenshot("/etc/passwd")

        self.assertIsNone(res)

    def test_take_screenshot_returns_none_on_subprocess_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")

            with patch.object(h, "_command_exists", side_effect=lambda c: c == "scrot"):
                with patch(
                    "ibgateway.screenshot.subprocess.run",
                    return_value=SimpleNamespace(returncode=1, stderr="boom"),
                ):
                    res = h.take_screenshot(out)

            self.assertIsNone(res)
