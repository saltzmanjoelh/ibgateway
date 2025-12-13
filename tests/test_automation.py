import os
import tempfile
import unittest
from pathlib import Path

from ibgateway.automation import AutomationHandler
from ibgateway.config import Config

from PIL import Image


class TestAutomationHandler(unittest.TestCase):
    def test_expected_state_screenshot_path_variants(self) -> None:
        cfg = Config()
        cfg.api_type = "FIX"
        cfg.trading_mode = "LIVE"
        h = AutomationHandler(cfg)
        p = h._expected_state_screenshot_path()
        self.assertTrue(str(p).endswith(os.path.join("test-screenshots", "fix-live.png")))

        cfg.api_type = "IB_API"
        cfg.trading_mode = "PAPER"
        p2 = h._expected_state_screenshot_path()
        self.assertTrue(str(p2).endswith(os.path.join("test-screenshots", "ibapi-paper.png")))

    def test_verify_target_state_fails_when_reference_missing(self) -> None:
        cfg = Config()
        cfg.screenshot_dir = "/tmp/screenshots"
        cfg.screenshot_backend = "python"

        class _H(AutomationHandler):
            def _expected_state_screenshot_path(self) -> Path:
                return Path("/nope/ref.png")

        h = _H(cfg)
        self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_fails_when_compare_raises(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            ref = Path(os.path.join(td, "ref.png"))
            ref.write_bytes(b"not-a-png")

            class _H(AutomationHandler):
                def _expected_state_screenshot_path(self) -> Path:
                    return ref

            h = _H(cfg)
            self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_fails_when_not_match(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            # Reference image is white; fallback "current" screenshot is black -> should not match.
            ref = Path(os.path.join(td, "ref.png"))
            Image.new("RGB", (1024, 768), (255, 255, 255)).save(str(ref), format="PNG")

            class _H(AutomationHandler):
                def _expected_state_screenshot_path(self) -> Path:
                    return ref

            h = _H(cfg)
            self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_succeeds_when_match(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            # Reference image matches fallback "current" screenshot: black 1024x768.
            ref = Path(os.path.join(td, "ref.png"))
            Image.new("RGB", (1024, 768), (0, 0, 0)).save(str(ref), format="PNG")

            class _H(AutomationHandler):
                def _expected_state_screenshot_path(self) -> Path:
                    return ref

            h = _H(cfg)
            self.assertTrue(h.verify_target_state_before_credentials())
