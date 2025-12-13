import os
import unittest
from unittest.mock import patch

from ibgateway.config import Config


class TestConfig(unittest.TestCase):
    def test_defaults_load(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            self.assertEqual(cfg.api_type, "IB_API")
            self.assertEqual(cfg.trading_mode, "PAPER")
            self.assertEqual(cfg.display, ":99")
            self.assertEqual(cfg.screenshot_port, 8080)

    def test_uppercases_values(self) -> None:
        with patch.dict(
            os.environ,
            {"IB_API_TYPE": "fix", "IB_TRADING_MODE": "live", "SCREENSHOT_PORT": "1234"},
            clear=True,
        ):
            cfg = Config()
            self.assertEqual(cfg.api_type, "FIX")
            self.assertEqual(cfg.trading_mode, "LIVE")
            self.assertEqual(cfg.screenshot_port, 1234)

    def test_invalid_api_type_raises(self) -> None:
        with patch.dict(os.environ, {"IB_API_TYPE": "NOPE"}, clear=True):
            with self.assertRaises(ValueError):
                Config()

    def test_invalid_trading_mode_raises(self) -> None:
        with patch.dict(os.environ, {"IB_TRADING_MODE": "NOPE"}, clear=True):
            with self.assertRaises(ValueError):
                Config()

    def test_invalid_screenshot_port_raises(self) -> None:
        with patch.dict(os.environ, {"SCREENSHOT_PORT": "not-an-int"}, clear=True):
            with self.assertRaises(ValueError):
                Config()
