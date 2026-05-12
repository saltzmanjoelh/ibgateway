"""Background watcher that streams IB Gateway's plaintext logs into a
single sink file the orchestrator already tails to stdout.

IB Gateway writes two plaintext log streams worth capturing:

  * ``~/Jts/launcher.log`` — system/JVM-level events (restart markers,
    config init, FX-thread errors). Lives at the top level of the Jts
    dir, always present, single file (no rotation).
  * ``~/Jts/<account-encoded-id>/api.YYYYMMDD.log`` — API protocol
    traffic. Only appears once ``WriteAPIMessages``/``LogFile`` are on
    in jts.ini (see :mod:`ibgateway_manager.jts_log_config`) AND the
    user has logged in. The per-account subdir name is opaque and the
    filename rotates daily.

We deal with the variability by running a tiny poller thread that
scans the Jts tree every 30 seconds, matches both shapes, and spawns
one ``tail -F`` per discovered file appending to a single sink. The
orchestrator already includes the sink in its tail-to-stdout set, so
each line lands in ``docker logs`` / CloudWatch.

Intentionally simple — ``tail -F`` handles file rotation, mid-write
reads, and the case where the file disappears and reappears. We never
read the file contents directly from Python.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set

_logger = logging.getLogger(__name__)


class ApiLogTailer:
    """Poll a Jts directory tree and tail new ``api.*.log`` files."""

    def __init__(
        self,
        jts_dir: str = "/root/Jts",
        sink_path: str = "/tmp/ibgateway-api.log",
        poll_interval_seconds: float = 30.0,
        log_globs: Iterable[str] = ("api.*.log", "launcher.log"),
        on_tail_started: Optional["Callable[[Path], None]"] = None,
    ) -> None:
        self.jts_dir = Path(jts_dir)
        self.sink_path = Path(sink_path)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.log_globs = tuple(log_globs)
        self.on_tail_started = on_tail_started
        self._tailed_files: Set[Path] = set()
        self._tail_procs: List[subprocess.Popen] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Begin polling. Returns immediately; work happens on a daemon thread."""
        self.sink_path.parent.mkdir(parents=True, exist_ok=True)
        self.sink_path.touch(exist_ok=True)
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="api-log-tailer", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and kill any tail subprocesses we spawned."""
        self._stop.set()
        for proc in self._tail_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        # Wait briefly so children finalize cleanly — keeps Python's GC
        # from later flagging ResourceWarning on unfinished Popens, and
        # makes sure /proc handles are released before the test runner
        # tears down its tempdir.
        for proc in self._tail_procs:
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        # Best-effort join so the test suite doesn't leak threads.
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ----- internals ----------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_and_tail_new()
            except Exception:
                _logger.exception("api-log-tailer scan failed")
            # wait() returns True if stop was set; we just use it for sleep.
            self._stop.wait(timeout=self.poll_interval_seconds)

    def _scan_and_tail_new(self) -> None:
        new_files = self._discover_new_logs()
        for log_file in new_files:
            self._tail_one(log_file)

    def _discover_new_logs(self) -> List[Path]:
        if not self.jts_dir.is_dir():
            return []
        discovered: List[Path] = []
        # Scan top-level first (catches launcher.log) then each account subdir
        # (catches api.YYYYMMDD.log). Glob each directory against all patterns
        # — patterns that don't match at a given level just return no files.
        scan_dirs = [self.jts_dir] + [
            d for d in sorted(self.jts_dir.iterdir()) if d.is_dir()
        ]
        for scan_dir in scan_dirs:
            for pattern in self.log_globs:
                for log_file in sorted(scan_dir.glob(pattern)):
                    if log_file in self._tailed_files:
                        continue
                    discovered.append(log_file)
        return discovered

    def _tail_one(self, log_file: Path) -> None:
        # ``tail -F`` follows by name (handles rotation / re-creation) and
        # retries when the file is missing. ``-n +1`` starts from the top
        # so we never miss the early connect handshake lines just because
        # this tailer woke up late.
        sink = self.sink_path.open("ab")
        try:
            proc = subprocess.Popen(
                ["tail", "-F", "-n", "+1", str(log_file)],
                stdout=sink,
                stderr=subprocess.DEVNULL,
            )
        finally:
            # The child inherits the file descriptor; we close our copy
            # so the sink isn't held open by the parent for no reason.
            sink.close()
        self._tail_procs.append(proc)
        self._tailed_files.add(log_file)
        _logger.info("api-log-tailer: now tailing %s", log_file)
        if self.on_tail_started is not None:
            try:
                self.on_tail_started(log_file)
            except Exception:
                _logger.exception("on_tail_started callback raised")
