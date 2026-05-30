"""Tests for the in-container recovery watchdog.

The decision logic (``RecoveryWatchdog._tick``) is exercised directly with
injected ``is_tcp_up`` / ``recover`` / ``clock`` — no threads, no sleeps, no
sockets. A small lifecycle smoke test covers start()/stop().
"""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ibgateway_manager.recovery_watchdog import (
    RecoveryWatchdog,
    watchdog_enabled_from_env,
)


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _make(is_up, recover, clock=None, *, fail_threshold=3, cooldown=600.0, poll=30.0):
    return RecoveryWatchdog(
        is_tcp_up=is_up,
        recover=recover,
        log=lambda _m: None,
        poll_interval=poll,
        fail_threshold=fail_threshold,
        cooldown_seconds=cooldown,
        clock=clock or _Clock(),
    )


class RecoveryWatchdogTickTests(unittest.TestCase):
    def test_tcp_up_never_recovers(self):
        recover = MagicMock()
        wd = _make(lambda: True, recover)
        for _ in range(10):
            self.assertFalse(wd._tick())
        recover.assert_not_called()
        self.assertEqual(wd._consecutive_down, 0)

    def test_below_threshold_does_not_recover(self):
        recover = MagicMock()
        wd = _make(lambda: False, recover, fail_threshold=3)
        self.assertFalse(wd._tick())  # 1/3
        self.assertFalse(wd._tick())  # 2/3
        recover.assert_not_called()

    def test_recovers_after_threshold_consecutive_down(self):
        recover = MagicMock()
        wd = _make(lambda: False, recover, fail_threshold=3, poll=30.0)
        self.assertFalse(wd._tick())
        self.assertFalse(wd._tick())
        self.assertTrue(wd._tick())  # 3/3 → recover
        recover.assert_called_once()
        reason = recover.call_args.args[0]
        self.assertIn("down", reason.lower())
        self.assertIn("3", reason)  # mentions the consecutive-down count
        self.assertEqual(wd._consecutive_down, 0)  # reset after recovery

    def test_intermittent_up_resets_counter(self):
        state = {"up": False}
        recover = MagicMock()
        wd = _make(lambda: state["up"], recover, fail_threshold=3)
        wd._tick()  # down 1
        wd._tick()  # down 2
        state["up"] = True
        wd._tick()  # up → reset
        self.assertEqual(wd._consecutive_down, 0)
        state["up"] = False
        wd._tick()  # down 1 again
        wd._tick()  # down 2 — never reached 3 consecutive
        recover.assert_not_called()

    def test_cooldown_blocks_repeat_then_allows_after_expiry(self):
        clock = _Clock()
        recover = MagicMock()
        wd = _make(lambda: False, recover, clock, fail_threshold=2, cooldown=600.0)
        wd._tick()
        self.assertTrue(wd._tick())  # first recovery at threshold 2
        self.assertEqual(recover.call_count, 1)

        # Still down, within cooldown → no further recovery even as the counter
        # climbs back past the threshold.
        for _ in range(5):
            self.assertFalse(wd._tick())
        self.assertEqual(recover.call_count, 1)

        clock.advance(601)  # past cooldown
        self.assertTrue(wd._tick())
        self.assertEqual(recover.call_count, 2)

    def test_recover_exception_still_arms_cooldown(self):
        clock = _Clock()
        recover = MagicMock(side_effect=RuntimeError("boom"))
        wd = _make(lambda: False, recover, clock, fail_threshold=1, cooldown=600.0)
        with self.assertRaises(RuntimeError):
            wd._tick()
        # finally-block ran: counter reset + cooldown armed so the loop won't
        # immediately retry on the next tick.
        self.assertEqual(wd._consecutive_down, 0)
        self.assertIsNotNone(wd._last_recovery_at)

    def test_from_config_paper_probes_4002(self):
        captured = {}

        def fake_check(cfg):
            captured["port"] = cfg.port
            return True

        with patch.object(
            __import__("ibgateway_manager.recovery_watchdog", fromlist=["check_tcp_listening"]),
            "check_tcp_listening",
            fake_check,
        ):
            cfg = SimpleNamespace(trading_mode="PAPER")
            wd = RecoveryWatchdog.from_config(cfg, recover=MagicMock(), log=lambda _m: None)
            wd._tick()
        self.assertEqual(captured["port"], 4002)

    def test_from_config_live_probes_4001(self):
        captured = {}

        def fake_check(cfg):
            captured["port"] = cfg.port
            return True

        with patch.object(
            __import__("ibgateway_manager.recovery_watchdog", fromlist=["check_tcp_listening"]),
            "check_tcp_listening",
            fake_check,
        ):
            cfg = SimpleNamespace(trading_mode="LIVE")
            wd = RecoveryWatchdog.from_config(cfg, recover=MagicMock(), log=lambda _m: None)
            wd._tick()
        self.assertEqual(captured["port"], 4001)


class RecoveryWatchdogLifecycleTests(unittest.TestCase):
    def test_start_stop_thread(self):
        recover = MagicMock()
        wd = _make(lambda: True, recover, poll=0.01)  # always up → never recovers
        wd.start()
        self.assertIsNotNone(wd._thread)
        time.sleep(0.05)  # let it spin a few times
        wd.stop()
        self.assertIsNone(wd._thread)
        recover.assert_not_called()
        # No leaked watchdog threads.
        self.assertNotIn(
            "ibgw-recovery-watchdog", [t.name for t in threading.enumerate()]
        )

    def test_double_start_is_idempotent(self):
        wd = _make(lambda: True, MagicMock(), poll=0.01)
        wd.start()
        first = wd._thread
        wd.start()  # no-op
        self.assertIs(wd._thread, first)
        wd.stop()


class WatchdogEnabledEnvTests(unittest.TestCase):
    def test_default_enabled(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("IBGATEWAY_WATCHDOG_ENABLED", None)
            self.assertTrue(watchdog_enabled_from_env())

    def test_explicit_disable(self):
        with patch.dict("os.environ", {"IBGATEWAY_WATCHDOG_ENABLED": "false"}):
            self.assertFalse(watchdog_enabled_from_env())


if __name__ == "__main__":
    unittest.main()
