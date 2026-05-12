"""Tests for ibgateway_manager.jts_log_config.

The patcher is the only thing standing between us and "API logs never
turn on in production," so every code path needs to fall on a real test.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ibgateway_manager.jts_log_config import _REQUIRED_KEYS, JtsLogConfig


class TestJtsLogConfig(unittest.TestCase):
    # ---- creation path (no pre-existing jts.ini) -----------------------

    def test_apply_creates_jts_ini_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = JtsLogConfig(jts_dir=td)
            self.assertFalse(cfg.ini_path.exists())
            cfg.apply()
            self.assertTrue(cfg.ini_path.is_file())
            text = cfg.ini_path.read_text()
            for section, keys in _REQUIRED_KEYS.items():
                self.assertIn(f"[{section}]", text, section)
                for key, value in keys.items():
                    self.assertIn(f"{key}={value}", text, f"{section}.{key}")

    def test_apply_creates_jts_dir_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jts = Path(td) / "Jts"  # not created
            cfg = JtsLogConfig(jts_dir=str(jts))
            cfg.apply()
            self.assertTrue(jts.is_dir())
            self.assertTrue((jts / "jts.ini").is_file())

    # ---- merge path (existing jts.ini) ---------------------------------

    def test_apply_preserves_unrelated_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "jts.ini"
            ini.write_text(
                "[Logon]\n"
                "useSSL=true\n"
                "displayInfo=foo\n"
                "[IBGateway]\n"
                "TrustedIPs=127.0.0.1\n"
            )
            JtsLogConfig(jts_dir=td).apply()
            text = ini.read_text()
            # Existing keys still there
            self.assertIn("useSSL=true", text)
            self.assertIn("displayInfo=foo", text)
            self.assertIn("TrustedIPs=127.0.0.1", text)
            # Our keys merged in
            self.assertIn("ApiLogLevel=5", text)
            self.assertIn("LogLevel=5", text)

    def test_apply_overwrites_wrong_value_for_required_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "jts.ini"
            ini.write_text(
                "[IBGateway]\n"
                "WriteAPIMessages=false\n"
                "ApiLogLevel=1\n"
            )
            JtsLogConfig(jts_dir=td).apply()
            text = ini.read_text()
            self.assertIn("WriteAPIMessages=true", text)
            self.assertIn("ApiLogLevel=5", text)
            # The old wrong values are gone (would be the only IBGateway
            # section, so a bare substring check works here).
            self.assertNotIn("WriteAPIMessages=false", text)
            self.assertNotIn("ApiLogLevel=1", text)

    def test_apply_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = JtsLogConfig(jts_dir=td)
            cfg.apply()
            first = cfg.ini_path.read_text()
            mtime_first = cfg.ini_path.stat().st_mtime_ns
            cfg.apply()
            second = cfg.ini_path.read_text()
            # File contents identical and no rewrite occurred (mtime stable).
            self.assertEqual(first, second)
            self.assertEqual(mtime_first, cfg.ini_path.stat().st_mtime_ns)

    # ---- parser robustness ---------------------------------------------

    def test_parser_tolerates_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "jts.ini"
            ini.write_text(
                "; comment line\n"
                "# another comment\n"
                "\n"
                "[Logon]\n"
                "useSSL=true\n"
                "\n"
            )
            JtsLogConfig(jts_dir=td).apply()
            text = ini.read_text()
            self.assertIn("useSSL=true", text)
            self.assertIn("[Logging]", text)

    def test_parser_tolerates_keys_without_section(self) -> None:
        """jts.ini sometimes has bare lines before any [section] header;
        we shouldn't crash on them."""
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "jts.ini"
            ini.write_text(
                "stray=value\n"
                "[Logon]\n"
                "useSSL=true\n"
            )
            JtsLogConfig(jts_dir=td).apply()
            text = ini.read_text()
            self.assertIn("useSSL=true", text)
            self.assertIn("ApiLogLevel=5", text)


if __name__ == "__main__":
    unittest.main()
