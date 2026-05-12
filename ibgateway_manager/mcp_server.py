"""
MCP server exposing IB Gateway features.

Streamable HTTP transport, bound to 127.0.0.1 by default. The trust boundary
is the SSM tunnel (or the local Docker network); there is no public network
path. (A bearer-token gate used to live here but the official MCP SDK's
FastMCP doesn't accept ``custom_middleware``; if reintroducing auth, build a
Starlette app from ``mcp.streamable_http_app()`` and wrap that.)

Tools:
  - get_screenshot                  Capture a fresh screenshot, return PNG image.
  - list_screenshots                List screenshots already on disk.
  - get_screenshot_by_name          Return an existing screenshot by filename.
  - get_connection_status           Visual analysis of the Connection Status table.
  - get_health                      Combined visual + TCP fallback status.
  - automate_login                  Run the xdotool-driven login/MFA flow.
  - retry_login_after_mfa_failure   Recovery for the post-MFA-failure dialog.
  - restart_gateway                 Kill and relaunch the IB Gateway process.
  - test_historical_data            Smoke-test IB API historical bars vs local Gateway.
  - get_gateway_logs                Tail one of the orchestrator log files.
"""

from __future__ import annotations

import base64
import glob
import io
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Image

from .automate_ibgateway import AutomationHandler
from .notify import notify_slack
from .config import Config
from .connection_status import check_connection_status
from .healthcheck import (
    build_config_from_env,
    check_tcp_listening,
    check_visual_health,
)
from .screenshot import ScreenshotHandler


_LOG_FILES = {
    "automate": "/tmp/automate-ibgateway.log",
    "screenshot-server": "/tmp/screenshot-server.log",
    "port-forward": "/tmp/port-forward.log",
    "x11vnc": "/tmp/x11vnc.log",
    "websockify": "/tmp/websockify.log",
    "mcp-server": "/tmp/mcp-server.log",
    "historical-data": "/tmp/test-historical-data.log",
}


def _read_image_as_mcp(path: str) -> Image:
    """Wrap an on-disk PNG as an MCP Image content block."""
    with open(path, "rb") as f:
        data = f.read()
    return Image(data=data, format="png")


def _list_screenshots(screenshot_dir: str) -> List[Dict[str, Any]]:
    files = sorted(
        glob.glob(os.path.join(screenshot_dir, "*.png")),
        key=os.path.getctime,
        reverse=True,
    )
    return [
        {
            "filename": os.path.basename(p),
            "path": p,
            "size": os.path.getsize(p),
            "created": os.path.getctime(p),
        }
        for p in files
    ]


def build_server(config: Optional[Config] = None) -> FastMCP:
    cfg = config or Config()

    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8090"))

    mcp = FastMCP(
        name="ibgateway",
        instructions=(
            "Tools to inspect and control the Interactive Brokers Gateway "
            "running inside this container."
        ),
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )

    @mcp.tool()
    def get_screenshot() -> Image:
        """Capture a fresh screenshot of the IB Gateway display."""
        handler = ScreenshotHandler(cfg)
        path = handler.take_screenshot()
        if not path:
            raise RuntimeError("Failed to capture screenshot")
        return _read_image_as_mcp(path)

    @mcp.tool()
    def list_screenshots() -> List[Dict[str, Any]]:
        """List all screenshots saved in the screenshot directory."""
        return _list_screenshots(cfg.screenshot_dir)

    @mcp.tool()
    def get_screenshot_by_name(filename: str) -> Image:
        """Return an existing screenshot by filename (no path traversal)."""
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("invalid filename")
        if not filename.endswith(".png"):
            raise ValueError("only .png files are supported")
        path = os.path.join(cfg.screenshot_dir, filename)
        real = os.path.realpath(path)
        if not real.startswith(os.path.realpath(cfg.screenshot_dir)):
            raise ValueError("path escapes screenshot directory")
        if not os.path.isfile(real):
            raise FileNotFoundError(filename)
        return _read_image_as_mcp(real)

    @mcp.tool()
    def get_connection_status() -> Dict[str, Any]:
        """Visual analysis of the IB Gateway Connection Status table."""
        return check_connection_status(cfg).to_dict()

    @mcp.tool()
    def get_health() -> Dict[str, Any]:
        """Combined visual + TCP-fallback health check (matches Docker HEALTHCHECK)."""
        hc_cfg = build_config_from_env()
        visual_status, detail = check_visual_health(timeout=hc_cfg.timeout_seconds)
        result: Dict[str, Any] = {
            "visual_status": visual_status,
            "visual_detail": detail,
            "tcp_target": f"{hc_cfg.host}:{hc_cfg.port}",
        }
        if visual_status == "unavailable":
            result["tcp_listening"] = check_tcp_listening(hc_cfg)
        return result

    @mcp.tool()
    def automate_login(
        trading_mode: Optional[str] = None,
        api_type: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the xdotool login/MFA automation. Overrides apply to this call only.

        Returns the exit code from AutomationHandler.automate() and the tail of
        the automation log.
        """
        local = Config()
        if trading_mode:
            local.trading_mode = trading_mode.upper()
        if api_type:
            local.api_type = api_type.upper()
        if username:
            local.username = username
        if password:
            local.password = password

        handler = AutomationHandler(local, verbose=False)
        rc = handler.automate()
        log_tail = ""
        log_path = _LOG_FILES["automate"]
        if Path(log_path).exists():
            log_tail = Path(log_path).read_text()[-4000:]
        return {"exit_code": rc, "log_tail": log_tail}

    @mcp.tool()
    def retry_login_after_mfa_failure() -> Dict[str, Any]:
        """Recovery for the IB Gateway 'UNRECOGNIZED USERNAME OR PASSWORD' dialog.

        That dialog often actually means MFA wasn't triggered on the previous
        login (credentials are fine; the auth round-trip just didn't complete).
        This tool dismisses the dialog, refocuses the password field, and
        resubmits — IB Gateway preserves the password contents so we don't
        retype.

        Manual / on-demand only — call this after observing the failure mode
        in get_screenshot. It is NOT invoked automatically anywhere.

        Returns exit_code (0 = success, 1 = couldn't find gateway window) and
        the tail of the automation log for diagnostics.
        """
        notify_slack(
            "MCP `retry_login_after_mfa_failure`: resubmitting login. MFA push incoming."
        )
        handler = AutomationHandler(cfg, verbose=False)
        rc = handler.retry_login_after_mfa_failure()
        log_tail = ""
        log_path = _LOG_FILES["automate"]
        if Path(log_path).exists():
            log_tail = Path(log_path).read_text()[-2000:]
        return {"exit_code": rc, "log_tail": log_tail}

    @mcp.tool()
    def restart_gateway() -> Dict[str, Any]:
        """Kill the running IB Gateway process and start a fresh one.

        Best-effort: signals SIGTERM, waits briefly, then SIGKILLs any
        survivors. Spawns a new ``/opt/ibgateway/ibgateway`` with DISPLAY set
        from config. Automation is not re-run; call ``automate_login`` after
        the GUI has redrawn if you need a fresh login.
        """
        killed_pids: List[int] = []
        try:
            out = subprocess.check_output(
                ["pgrep", "-f", "/opt/ibgateway/ibgateway"], text=True
            )
            killed_pids = [int(p) for p in out.split() if p.strip().isdigit()]
        except subprocess.CalledProcessError:
            killed_pids = []

        for pid in killed_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                subprocess.check_output(
                    ["pgrep", "-f", "/opt/ibgateway/ibgateway"], text=True
                )
                time.sleep(0.2)
            except subprocess.CalledProcessError:
                break
        else:
            for pid in killed_pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        env = os.environ.copy()
        env["DISPLAY"] = cfg.display
        notify_slack("MCP `restart_gateway`: launching new IB Gateway. MFA push incoming.")
        new_proc = subprocess.Popen(
            ["/opt/ibgateway/ibgateway"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"killed_pids": killed_pids, "new_pid": new_proc.pid}

    @mcp.tool()
    def test_historical_data() -> Dict[str, Any]:
        """Run the same IB API historical bars smoke as ``IBGATEWAY_ACTION=test_historical_data``.

        Issues ``reqHistoricalData`` against ``127.0.0.1:4002`` (paper API in-container).
        Override with ``IB_HIST_HOST``, ``IB_HIST_PORT``, ``IB_HIST_CLIENT_ID`` if needed.

        Returns stdout/stderr capture, exit-style code field (0 = bars completed), and
        mirrors output to ``/tmp/test-historical-data.log`` for ``get_gateway_logs``.
        """
        from contextlib import redirect_stderr, redirect_stdout

        from . import historical_simple as _historical_simple

        log_path = "/tmp/test-historical-data.log"
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = _historical_simple.test_historical_data()
        stdout_text = stdout_buf.getvalue()
        stderr_text = stderr_buf.getvalue()
        chunk = f"=== exit_code={rc} ===\n--- stdout ---\n{stdout_text}--- stderr ---\n{stderr_text}"
        try:
            Path(log_path).write_text(chunk, encoding="utf-8", errors="replace")
        except OSError:
            pass

        return {
            "exit_code": rc,
            "ok": rc == 0,
            "stdout_tail": stdout_text[-8000:] if stdout_text else "",
            "stderr_tail": stderr_text[-4000:] if stderr_text else "",
            "log_path": log_path,
        }

    @mcp.tool()
    def get_gateway_logs(name: str = "automate", lines: int = 200) -> Dict[str, Any]:
        """Return the last ``lines`` lines of one of the orchestrator log files.

        Available names: automate, screenshot-server, port-forward, x11vnc,
        websockify, mcp-server, historical-data.
        """
        if name not in _LOG_FILES:
            raise ValueError(
                f"unknown log '{name}'. Choose one of: {sorted(_LOG_FILES)}"
            )
        path = _LOG_FILES[name]
        if not Path(path).exists():
            return {"name": name, "path": path, "exists": False, "content": ""}
        content = Path(path).read_text(errors="replace").splitlines()
        tail = "\n".join(content[-max(lines, 1):])
        return {"name": name, "path": path, "exists": True, "content": tail}

    return mcp


def run(config: Optional[Config] = None) -> int:
    server = build_server(config)
    server.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    sys.exit(run())
