import os
import tempfile
import unittest

from ibgateway.cli import IBGatewayCLI

from PIL import Image


class TestCLICompareScreenshots(unittest.TestCase):
    def test_compare_screenshots_missing_file_returns_1(self) -> None:
        cli = IBGatewayCLI()
        rc = cli._compare_screenshots("/nope/a.png", "/nope/b.png", 0.01)
        self.assertEqual(rc, 1)

    def test_compare_screenshots_small_changes_returns_mean_diff_rounded(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            # 100x100 black image.
            img_a = Image.new("RGB", (100, 100), (0, 0, 0))
            img_a.save(a, format="PNG")

            # Copy and change exactly 100 pixels (1%) to white.
            img_b = img_a.copy()
            px = img_b.load()
            changed = 0
            for y in range(10):
                for x in range(10):
                    px[x, y] = (255, 255, 255)
                    changed += 1
            self.assertEqual(changed, 100)
            img_b.save(b, format="PNG")

            rc = cli._compare_screenshots(a, b, 0.01)

        # With diff_percentage == 1.0% (not > 1.0), CLI returns round(mean_diff) ~= 3.
        self.assertEqual(rc, 3)

    def test_compare_screenshots_has_changes_returns_0(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            Image.new("RGB", (64, 64), (255, 255, 255)).save(a, format="PNG")
            Image.new("RGB", (64, 64), (0, 0, 0)).save(b, format="PNG")
            rc = cli._compare_screenshots(a, b, 0.01)

        self.assertEqual(rc, 0)
