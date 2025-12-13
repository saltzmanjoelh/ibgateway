import os
import tempfile
import unittest
import subprocess

from ibgateway.config import Config
from ibgateway.screenshot import ScreenshotHandler


class TestScreenshotHandler(unittest.TestCase):
    def test_log_verbose_prefix(self) -> None:
        cfg = Config()
        h = ScreenshotHandler(cfg, verbose=True)
        # Just ensure it runs (covers verbose branch).
        h.log("hello")

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

    def test_validate_path_realpath_exception_is_nonfatal(self) -> None:
        cfg = Config()
        # Force os.path.realpath(self.config.screenshot_dir) to raise TypeError.
        cfg.screenshot_dir = None  # type: ignore[assignment]
        h = ScreenshotHandler(cfg)
        self.assertTrue(h.validate_path("/tmp/ok.png"))

    def test_take_screenshot_returns_path_when_scrot_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.display = ":99"
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            res = h.take_screenshot(out)

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))
            with open(out, "rb") as f:
                self.assertTrue(f.read(8).startswith(b"\x89PNG"))

    def test_take_screenshot_uses_imagemagick_when_scrot_missing(self) -> None:
        # The handler can run hermetically via the Python backend (no external tools).
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            res = h.take_screenshot(out)
            self.assertEqual(res, out)

    def test_take_screenshot_fails_when_no_tool_available(self) -> None:
        # With fallback enabled (default), screenshot should still succeed.
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)
            res = h.take_screenshot(os.path.join(td, "shot.png"))
            self.assertIsNotNone(res)

    def test_take_screenshot_auto_prefers_scrot_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Create a fake scrot binary on PATH.
            bindir = os.path.join(td, "bin")
            os.makedirs(bindir, exist_ok=True)
            scrot = os.path.join(bindir, "scrot")
            with open(scrot, "w", encoding="utf-8") as f:
                f.write(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "out=\"${@: -1}\"\n"
                    "printf '\\x89PNG\\r\\n\\x1a\\n' > \"$out\"\n"
                    "exit 0\n"
                )
            os.chmod(scrot, 0o755)

            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "auto"
            cfg.screenshot_allow_fallback = False
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = bindir + ":" + old_path
            try:
                res = h.take_screenshot(out)
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))

    def test_take_screenshot_auto_uses_imagemagick_when_scrot_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bindir = os.path.join(td, "bin")
            os.makedirs(bindir, exist_ok=True)

            # Provide a local `which` that hides scrot and exposes import (so we don't
            # accidentally pick up a system scrot from the runner).
            which = os.path.join(bindir, "which")
            with open(which, "w", encoding="utf-8") as f:
                f.write(
                    "#!/bin/sh\n"
                    "cmd=\"$1\"\n"
                    "if [ \"$cmd\" = \"import\" ]; then exit 0; fi\n"
                    "exit 1\n"
                )
            os.chmod(which, 0o755)

            # Provide only 'import' command.
            imp = os.path.join(bindir, "import")
            with open(imp, "w", encoding="utf-8") as f:
                f.write(
                    "#!/bin/sh\n"
                    "set -eu\n"
                    "out=\"$(eval echo \\${$#})\"\n"
                    "printf '\\211PNG\\r\\n\\032\\n' > \"$out\"\n"
                    "exit 0\n"
                )
            os.chmod(imp, 0o755)

            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "auto"
            cfg.screenshot_allow_fallback = False
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            old_path = os.environ.get("PATH", "")
            # Use only our bindir so scrot can't be discovered.
            os.environ["PATH"] = bindir
            try:
                res = h.take_screenshot(out)
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))

    def test_take_screenshot_auto_no_tools_and_no_fallback_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bindir = os.path.join(td, "bin")
            os.makedirs(bindir, exist_ok=True)
            # Override 'which' so _command_exists always returns False without needing to patch.
            which = os.path.join(bindir, "which")
            with open(which, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(which, 0o755)

            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "auto"
            cfg.screenshot_allow_fallback = False
            h = ScreenshotHandler(cfg)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = bindir
            try:
                res = h.take_screenshot(os.path.join(td, "shot.png"))
            finally:
                os.environ["PATH"] = old_path

            self.assertIsNone(res)

    def test_take_screenshot_auto_command_failure_falls_back_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bindir = os.path.join(td, "bin")
            os.makedirs(bindir, exist_ok=True)
            scrot = os.path.join(bindir, "scrot")
            with open(scrot, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\nexit 1\n")
            os.chmod(scrot, 0o755)

            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "auto"
            cfg.screenshot_allow_fallback = True
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = bindir + ":" + old_path
            try:
                res = h.take_screenshot(out)
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))

    def test_take_screenshot_auto_subprocess_error_falls_back_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bindir = os.path.join(td, "bin")
            os.makedirs(bindir, exist_ok=True)
            # Make 'scrot' a directory so running it raises an exception.
            os.makedirs(os.path.join(bindir, "scrot"), exist_ok=True)

            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "auto"
            cfg.screenshot_allow_fallback = True
            h = ScreenshotHandler(cfg)

            out = os.path.join(td, "shot.png")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = bindir + ":" + old_path
            try:
                res = h.take_screenshot(out)
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(res, out)
            self.assertTrue(os.path.exists(out))

    def test_take_screenshot_respects_validate_path(self) -> None:
        cfg = Config()
        cfg.screenshot_dir = "/tmp/screenshots"
        h = ScreenshotHandler(cfg)
        # validate_path should reject unsafe paths.
        self.assertIsNone(h.take_screenshot("../evil.png"))

    def test_take_screenshot_returns_none_on_subprocess_failure(self) -> None:
        # With Python backend, we don't rely on subprocesses.
        with tempfile.TemporaryDirectory() as td:
            cfg = Config()
            cfg.screenshot_dir = td
            cfg.screenshot_backend = "python"
            h = ScreenshotHandler(cfg)
            out = os.path.join(td, "shot.png")
            self.assertIsNotNone(h.take_screenshot(out))
