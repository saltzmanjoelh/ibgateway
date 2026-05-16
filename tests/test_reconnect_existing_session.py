"""Tests for AutomationHandler.reconnect_existing_session.

Covers the recovery flow for the EXISTING SESSION DETECTED modal — the
gateway puts that up when IBKR's auth server already sees another active
session for the same credentials (typical when the operator switches
between local docker-compose and the ECS task).

Like the other automation flows the actual xdotool keystrokes are
untestable end-to-end without a live Xvfb. What we can pin down is:

* the search → activate → Return sequence fires in the right order,
* alternate window-name needles are tried before giving up,
* missing-modal returns exit 1 without calling Return.

Strategy: patch ``run_xdotool`` to collect every (args) tuple and stub
its return values for the "search" calls so we can simulate
modal-found vs not-found.
"""
from __future__ import annotations

import unittest
import unittest.mock as mock

from ibgateway_manager.automate_ibgateway import AutomationHandler


class _FakeConfig:
    """Minimal stand-in for Config — AutomationHandler.__init__ touches
    a couple of attrs (verbose flag, display) and constructs a
    ScreenshotHandler which we mock out at the patch level."""

    def __init__(self, display: str = ":99") -> None:
        self.display = display
        # AutomationHandler stores these on self but never reads them in
        # the reconnect_existing_session path. Defaults keep the
        # constructor happy if anything is touched.
        self.username = ""
        self.password = ""
        self.api_type = "IB_API"
        self.trading_mode = "PAPER"


class ReconnectExistingSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Suppress the screenshot handler ctor side effects.
        patcher = mock.patch("ibgateway_manager.automate_ibgateway.ScreenshotHandler")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.handler = AutomationHandler(_FakeConfig(), verbose=False)

    def _build_xdotool_mock(self, search_results: dict[str, str | None]):
        """Build a run_xdotool side-effect that returns canned strings for
        ``search --name <needle>`` and a no-op for everything else.

        Records every call as a tuple of positional args for assertions.
        """
        calls: list[tuple] = []

        def fake_xdotool(*args):
            calls.append(args)
            if len(args) >= 3 and args[0] == "search" and args[1] == "--name":
                return search_results.get(args[2])
            return ""

        return calls, fake_xdotool

    # ── happy path ────────────────────────────────────────────────────

    def test_modal_found_first_needle_clicks_return(self):
        """The most common case: the canonical 'EXISTING SESSION DETECTED'
        title matches on the first try → activate + Return."""
        calls, fake = self._build_xdotool_mock(
            {"EXISTING SESSION DETECTED": "0x12345 SomeOtherWindowId"}
        )
        with mock.patch.object(self.handler, "run_xdotool", side_effect=fake):
            rc = self.handler.reconnect_existing_session()
        self.assertEqual(rc, 0)

        # Sequence: 1 search call, 1 windowactivate, 1 key Return.
        kinds = [c[0] for c in calls]
        self.assertEqual(kinds.count("search"), 1)
        self.assertIn(("windowactivate", "--sync", "0x12345"), calls)
        self.assertIn(("key", "Return"), calls)

    def test_modal_found_only_on_alternate_needle(self):
        """If the canonical title misses but 'Existing Session' matches
        (older IB Gateway variant), fall through and still succeed."""
        calls, fake = self._build_xdotool_mock(
            {
                "EXISTING SESSION DETECTED": None,
                "EXISTING SESSION": None,
                "Existing Session": "0xABCDE",
            }
        )
        with mock.patch.object(self.handler, "run_xdotool", side_effect=fake):
            rc = self.handler.reconnect_existing_session()
        self.assertEqual(rc, 0)

        # All three needles got tried in order before the match.
        searches = [c[2] for c in calls if c[0] == "search"]
        self.assertEqual(
            searches,
            ["EXISTING SESSION DETECTED", "EXISTING SESSION", "Existing Session"],
        )
        self.assertIn(("windowactivate", "--sync", "0xABCDE"), calls)
        self.assertIn(("key", "Return"), calls)

    # ── failure paths ─────────────────────────────────────────────────

    def test_no_modal_found_returns_one_and_does_not_press_return(self):
        """Nothing matching any of the needles → exit 1 and we must NOT
        send a stray Return, since that could click a different focused
        thing on the live display."""
        calls, fake = self._build_xdotool_mock({})  # no matches
        with mock.patch.object(self.handler, "run_xdotool", side_effect=fake):
            rc = self.handler.reconnect_existing_session()
        self.assertEqual(rc, 1)

        # All three needles tried, no activate, no key press.
        searches = [c[2] for c in calls if c[0] == "search"]
        self.assertEqual(
            searches,
            ["EXISTING SESSION DETECTED", "EXISTING SESSION", "Existing Session"],
        )
        self.assertFalse(any(c[0] == "windowactivate" for c in calls))
        self.assertFalse(any(c == ("key", "Return") for c in calls))

    def test_multi_window_search_result_picks_first_id(self):
        """``xdotool search`` can return multiple space-separated window
        IDs (one per matching window). We use the first only — confirm
        we don't accidentally feed the whole multi-id string to
        windowactivate."""
        calls, fake = self._build_xdotool_mock(
            {"EXISTING SESSION DETECTED": "0xFIRST 0xSECOND 0xTHIRD"}
        )
        with mock.patch.object(self.handler, "run_xdotool", side_effect=fake):
            rc = self.handler.reconnect_existing_session()
        self.assertEqual(rc, 0)
        self.assertIn(("windowactivate", "--sync", "0xFIRST"), calls)
        self.assertNotIn(
            ("windowactivate", "--sync", "0xFIRST 0xSECOND 0xTHIRD"),
            calls,
        )


if __name__ == "__main__":
    unittest.main()
