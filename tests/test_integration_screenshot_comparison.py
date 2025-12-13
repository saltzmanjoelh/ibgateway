import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

from ibgateway.automation import AutomationHandler
from ibgateway.config import Config
from ibgateway.screenshot import compare_images_pil


def _write_solid_rgb_png(path: str, *, color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")


@unittest.skipUnless(HAS_PIL, "Pillow is required for screenshot comparison tests")
class TestScreenshotComparisonIntegration(unittest.TestCase):
    def test_compare_images_pil_identical_is_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            _write_solid_rgb_png(a, color=(255, 255, 255))
            _write_solid_rgb_png(b, color=(255, 255, 255))

            result = compare_images_pil(a, b, threshold=0.01, max_diff_percentage=1.0)

            self.assertTrue(result["is_match"])
            self.assertTrue(result["is_similar"])
            self.assertFalse(result["has_changes"])
            self.assertEqual(result["diff_percentage"], 0.0)

    def test_compare_images_pil_different_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            _write_solid_rgb_png(a, color=(255, 255, 255))
            _write_solid_rgb_png(b, color=(0, 0, 0))

            result = compare_images_pil(a, b, threshold=0.01, max_diff_percentage=1.0)

            self.assertFalse(result["is_match"])
            self.assertTrue(result["has_changes"])
            self.assertGreater(result["diff_percentage"], 50.0)

    def test_cli_compare_screenshots_runs_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            _write_solid_rgb_png(a, color=(255, 255, 255))
            _write_solid_rgb_png(b, color=(0, 0, 0))

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ibgateway.cli",
                    "compare-screenshots",
                    a,
                    b,
                    "--threshold",
                    "0.01",
                ],
                capture_output=True,
                text=True,
            )

            # For "changes detected" the CLI returns 0.
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
            self.assertIn("Comparing images:", proc.stdout)
            self.assertIn("X Images are different", proc.stdout)

    def test_automation_verifies_target_state_before_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ref = os.path.join(td, "ref.png")
            current = os.path.join(td, "current.png")
            _write_solid_rgb_png(ref, color=(10, 20, 30))
            _write_solid_rgb_png(current, color=(10, 20, 30))

            cfg = Config()
            cfg.api_type = "IB_API"
            cfg.trading_mode = "PAPER"
            cfg.screenshot_dir = td
            cfg.username = "user"  # ensure verification runs in automate flow, too

            handler = AutomationHandler(cfg, verbose=False)

            class _FakeScreenshotHandler:
                def __init__(self, *_args, **_kwargs):
                    pass

                def take_screenshot(self, output_path: str):
                    shutil.copyfile(current, output_path)
                    return output_path

            with patch("ibgateway.automation.ScreenshotHandler", _FakeScreenshotHandler):
                with patch.object(handler, "_expected_state_screenshot_path", return_value=ref):
                    ok = handler.verify_target_state_before_credentials()

            self.assertTrue(ok)
