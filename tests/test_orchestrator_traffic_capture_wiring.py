"""Regression guards for the orchestrator's ApiTrafficCapture wiring.

``ApiTrafficCapture`` is intentionally NOT gated by
``_log_capture_enabled()`` (the launcher.log tailer's trading-mode
gate). Its on/off state is decided at image-build time by the
``ENABLE_TCPDUMP`` Dockerfile arg:

  * default build: tcpdump absent → ``ApiTrafficCapture.start()``
    returns ``False`` and logs an informational line, regardless of
    trading mode or any runtime env var.
  * diagnostic build (``--build-arg ENABLE_TCPDUMP=true``): tcpdump
    present → capture starts.

If someone reintroduces the trading-mode gate on top of
ApiTrafficCapture, these tests fail loudly. The construction call AND
the .start() call must both live outside the
``if self._log_capture_enabled():`` block in orchestrator.start().

We pin the property via source inspection — far cheaper than mocking
out the full orchestrator startup, and the failure message is
actionable: "the ApiTrafficCapture block ended up under the trading-
mode gate again."
"""
from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from ibgateway_manager import orchestrator


class TestTrafficCaptureNotGatedByTradingMode(unittest.TestCase):
    """Walk ``orchestrator.start`` AST and confirm that
    ``ApiTrafficCapture()`` / ``self.api_traffic_capture.start()`` are
    NOT inside an ``if`` whose test references
    ``_log_capture_enabled`` or the ``log_capture_on`` local
    variable bound from it.
    """

    def _start_function_ast(self) -> ast.FunctionDef:
        src_path = Path(inspect.getsourcefile(orchestrator))
        tree = ast.parse(src_path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ClassDef)
                and node.name == "ServiceOrchestrator"
            ):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "start":
                        return child  # type: ignore[return-value]
        raise AssertionError("ServiceOrchestrator.start not found")

    def _under_log_capture_if(self, target: ast.AST, func: ast.FunctionDef) -> bool:
        """Is ``target`` inside an ``if log_capture_on:`` (or
        ``if self._log_capture_enabled():``) within ``func``?"""
        for if_node in [n for n in ast.walk(func) if isinstance(n, ast.If)]:
            cond = ast.unparse(if_node.test)
            if "log_capture_on" in cond or "_log_capture_enabled" in cond:
                # any target node inside this if's body / orelse?
                for branch in (if_node.body, if_node.orelse):
                    for branch_node in branch:
                        for sub in ast.walk(branch_node):
                            if sub is target:
                                return True
        return False

    def test_api_traffic_capture_constructor_not_gated(self) -> None:
        func = self._start_function_ast()
        # Find ``ApiTrafficCapture()`` calls inside the function body
        ctor_calls = [
            c for c in ast.walk(func)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "ApiTrafficCapture"
        ]
        self.assertTrue(
            ctor_calls,
            "ApiTrafficCapture() call missing from ServiceOrchestrator.start — "
            "the capture is wired into the orchestrator at start() time."
        )
        for call in ctor_calls:
            self.assertFalse(
                self._under_log_capture_if(call, func),
                "Regression: ApiTrafficCapture() is now inside an "
                "`if log_capture_on:` (or `_log_capture_enabled()`) block. "
                "The wire-protocol capture is supposed to be gated only "
                "by the ENABLE_TCPDUMP build arg (binary presence), not "
                "by trading mode. Remove the conditional and let the "
                "module's own missing-tcpdump fallback handle the "
                "default-image case.",
            )

    def test_api_traffic_capture_start_call_not_gated(self) -> None:
        func = self._start_function_ast()
        # Find ``self.api_traffic_capture.start()`` calls
        start_calls = [
            c for c in ast.walk(func)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "start"
            and isinstance(c.func.value, ast.Attribute)
            and c.func.value.attr == "api_traffic_capture"
        ]
        self.assertTrue(
            start_calls,
            "self.api_traffic_capture.start() call missing from "
            "ServiceOrchestrator.start — capture would never run."
        )
        for call in start_calls:
            self.assertFalse(
                self._under_log_capture_if(call, func),
                "Regression: self.api_traffic_capture.start() is now "
                "inside an `if log_capture_on:` block. See the sibling "
                "test for the constructor case — same reasoning."
            )

    def test_api_log_tailer_IS_still_gated(self) -> None:
        """Sanity-check the *other* pipeline: ``ApiLogTailer`` SHOULD
        remain gated by ``_log_capture_enabled()``. If both are
        ungated, we've lost the trading-mode protection on launcher.log
        too — which would leak real account balances in live mode."""
        func = self._start_function_ast()
        tailer_starts = [
            c for c in ast.walk(func)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "start"
            and isinstance(c.func.value, ast.Attribute)
            and c.func.value.attr == "api_log_tailer"
        ]
        self.assertTrue(
            tailer_starts,
            "self.api_log_tailer.start() call missing from "
            "ServiceOrchestrator.start — the launcher.log tailer would "
            "never run."
        )
        for call in tailer_starts:
            self.assertTrue(
                self._under_log_capture_if(call, func),
                "self.api_log_tailer.start() must remain inside the "
                "`if log_capture_on:` block — that's what prevents "
                "live-mode CCPDispatcher account-balance dumps from "
                "reaching CloudWatch by default.",
            )


if __name__ == "__main__":
    unittest.main()
