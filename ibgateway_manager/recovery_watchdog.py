"""Automatic in-container recovery for a genuinely-dead IB Gateway.

The orchestrator runs login automation **once** at cold start, then blocks on
the gateway process. After IB Gateway's nightly auto-restart it can come back to
a blank/black screen with the API port down — and nothing re-drives login, so it
sits dead until a human runs the ``restart_gateway`` / ``automate_login`` MCP
tools. The Docker HEALTHCHECK detects this (exit 1 once TCP is also down) but
HEALTHCHECK never restarts anything on its own.

This watchdog closes that loop. It polls the API port and, once it has been
**down for ``fail_threshold`` consecutive checks** — meaning the Java process is
genuinely gone, not a transient login/MFA/blank-window moment — it triggers a
restart + re-login via the orchestrator's ``recover_gateway()``.

Conservative by design: each recovery relaunch pushes a fresh MFA to the
operator's phone, so it acts only on a *sustained* TCP-down and then holds a
cooldown before it will act again. This mirrors the HEALTHCHECK's own
philosophy (it only fails when TCP is also down — a visually-unhealthy gateway
whose port is still up is treated as "in login/recovery, don't touch").

Tuning (env vars, all optional):
  IBGATEWAY_WATCHDOG_ENABLED            on/off (default on)
  IBGATEWAY_WATCHDOG_POLL_SECONDS       poll cadence (default 30)
  IBGATEWAY_WATCHDOG_FAIL_THRESHOLD     consecutive down checks before acting (default 5 → ~2.5 min)
  IBGATEWAY_WATCHDOG_COOLDOWN_SECONDS   min seconds between recoveries (default 900)
  IBGATEWAY_WATCHDOG_TCP_TIMEOUT_SECONDS per-probe TCP timeout (default 1.5)
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from .healthcheck import HealthcheckConfig, _port_for_trading_mode, check_tcp_listening


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (ValueError, AttributeError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (ValueError, AttributeError):
        return default


def watchdog_enabled_from_env() -> bool:
    return os.getenv("IBGATEWAY_WATCHDOG_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


class RecoveryWatchdog:
    """Background thread that auto-restarts a dead IB Gateway.

    The decision logic lives in :meth:`_tick`, which is pure enough to unit-test
    by injecting ``is_tcp_up`` / ``recover`` / ``clock`` — no threads or sleeps.
    """

    def __init__(
        self,
        *,
        is_tcp_up: Callable[[], bool],
        recover: Callable[[str], object],
        log: Callable[[str], None],
        poll_interval: float = 30.0,
        fail_threshold: int = 5,
        cooldown_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._is_tcp_up = is_tcp_up
        self._recover = recover
        self._log = log
        self.poll_interval = poll_interval
        self.fail_threshold = max(1, fail_threshold)
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock

        self._consecutive_down = 0
        self._last_recovery_at: Optional[float] = None
        self._cooldown_logged = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def from_config(
        cls,
        config,
        *,
        recover: Callable[[str], object],
        log: Callable[[str], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> "RecoveryWatchdog":
        port = _port_for_trading_mode(config.trading_mode)
        tcp_timeout = _env_float("IBGATEWAY_WATCHDOG_TCP_TIMEOUT_SECONDS", 1.5)

        def is_tcp_up() -> bool:
            return check_tcp_listening(
                HealthcheckConfig(host="127.0.0.1", port=port, timeout_seconds=tcp_timeout)
            )

        return cls(
            is_tcp_up=is_tcp_up,
            recover=recover,
            log=log,
            poll_interval=_env_float("IBGATEWAY_WATCHDOG_POLL_SECONDS", 30.0),
            fail_threshold=_env_int("IBGATEWAY_WATCHDOG_FAIL_THRESHOLD", 5),
            cooldown_seconds=_env_float("IBGATEWAY_WATCHDOG_COOLDOWN_SECONDS", 900.0),
            clock=clock,
        )

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="ibgw-recovery-watchdog", daemon=True
        )
        self._thread.start()
        self._log(
            f"recovery watchdog started (poll={self.poll_interval:.0f}s, "
            f"fail_threshold={self.fail_threshold}, "
            f"cooldown={self.cooldown_seconds:.0f}s)"
        )

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        # wait() returns True the instant stop is set, so the loop exits
        # promptly on shutdown instead of sleeping out the interval.
        while not self._stop.wait(self.poll_interval):
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 — never let the loop die
                self._log(f"recovery watchdog: tick error (ignored): {exc}")

    # ── decision logic (unit-tested) ───────────────────────────────────

    def _tick(self) -> bool:
        """One probe. Returns True iff a recovery was triggered this tick."""
        if self._is_tcp_up():
            if self._consecutive_down:
                self._log("recovery watchdog: API port back up — clearing fail counter")
            self._consecutive_down = 0
            self._cooldown_logged = False
            return False

        self._consecutive_down += 1
        self._log(
            f"recovery watchdog: API port DOWN "
            f"({self._consecutive_down}/{self.fail_threshold})"
        )
        if self._consecutive_down < self.fail_threshold:
            return False

        # Sustained down — the process is genuinely gone. Respect the cooldown
        # so a slow relaunch doesn't get re-killed mid-boot (and to bound MFA
        # pushes to at most one per cooldown window).
        now = self._clock()
        if (
            self._last_recovery_at is not None
            and (now - self._last_recovery_at) < self.cooldown_seconds
        ):
            if not self._cooldown_logged:
                remaining = self.cooldown_seconds - (now - self._last_recovery_at)
                self._log(
                    f"recovery watchdog: gateway still down but in cooldown "
                    f"(~{remaining:.0f}s left) — not restarting yet"
                )
                self._cooldown_logged = True
            return False

        reason = (
            f"API port down for {self._consecutive_down} consecutive checks "
            f"(~{self._consecutive_down * self.poll_interval:.0f}s)"
        )
        self._log(f"recovery watchdog: TRIGGERING recovery — {reason}")
        try:
            self._recover(reason)
        finally:
            self._last_recovery_at = self._clock()
            self._consecutive_down = 0
            self._cooldown_logged = False
        return True
