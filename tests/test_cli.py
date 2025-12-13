import os
import tempfile
import unittest
from unittest.mock import patch

from ibgateway.cli import IBGatewayCLI


class TestCLICompareScreenshots(unittest.TestCase):
    def test_compare_screenshots_missing_file_returns_1(self) -> None:
        cli = IBGatewayCLI()
        with patch("ibgateway.cli.os.path.exists", return_value=False):
            rc = cli._compare_screenshots("/nope/a.png", "/nope/b.png", 0.01)
        self.assertEqual(rc, 1)

    def test_compare_screenshots_pillow_runtimeerror_falls_back_to_filesize(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            with open(a, "wb") as f:
                f.write(b"a" * 100)
            with open(b, "wb") as f:
                f.write(b"b" * 200)

            with patch("ibgateway.cli.os.path.exists", return_value=True):
                with patch("ibgateway.cli.os.path.getsize", side_effect=[100, 200]):
                    with patch("ibgateway.cli.compare_images_pil", side_effect=RuntimeError("no pillow")):
                        rc = cli._compare_screenshots(a, b, 0.01)

        # size diff percent is >5 => considered different => 0
        self.assertEqual(rc, 0)

    def test_compare_screenshots_compare_images_exception_returns_1(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            with open(a, "wb") as f:
                f.write(b"a" * 100)
            with open(b, "wb") as f:
                f.write(b"b" * 100)

            with patch("ibgateway.cli.os.path.exists", return_value=True):
                with patch("ibgateway.cli.os.path.getsize", side_effect=[100, 100]):
                    with patch("ibgateway.cli.compare_images_pil", side_effect=Exception("boom")):
                        rc = cli._compare_screenshots(a, b, 0.01)

        self.assertEqual(rc, 1)

    def test_compare_screenshots_no_changes_returns_mean_diff_rounded(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            with open(a, "wb") as f:
                f.write(b"a" * 100)
            with open(b, "wb") as f:
                f.write(b"b" * 101)

            with patch("ibgateway.cli.os.path.exists", return_value=True):
                with patch("ibgateway.cli.os.path.getsize", side_effect=[100, 101]):
                    with patch(
                        "ibgateway.cli.compare_images_pil",
                        return_value={
                            "mean_diff": 2.6,
                            "max_diff": 10,
                            "diff_percentage": 0.0,
                            "is_similar": True,
                            "has_changes": False,
                            "is_match": True,
                        },
                    ):
                        rc = cli._compare_screenshots(a, b, 0.01)

        self.assertEqual(rc, 3)

    def test_compare_screenshots_has_changes_returns_0(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            with open(a, "wb") as f:
                f.write(b"a" * 100)
            with open(b, "wb") as f:
                f.write(b"b" * 101)

            with patch("ibgateway.cli.os.path.exists", return_value=True):
                with patch("ibgateway.cli.os.path.getsize", side_effect=[100, 101]):
                    with patch(
                        "ibgateway.cli.compare_images_pil",
                        return_value={
                            "mean_diff": 100.0,
                            "max_diff": 255,
                            "diff_percentage": 20.0,
                            "is_similar": False,
                            "has_changes": True,
                            "is_match": False,
                        },
                    ):
                        rc = cli._compare_screenshots(a, b, 0.01)

        self.assertEqual(rc, 0)
