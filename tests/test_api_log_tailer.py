"""Tests for ibgateway_manager.api_log_tailer.

End-to-end (the integration path is the whole point): write fake
``api.*.log`` files into a temp Jts tree, run the tailer's discovery
+ tail step, append lines to the source files, and assert they end up
in the sink file.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from ibgateway_manager.api_log_tailer import ApiLogTailer


def _wait_for(predicate, timeout=5.0, interval=0.05) -> bool:
    """Spin until predicate() is truthy or timeout elapses. Returns last value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    return predicate()


class TestApiLogTailer(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.mkdtemp()
        self.jts = Path(self.td) / "Jts"
        self.jts.mkdir()
        self.sink = Path(self.td) / "sink.log"
        self.tailer: ApiLogTailer | None = None

    def tearDown(self) -> None:
        if self.tailer is not None:
            self.tailer.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def _new_tailer(self, **overrides) -> ApiLogTailer:
        # Use a tight poll interval so tests don't drag.
        params = dict(
            jts_dir=str(self.jts),
            sink_path=str(self.sink),
            poll_interval_seconds=0.1,
        )
        params.update(overrides)
        self.tailer = ApiLogTailer(**params)
        return self.tailer

    # ---- start/stop ----------------------------------------------------

    def test_start_creates_sink_file(self) -> None:
        self._new_tailer().start()
        self.assertTrue(self.sink.is_file())

    def test_double_start_does_not_spawn_two_threads(self) -> None:
        t = self._new_tailer()
        t.start()
        t.start()  # second call is a no-op
        # If a second thread were spawned, we'd have two named "api-log-tailer".
        # threading._active is private; instead probe via thread attribute.
        self.assertTrue(t._thread is not None and t._thread.is_alive())

    def test_stop_kills_tail_subprocesses(self) -> None:
        account = self.jts / "acct"
        account.mkdir()
        (account / "api.20260512.log").write_text("hello\n")
        t = self._new_tailer()
        t.start()
        self.assertTrue(_wait_for(lambda: len(t._tail_procs) >= 1))
        procs = list(t._tail_procs)
        t.stop()
        # All children should be terminated within a moment.
        for proc in procs:
            self.assertTrue(_wait_for(lambda p=proc: p.poll() is not None, timeout=3.0))

    # ---- discovery + tailing -------------------------------------------

    def test_discovers_log_file_already_present(self) -> None:
        account = self.jts / "acct1"
        account.mkdir()
        log = account / "api.20260512.log"
        log.write_text("initial line\n")
        self._new_tailer().start()
        self.assertTrue(
            _wait_for(lambda: "initial line" in self.sink.read_text())
        )

    def test_discovers_log_file_created_after_start(self) -> None:
        self._new_tailer().start()
        time.sleep(0.2)  # tailer makes a first scan with nothing
        account = self.jts / "acct1"
        account.mkdir()
        log = account / "api.20260512.log"
        log.write_text("late line\n")
        self.assertTrue(
            _wait_for(lambda: "late line" in self.sink.read_text())
        )

    def test_picks_up_lines_appended_after_tailing_started(self) -> None:
        account = self.jts / "acct1"
        account.mkdir()
        log = account / "api.20260512.log"
        log.write_text("first\n")
        self._new_tailer().start()
        self.assertTrue(_wait_for(lambda: "first" in self.sink.read_text()))
        # Append a new line — tail -F should pick it up.
        with log.open("a") as f:
            f.write("second\n")
        self.assertTrue(_wait_for(lambda: "second" in self.sink.read_text()))

    def test_each_log_file_tailed_only_once(self) -> None:
        account = self.jts / "acct1"
        account.mkdir()
        (account / "api.20260512.log").write_text("one\n")
        t = self._new_tailer()
        t.start()
        self.assertTrue(_wait_for(lambda: len(t._tail_procs) >= 1))
        first_count = len(t._tail_procs)
        # Force several more scans
        time.sleep(0.5)
        self.assertEqual(first_count, len(t._tail_procs))

    def test_handles_new_log_file_for_rotated_day(self) -> None:
        account = self.jts / "acct1"
        account.mkdir()
        (account / "api.20260511.log").write_text("yesterday\n")
        t = self._new_tailer()
        t.start()
        self.assertTrue(_wait_for(lambda: "yesterday" in self.sink.read_text()))
        # Day rolled over — new file appears.
        (account / "api.20260512.log").write_text("today\n")
        self.assertTrue(_wait_for(lambda: "today" in self.sink.read_text()))
        self.assertEqual(len(t._tail_procs), 2)

    def test_ignores_non_matching_files(self) -> None:
        account = self.jts / "acct1"
        account.mkdir()
        (account / "ibgateway.20260512.ibgzenc").write_text("encrypted blob\n")
        (account / "language.jar").write_text("jar content\n")
        # Restrict globs so we don't pick up launcher.log default.
        t = self._new_tailer(log_globs=("api.*.log",))
        t.start()
        time.sleep(0.3)
        # No api.*.log files in the tree → no tails spawned.
        self.assertEqual(len(t._tail_procs), 0)
        self.assertNotIn("encrypted blob", self.sink.read_text())
        self.assertNotIn("jar content", self.sink.read_text())

    # ---- top-level discovery (launcher.log) ----------------------------

    def test_discovers_launcher_log_at_top_level(self) -> None:
        """launcher.log lives at /root/Jts/launcher.log, not under an
        account subdir. The scan should pick it up."""
        (self.jts / "launcher.log").write_text("gateway booting\n")
        self._new_tailer().start()
        self.assertTrue(
            _wait_for(lambda: "gateway booting" in self.sink.read_text())
        )

    def test_discovers_launcher_log_and_api_log_in_same_scan(self) -> None:
        """Both files appear together in a single discovery pass — sink
        ends up with content from both streams."""
        (self.jts / "launcher.log").write_text("LAUNCHER LINE\n")
        account = self.jts / "acct1"
        account.mkdir()
        (account / "api.20260512.log").write_text("API LINE\n")
        t = self._new_tailer()
        t.start()
        self.assertTrue(_wait_for(
            lambda: "LAUNCHER LINE" in self.sink.read_text()
            and "API LINE" in self.sink.read_text()
        ))
        self.assertEqual(len(t._tail_procs), 2)

    # ---- on_tail_started callback --------------------------------------

    def test_on_tail_started_invoked_per_discovered_file(self) -> None:
        (self.jts / "launcher.log").write_text("a\n")
        account = self.jts / "acct1"
        account.mkdir()
        (account / "api.20260512.log").write_text("b\n")

        invoked: list = []
        self._new_tailer(on_tail_started=invoked.append).start()

        self.assertTrue(_wait_for(lambda: len(invoked) == 2))
        names = sorted(p.name for p in invoked)
        self.assertEqual(names, ["api.20260512.log", "launcher.log"])

    def test_on_tail_started_callback_exception_is_swallowed(self) -> None:
        (self.jts / "launcher.log").write_text("hello\n")

        def _boom(_path):
            raise RuntimeError("callback exploded")

        t = self._new_tailer(on_tail_started=_boom)
        t.start()
        # File still gets tailed despite callback raising.
        self.assertTrue(_wait_for(lambda: "hello" in self.sink.read_text()))

    def test_handles_missing_jts_dir_at_start(self) -> None:
        """First-boot: orchestrator starts the tailer before IB Gateway
        has created its Jts subtree. We shouldn't crash."""
        shutil.rmtree(self.jts)
        self._new_tailer().start()
        time.sleep(0.3)
        # No crash; sink still exists.
        self.assertTrue(self.sink.is_file())


if __name__ == "__main__":
    unittest.main()
