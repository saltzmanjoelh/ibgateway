import os
import unittest

from ibgateway.config import Config


class TestConfig(unittest.TestCase):
    def test_defaults_load(self) -> None:
        old = dict(os.environ)
        try:
            os.environ.clear()
            cfg = Config()
            self.assertEqual(cfg.api_type, "IB_API")
            self.assertEqual(cfg.trading_mode, "PAPER")
            self.assertEqual(cfg.display, ":99")
            self.assertEqual(cfg.screenshot_port, 8080)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_uppercases_values(self) -> None:
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"IB_API_TYPE": "fix", "IB_TRADING_MODE": "live", "SCREENSHOT_PORT": "1234"})
            cfg = Config()
            self.assertEqual(cfg.api_type, "FIX")
            self.assertEqual(cfg.trading_mode, "LIVE")
            self.assertEqual(cfg.screenshot_port, 1234)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_invalid_api_type_raises(self) -> None:
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ["IB_API_TYPE"] = "NOPE"
            with self.assertRaises(ValueError):
                Config()
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_invalid_trading_mode_raises(self) -> None:
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ["IB_TRADING_MODE"] = "NOPE"
            with self.assertRaises(ValueError):
                Config()
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_invalid_screenshot_port_raises(self) -> None:
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ["SCREENSHOT_PORT"] = "not-an-int"
            with self.assertRaises(ValueError):
                Config()
        finally:
            os.environ.clear()
            os.environ.update(old)
