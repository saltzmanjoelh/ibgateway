import os
import tempfile
import unittest

from PIL import Image

from ibgateway.screenshot import compare_images_pil


class TestCompareImagesPilEdges(unittest.TestCase):
    def test_size_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            Image.new("RGB", (10, 10), (0, 0, 0)).save(a)
            Image.new("RGB", (12, 10), (0, 0, 0)).save(b)

            with self.assertRaises(ValueError):
                compare_images_pil(a, b)

    def test_non_rgb_images_are_converted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            Image.new("L", (10, 10), 0).save(a)
            Image.new("L", (10, 10), 0).save(b)

            result = compare_images_pil(a, b)
            self.assertTrue(result["is_match"])
