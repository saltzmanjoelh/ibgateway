"""Tests for the Docker HEALTHCHECK helper at ``ibgateway_manager.healthcheck``.

The interesting branches:

* visual healthy / degraded → exit 0 (no TCP probe).
* visual unhealthy + TCP up → exit 0 (the lenient-fallback path — gateway is
  on a login dialog or in daily-recovery, NOT a dead Java process; ECS
  must not restart because each restart fires an MFA push).
* visual unhealthy + TCP down → exit 1 (Java process actually dead).
* visual unavailable + TCP up → exit 0 (early startup).
* visual unavailable + TCP down → exit 1.

The visual + TCP checks are mocked at the module-level so we don't need
an actual screenshot server or socket listener.
"""
from __future__ import annotations

import unittest
import unittest.mock as mock

from ibgateway_manager import healthcheck


def _cfg() -> healthcheck.HealthcheckConfig:
    return healthcheck.HealthcheckConfig(host="127.0.0.1", port=4002, timeout_seconds=1.5)


def _detail(overall: str, rows=None, error=None):
    """Shape returned by check_visual_health()'s second tuple element."""
    return {
        "overall": overall,
        "rows": rows or [],
        "screenshot_path": "/tmp/screenshots/x.png",
        "error": error,
    }


class HealthcheckMainTests(unittest.TestCase):
    def setUp(self) -> None:
        # Always inject a known config so we don't read env.
        self._cfg_patch = mock.patch.object(
            healthcheck, "build_config_from_env", return_value=_cfg()
        )
        self._cfg_patch.start()
        self.addCleanup(self._cfg_patch.stop)

    def _run(self, visual_status: str, tcp_ok: bool, detail=None) -> int:
        with mock.patch.object(
            healthcheck, "check_visual_health", return_value=(visual_status, detail)
        ), mock.patch.object(
            healthcheck, "check_tcp_listening", return_value=tcp_ok
        ) as tcp_mock:
            rc = healthcheck.main([])
        return rc, tcp_mock

    # ── happy paths (visual reports good state) ────────────────────────

    def test_visual_healthy_does_not_probe_tcp(self):
        rc, tcp_mock = self._run("healthy", tcp_ok=False, detail=_detail("healthy"))
        self.assertEqual(rc, 0)
        # Visual says healthy → no reason to even ask the TCP socket.
        tcp_mock.assert_not_called()

    def test_visual_degraded_does_not_probe_tcp(self):
        # "degraded" means API row green but some farm rows yellow — still OK.
        rc, tcp_mock = self._run("degraded", tcp_ok=False, detail=_detail("degraded"))
        self.assertEqual(rc, 0)
        tcp_mock.assert_not_called()

    # ── the lenient-fallback branch (the one we just added) ────────────

    def test_visual_unhealthy_but_tcp_up_returns_zero(self):
        """The whole point of the fallback: visual is unhealthy (gateway is on
        a login dialog or daily-recovery), but the Java process is alive on
        TCP. ECS must NOT restart in this state — each restart triggers a
        fresh MFA push."""
        rc, tcp_mock = self._run(
            "unhealthy", tcp_ok=True, detail=_detail("unhealthy", error="not green")
        )
        self.assertEqual(rc, 0)
        tcp_mock.assert_called_once()

    def test_visual_unhealthy_and_tcp_down_returns_one(self):
        """Both visual and TCP failed → Java process is genuinely dead. This
        is the only case where exit 1 from the unhealthy branch is correct."""
        rc, tcp_mock = self._run(
            "unhealthy", tcp_ok=False, detail=_detail("unhealthy", error="not green")
        )
        self.assertEqual(rc, 1)
        tcp_mock.assert_called_once()

    def test_visual_unhealthy_with_no_detail_dict_falls_back_to_tcp(self):
        """A None detail (screenshot server gave a malformed response) must
        not blow up the fallback branch — the code reads detail.get('error')
        defensively. TCP up still wins."""
        rc, _ = self._run("unhealthy", tcp_ok=True, detail=None)
        self.assertEqual(rc, 0)

    # ── the "unavailable" branch (existing pre-fallback behavior) ──────

    def test_visual_unavailable_but_tcp_up_returns_zero(self):
        """Early-startup case: screenshot server isn't up yet, but the
        gateway's API port is bound. Treat as healthy."""
        rc, tcp_mock = self._run("unavailable", tcp_ok=True, detail=None)
        self.assertEqual(rc, 0)
        tcp_mock.assert_called_once()

    def test_visual_unavailable_and_tcp_down_returns_one(self):
        rc, tcp_mock = self._run("unavailable", tcp_ok=False, detail=None)
        self.assertEqual(rc, 1)
        tcp_mock.assert_called_once()

    # ── config-failure branch ──────────────────────────────────────────

    def test_invalid_config_returns_one(self):
        with mock.patch.object(
            healthcheck,
            "build_config_from_env",
            side_effect=ValueError("bad mode"),
        ):
            rc = healthcheck.main([])
        self.assertEqual(rc, 1)


class PortMappingTests(unittest.TestCase):
    """Sanity-check the IB_TRADING_MODE → port mapping in case someone
    swaps the literals later — production CFN passes the env var, so any
    drift here surfaces as ECS reading the wrong port."""

    def test_live_maps_to_4001(self):
        self.assertEqual(healthcheck._port_for_trading_mode("LIVE"), 4001)

    def test_paper_maps_to_4002(self):
        self.assertEqual(healthcheck._port_for_trading_mode("PAPER"), 4002)

    def test_lowercase_is_normalized(self):
        self.assertEqual(healthcheck._port_for_trading_mode("paper"), 4002)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            healthcheck._port_for_trading_mode("DEMO")


if __name__ == "__main__":
    unittest.main()
