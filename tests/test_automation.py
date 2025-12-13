import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ibgateway.automation import AutomationHandler
from ibgateway.config import Config


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
        h = AutomationHandler(cfg)
        with patch.object(h, "_expected_state_screenshot_path", return_value=Path("/nope/ref.png")):
            self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_fails_when_screenshot_capture_fails(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            h = AutomationHandler(cfg)
            ref = Path(os.path.join(td, "ref.png"))
            ref.write_bytes(b"x")

            class _FakeScreenshotHandler:
                def __init__(self, *_a, **_k):
                    pass

                def take_screenshot(self, _output_path: str):
                    return None

            with patch.object(h, "_expected_state_screenshot_path", return_value=ref):
                with patch("ibgateway.automation.ScreenshotHandler", _FakeScreenshotHandler):
                    self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_fails_when_compare_raises(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            h = AutomationHandler(cfg)
            ref = Path(os.path.join(td, "ref.png"))
            ref.write_bytes(b"x")

            class _FakeScreenshotHandler:
                def __init__(self, *_a, **_k):
                    pass

                def take_screenshot(self, output_path: str):
                    Path(output_path).write_bytes(b"y")
                    return output_path

            with patch.object(h, "_expected_state_screenshot_path", return_value=ref):
                with patch("ibgateway.automation.ScreenshotHandler", _FakeScreenshotHandler):
                    with patch("ibgateway.automation.compare_images_pil", side_effect=Exception("boom")):
                        self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_fails_when_not_match(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            h = AutomationHandler(cfg)
            ref = Path(os.path.join(td, "ref.png"))
            ref.write_bytes(b"x")

            class _FakeScreenshotHandler:
                def __init__(self, *_a, **_k):
                    pass

                def take_screenshot(self, output_path: str):
                    Path(output_path).write_bytes(b"y")
                    return output_path

            with patch.object(h, "_expected_state_screenshot_path", return_value=ref):
                with patch("ibgateway.automation.ScreenshotHandler", _FakeScreenshotHandler):
                    with patch(
                        "ibgateway.automation.compare_images_pil",
                        return_value={
                            "mean_diff": 1.0,
                            "max_diff": 10,
                            "diff_percentage": 2.0,
                            "is_similar": True,
                            "has_changes": True,
                            "is_match": False,
                        },
                    ):
                        self.assertFalse(h.verify_target_state_before_credentials())

    def test_verify_target_state_succeeds_when_match(self) -> None:
        cfg = Config()
        with tempfile.TemporaryDirectory() as td:
            cfg.screenshot_dir = td
            h = AutomationHandler(cfg)
            ref = Path(os.path.join(td, "ref.png"))
            ref.write_bytes(b"x")

            class _FakeScreenshotHandler:
                def __init__(self, *_a, **_k):
                    pass

                def take_screenshot(self, output_path: str):
                    Path(output_path).write_bytes(b"y")
                    return output_path

            with patch.object(h, "_expected_state_screenshot_path", return_value=ref):
                with patch("ibgateway.automation.ScreenshotHandler", _FakeScreenshotHandler):
                    with patch(
                        "ibgateway.automation.compare_images_pil",
                        return_value={
                            "mean_diff": 0.0,
                            "max_diff": 0,
                            "diff_percentage": 0.0,
                            "is_similar": True,
                            "has_changes": False,
                            "is_match": True,
                        },
                    ):
                        self.assertTrue(h.verify_target_state_before_credentials())
