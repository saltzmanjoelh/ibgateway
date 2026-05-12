"""Tests for ibgateway_manager.api_traffic_capture.

The module wraps tcpdump as a subprocess. Tests use a small ``fake_tcpdump``
shell script that emits known content and then idles, so we exercise the
real subprocess plumbing without requiring tcpdump to be installed and
without needing NET_RAW capability.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from ibgateway_manager.api_traffic_capture import ApiTrafficCapture


def _wait_for(predicate, timeout=3.0, interval=0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestApiTrafficCapture(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.mkdtemp()
        self.sink = Path(self.td) / "api-traffic.log"
        # Build a fake tcpdump that emits some lines and then sleeps.
        # Real tcpdump emits one packet per line and stays alive; this
        # mirrors the lifecycle the orchestrator depends on.
        self.fake = Path(self.td) / "fake_tcpdump"
        self.fake.write_text(
            "#!/bin/sh\n"
            "echo 'CAPTURE_START args:' \"$@\"\n"
            "echo '12:34:56.789 IP 127.0.0.1.59123 > 127.0.0.1.4002: ...'\n"
            "echo '<- [20;1;0;AAPL;STK;;;;SMART;NASDAQ;USD;;;0]'\n"
            "echo '-> [17;1;5;20260410 11:00:00 US/Eastern;261.75;...]'\n"
            "sleep 300\n"
        )
        self.fake.chmod(stat.S_IRWXU)
        self.cap: ApiTrafficCapture | None = None

    def tearDown(self) -> None:
        if self.cap is not None:
            self.cap.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def _new(self, **overrides) -> ApiTrafficCapture:
        params = dict(
            sink_path=str(self.sink),
            ports=(4002,),
            tcpdump_path=str(self.fake),
        )
        params.update(overrides)
        self.cap = ApiTrafficCapture(**params)
        return self.cap

    # ---- start / stop --------------------------------------------------

    def test_start_returns_true_when_tcpdump_present(self) -> None:
        self.assertTrue(self._new().start())

    def test_start_creates_sink_file(self) -> None:
        self._new().start()
        self.assertTrue(self.sink.is_file())

    def test_start_returns_false_when_tcpdump_missing(self) -> None:
        cap = self._new(tcpdump_path="/nonexistent/tcpdump")
        self.assertFalse(cap.start())
        # Falsy start means no subprocess was spawned.
        self.assertFalse(cap.is_running())

    def test_is_running_true_after_start(self) -> None:
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(lambda: c.is_running()))

    def test_pid_populated_after_start(self) -> None:
        c = self._new()
        c.start()
        self.assertIsInstance(c.pid, int)
        self.assertGreater(c.pid, 0)

    def test_stop_terminates_subprocess(self) -> None:
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(lambda: c.is_running()))
        c.stop()
        self.assertFalse(c.is_running())

    def test_stop_is_idempotent(self) -> None:
        c = self._new()
        c.start()
        c.stop()
        c.stop()  # second call must not raise

    def test_stop_before_start_is_safe(self) -> None:
        # No start() called — stop() must be a no-op rather than crash.
        c = self._new()
        c.stop()

    # ---- output --------------------------------------------------------

    def test_subprocess_output_goes_to_sink(self) -> None:
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(
            lambda: "CAPTURE_START" in self.sink.read_text()
        ))
        content = self.sink.read_text()
        self.assertIn("<- [20;1;0;AAPL", content)
        self.assertIn("-> [17;1;5;20260410", content)

    def test_argv_contains_port_filter(self) -> None:
        """Verify the constructed argv carries the port filter we expect."""
        c = self._new(ports=(4001, 4002))
        c.start()
        self.assertTrue(_wait_for(
            lambda: "CAPTURE_START args:" in self.sink.read_text()
        ))
        first_line = self.sink.read_text().splitlines()[0]
        # The fake echoes its argv after "args:" — confirm the filter is there.
        self.assertIn("port 4001 or port 4002", first_line)

    def test_argv_uses_line_buffering_flag(self) -> None:
        """Without -l, tcpdump batches output and CloudWatch lags by minutes.
        Regression guard: -l must be in the argv."""
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(
            lambda: "CAPTURE_START args:" in self.sink.read_text()
        ))
        first_line = self.sink.read_text().splitlines()[0]
        self.assertIn(" -l ", " " + first_line + " ")

    def test_argv_captures_full_packet(self) -> None:
        """Without -s 0, tcpdump truncates at 96 bytes and we lose
        most of the IBKR payload."""
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(
            lambda: "CAPTURE_START args:" in self.sink.read_text()
        ))
        first_line = self.sink.read_text().splitlines()[0]
        self.assertIn("-s 0", first_line)

    # ---- port resolution -----------------------------------------------

    def test_default_ports_is_paper_only(self) -> None:
        """Default must be just 4002 — capturing 4001 would pull in
        unreadable gateway↔IBKR-CCP TLS noise at 17:1 ratio (verified
        empirically against the live container)."""
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IBGATEWAY_API_TRAFFIC_PORTS", None)
            c = ApiTrafficCapture(tcpdump_path=str(self.fake))
            self.assertEqual(c.ports, (4002,))

    def test_env_var_overrides_default_ports(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_API_TRAFFIC_PORTS": "4001"}
        ):
            c = ApiTrafficCapture(tcpdump_path=str(self.fake))
            self.assertEqual(c.ports, (4001,))

    def test_env_var_accepts_comma_separated_list(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_API_TRAFFIC_PORTS": "4001, 4002, 7497"}
        ):
            c = ApiTrafficCapture(tcpdump_path=str(self.fake))
            self.assertEqual(c.ports, (4001, 4002, 7497))

    def test_malformed_env_var_falls_back_to_default(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"IBGATEWAY_API_TRAFFIC_PORTS": "abc,not,ints"}
        ):
            c = ApiTrafficCapture(tcpdump_path=str(self.fake))
            self.assertEqual(c.ports, (4002,))

    # ---- robustness ----------------------------------------------------

    def test_creates_sink_directory_if_missing(self) -> None:
        sink = Path(self.td) / "nested" / "dir" / "traffic.log"
        c = self._new(sink_path=str(sink))
        self.assertTrue(c.start())
        self.assertTrue(sink.is_file())

    def test_append_mode_preserves_existing_content(self) -> None:
        """Container restart cycles must preserve previous capture
        (sink is the tail target — overwriting would lose buffered tail)."""
        self.sink.write_text("PREVIOUS LINE\n")
        c = self._new()
        c.start()
        self.assertTrue(_wait_for(
            lambda: "CAPTURE_START" in self.sink.read_text()
        ))
        self.assertIn("PREVIOUS LINE", self.sink.read_text())


if __name__ == "__main__":
    unittest.main()
