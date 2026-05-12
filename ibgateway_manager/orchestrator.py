"""
Service orchestrator for IB Gateway - coordinates all services.

Startup hooks (optional), via environment:

  ``IBGATEWAY_ACTION`` — runs once after automation, MCP, screenshot service, and socat API
  forwarding are up (see ``_maybe_run_startup_action``). Supported values::

    test_historical_data — run ``historical_simple.test_historical_data()`` (IB API bars probe); combines
                           captured stdout/stderr into ``/tmp/test-historical-data.log``.
                           Non-zero exit from the orchestrator if the probe fails.

  Hyphens are accepted (`test-historical-data` → ``test_historical_data``).
"""

import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import List, Optional

from .api_log_tailer import ApiLogTailer
from .api_traffic_capture import (
    DEFAULT_SINK_PATH as IBGATEWAY_API_TRAFFIC_SINK,
    ApiTrafficCapture,
)
from .config import Config
from .notify import launch_reason, notify_slack
from .screenshot import ScreenshotHandler
from .services import XvfbManager, VNCManager, NoVNCManager, WindowManager
from .port_forwarder import PortForwarder


# Sink for plaintext launcher.log content. The api-log-tailer discovers
# ``~/Jts/launcher.log`` and spawns ``tail -F`` into this sink; the
# orchestrator's existing tail process streams the sink to stdout.
IBGATEWAY_LAUNCHER_LOG_SINK = "/tmp/ibgateway-launcher.log"


class ServiceOrchestrator:
    """Orchestrates all IB Gateway services."""

    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose

        # Service managers
        self.xvfb = XvfbManager(config, verbose)
        self.vnc = VNCManager(config, verbose)
        self.novnc = NoVNCManager(config, verbose)
        self.window_manager = WindowManager(config, verbose)

        # Process tracking
        self.ibgateway_process: Optional[subprocess.Popen] = None
        self.automation_process: Optional[subprocess.Popen] = None
        self.screenshot_process: Optional[subprocess.Popen] = None
        self.mcp_process: Optional[subprocess.Popen] = None
        self.port_forwarder: Optional[PortForwarder] = None
        self.tail_process: Optional[subprocess.Popen] = None
        self.api_log_tailer: Optional[ApiLogTailer] = None
        self.api_traffic_capture: Optional[ApiTrafficCapture] = None

        # Log files
        self.log_files = [
            "/tmp/automate-ibgateway.log",
            "/tmp/port-forward.log",
            "/tmp/screenshot-server.log",
            "/tmp/mcp-server.log",
            "/tmp/websockify.log",
            "/tmp/x11vnc.log",
            IBGATEWAY_LAUNCHER_LOG_SINK,
            IBGATEWAY_API_TRAFFIC_SINK,
            "/tmp/test-historical-data.log",
        ]

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._cleanup)
        signal.signal(signal.SIGINT, self._cleanup)

    def log(self, message: str):
        """Print log message."""
        print(f"[ORCHESTRATOR] {message}", flush=True)

    def _log_capture_enabled(self) -> bool:
        """Decide whether to start the gateway-log streaming pipelines.

        Both pipelines surface gateway-internal state to ``docker logs``
        and CloudWatch:

          * ``ApiTrafficCapture`` — tcpdump of IBKR wire-protocol bytes
            on port 4002. Reveals every reqHistoricalData / order / etc.
          * ``ApiLogTailer`` — tails ``launcher.log`` which carries auth
            flow, JVM events, account-refresh dumps, and saved-settings
            paths.

        In **live** trading mode both pipelines would expose real
        account balances (e.g. ``NetLiquidation 254037.87`` from
        CCPDispatcher), real order IDs, and SMS-MFA token suffixes to
        CloudWatch. That's a leak surface we don't want enabled by
        default — operators who need it in production should opt in
        consciously.

        In **paper** trading mode the simulated balances and synthetic
        order IDs are fine to log; this is the default development /
        CI mode and visibility is the whole point.

        Override:
          ``IBGATEWAY_LOG_CAPTURE=true``        — force enable
          ``IBGATEWAY_LOG_CAPTURE=false``       — force disable
          ``IBGATEWAY_LOG_CAPTURE=paper-only``  — default; on for paper, off for live
        """
        setting = os.getenv("IBGATEWAY_LOG_CAPTURE", "paper-only").strip().lower()
        if setting == "true":
            return True
        if setting == "false":
            return False
        return self.config.trading_mode == "PAPER"

    def _create_log_files(self):
        """Create log files."""
        self.log("=== Create and stream logs ===")
        for log_file in self.log_files:
            Path(log_file).touch()

    def _start_log_tailing(self):
        """Start tailing log files."""
        if self.verbose:
            # Tail all logs in verbose mode
            self.tail_process = subprocess.Popen(
                ["tail", "-f"] + self.log_files,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
        else:
            # In normal mode tail the automation log + the IB Gateway API
            # log sink so plaintext gateway API messages reach CloudWatch.
            self.tail_process = subprocess.Popen(
                [
                    "tail", "-F",
                    "/tmp/automate-ibgateway.log",
                    IBGATEWAY_LAUNCHER_LOG_SINK,
                    IBGATEWAY_API_TRAFFIC_SINK,
                ],
                stdout=sys.stdout,
                stderr=sys.stderr
            )

    def _wait_for_screenshot_service(self, timeout: int = 60) -> bool:
        """Wait for screenshot service to be ready."""
        self.log("Waiting for screenshot service to be ready...")

        for i in range(timeout):
            try:
                import urllib.request
                response = urllib.request.urlopen(f"http://localhost:{self.config.screenshot_port}/", timeout=1)
                if response.getcode() == 200:
                    # If port is accessible, consider it ready
                    self.log("✓ Screenshot service is ready")
                    return True
            except Exception:
                pass

            # Also check log file for ready message
            if Path("/tmp/screenshot-server.log").exists():
                log_content = Path("/tmp/screenshot-server.log").read_text()
                if "Screenshot service ready" in log_content:
                    self.log("✓ Screenshot service is ready")
                    return True

            time.sleep(1)

        self.log("ERROR: Screenshot service failed to start")
        return False

    def _wait_for_mcp_server(self, timeout: int = 30) -> bool:
        """Wait for the MCP server to start listening on its port."""
        self.log("Waiting for MCP server to be ready...")
        host = self.config.mcp_host or "127.0.0.1"
        # Streamable HTTP binds the host literally — when bound to 127.0.0.1
        # the orchestrator probes localhost.
        probe_host = "127.0.0.1" if host in ("0.0.0.0", "127.0.0.1") else host
        for _ in range(timeout):
            try:
                with socket.create_connection((probe_host, self.config.mcp_port), timeout=1):
                    self.log(f"✓ MCP server is ready on {host}:{self.config.mcp_port}")
                    return True
            except OSError:
                pass
            time.sleep(1)
        self.log("WARNING: MCP server did not become ready within timeout")
        return False

    def _wait_for_automation(self, timeout: int = 90) -> bool:
        """Wait for automation to complete."""
        self.log("Waiting for automation to complete...")

        for i in range(timeout):
            # Check if process crashed
            if self.automation_process and self.automation_process.poll() is not None:
                exit_code = self.automation_process.returncode
                # Process finished, check log for completion
                if Path("/tmp/automate-ibgateway.log").exists():
                    log_content = Path("/tmp/automate-ibgateway.log").read_text()
                    if "Configuration Complete" in log_content:
                        self.log("✓ Automation completed")
                        return True
                    else:
                        # Process exited but didn't complete - check exit code
                        if exit_code != 0:
                            self.log(f"ERROR: Automation process exited with code {exit_code}")
                            # Show last part of log for debugging
                            if log_content:
                                self.log(f"Last log entries: {log_content[-1000:]}")
                            return False
                        else:
                            # Exit code 0 but no completion message - might be OK, but log warning
                            self.log("WARNING: Automation process finished but completion message not found")
                            return False

            # Check log file for completion message
            if Path("/tmp/automate-ibgateway.log").exists():
                log_content = Path("/tmp/automate-ibgateway.log").read_text()
                if "Configuration Complete" in log_content:
                    self.log("✓ Automation completed")
                    return True

            time.sleep(1)

        # Timeout reached
        # Final check
        if Path("/tmp/automate-ibgateway.log").exists():
            log_content = Path("/tmp/automate-ibgateway.log").read_text()
            if "Configuration Complete" in log_content:
                self.log("✓ Automation completed")
                return True

        self.log(f"ERROR: Automation did not complete within {timeout}s timeout")
        if Path("/tmp/automate-ibgateway.log").exists():
            log_content = Path("/tmp/automate-ibgateway.log").read_text()
            if log_content:
                self.log(f"Last log entries: {log_content[-1000:]}")
        return False

    def _wait_for_port_forwarding(self, timeout: int = 30) -> bool:
        """Wait for port forwarding to be ready."""
        self.log("Waiting for port forwarding to be ready...")

        for i in range(timeout):
            try:
                result = subprocess.run(
                    ["netstat", "-tlnp"],
                    capture_output=True,
                    text=True
                )
                output = result.stdout if result.returncode == 0 else ""

                # Try ss as fallback
                if not output:
                    result = subprocess.run(
                        ["ss", "-tlnp"],
                        capture_output=True,
                        text=True
                    )
                    output = result.stdout if result.returncode == 0 else ""

                if ":4003 " in output and ":4004 " in output:
                    self.log("✓ Port forwarding is ready")
                    return True
            except Exception:
                pass

            time.sleep(1)

        self.log("ERROR: Port forwarding failed to start within timeout")
        return False

    def _run_test_historical_data_action(self) -> int:
        """Run IB API historical smoke test; writes combined streams to ``/tmp/test-historical-data.log``."""
        log_path = "/tmp/test-historical-data.log"
        self.log(f"=== Running IBGATEWAY_ACTION=test_historical_data (log: {log_path}) ===")
        from .historical_simple import test_historical_data

        stdout_buf = StringIO()
        stderr_buf = StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = test_historical_data()

        out_t = stdout_buf.getvalue()
        err_t = stderr_buf.getvalue()
        chunk = f"=== exit_code={rc} ===\n--- stdout ---\n{out_t}--- stderr ---\n{err_t}"
        try:
            Path(log_path).write_text(chunk, encoding="utf-8", errors="replace")
        except OSError as exc:
            self.log(f"WARNING: could not write {log_path}: {exc}")

        self.log(f"test_historical_data finished rc={rc}")
        if rc != 0:
            self.log(chunk[-3500:])
        return rc

    def _maybe_run_startup_action(self) -> int:
        raw = os.getenv("IBGATEWAY_ACTION", "").strip()
        if not raw:
            return 0
        action = raw.lower().replace("-", "_")
        if action == "test_historical_data":
            return self._run_test_historical_data_action()
        self.log(f"WARNING: unknown IBGATEWAY_ACTION={raw!r} (ignored)")
        return 0

    def _verify_all_services(self):
        """Verify all services are ready."""
        self.log("")
        self.log("=== Verifying all services ===")

        xvfb_ready = self.xvfb.process and self.xvfb.process.poll() is None
        vnc_ready = self.vnc.wait_for_ready(timeout=1)
        novnc_ready = self.novnc.wait_for_ready(timeout=1)
        screenshot_ready = self._wait_for_screenshot_service(timeout=1)
        port_forward_ready = self._wait_for_port_forwarding(timeout=1)

        automation_ready = False
        if Path("/tmp/automate-ibgateway.log").exists():
            log_content = Path("/tmp/automate-ibgateway.log").read_text()
            automation_ready = "Configuration Complete" in log_content or (
                self.automation_process and self.automation_process.poll() is not None
            )

        mcp_ready = self.mcp_process is not None and self.mcp_process.poll() is None

        self.log(f"{'✓' if xvfb_ready else '✗'} Xvfb: {'Ready' if xvfb_ready else 'Not ready'}")
        self.log(f"{'✓' if vnc_ready else '✗'} VNC: {'Ready' if vnc_ready else 'Not ready'}")
        self.log(f"{'✓' if novnc_ready else '✗'} noVNC: {'Ready' if novnc_ready else 'Not ready'}")
        self.log(f"{'✓' if screenshot_ready else '✗'} Screenshot service: {'Ready' if screenshot_ready else 'Not ready'}")
        self.log(f"{'✓' if port_forward_ready else '✗'} Port forwarding: {'Ready' if port_forward_ready else 'Not ready'}")
        self.log(f"{'✓' if automation_ready else '✗'} Automation: {'Complete' if automation_ready else 'Not complete'}")
        self.log(f"{'✓' if mcp_ready else '✗'} MCP server: {'Running' if mcp_ready else 'Not running'}")

    def start(self, skip_automation: bool = False, skip_mcp: bool = False) -> int:
        """Start all services.

        Args:
            skip_automation: If True, skip automation and only start services.
                            Can also be set via SKIP_AUTOMATION environment variable.
            skip_mcp: If True, skip the MCP server.
                            Can also be set via SKIP_MCP environment variable.
        """
        # Check environment variable if skip_automation not explicitly set
        if not skip_automation:
            skip_automation = os.getenv("SKIP_AUTOMATION", "0") in ("1", "true", "yes")
        if not skip_mcp:
            skip_mcp = os.getenv("SKIP_MCP", "0") in ("1", "true", "yes")

        self.log("=== IBGateway ===")

        # Create log files
        self._create_log_files()

        # Start log tailing
        self._start_log_tailing()

        # Start Xvfb
        if not self.xvfb.start():
            return 1
        if not self.xvfb.wait_for_ready():
            return 1

        # Start window manager
        self.window_manager.start()

        # Capture "initial state" screenshot (with xterm window present).
        # This is helpful for CI artifact debugging and should be best-effort.
        try:
            time.sleep(1)  # give xterm a moment to render
            screenshotter = ScreenshotHandler(self.config, verbose=self.verbose)
            screenshotter.take_screenshot(os.path.join(self.config.screenshot_dir, "initial_state.png"))
        except Exception as e:
            self.log(f"WARNING: Failed to capture initial_state screenshot: {e}")

        # The current "window manager" implementation launches an xterm; close it
        # so it doesn't obstruct the IBGateway UI in VNC/noVNC.
        try:
            self.window_manager.close_terminal_windows()
        except Exception as e:
            self.log(f"ERROR: Failed to close terminal window before starting IB Gateway: {e}")
            return 1

        # Capture screenshot after closing the terminal window.
        try:
            time.sleep(0.5)
            screenshotter = ScreenshotHandler(self.config, verbose=self.verbose)
            screenshotter.take_screenshot(os.path.join(self.config.screenshot_dir, "after_close_terminal.png"))
        except Exception as e:
            self.log(f"WARNING: Failed to capture after_close_terminal screenshot: {e}")

        # Start VNC
        if not self.vnc.start():
            return 1
        if not self.vnc.wait_for_ready():
            return 1

        # Start noVNC
        if not self.novnc.start():
            return 1
        if not self.novnc.wait_for_ready():
            return 1

        # Debug: Show environment
        self.log("=== Environment ===")
        self.log(f"RESOLUTION={self.config.resolution}")
        self.log(f"USER={os.getenv('USER', 'root')}")
        self.log(f"DISPLAY={self.config.display}")

        # Gate the launcher.log tailer on trading mode. Live mode would
        # leak real balances + order IDs from CCPDispatcher's account
        # refresh dumps to CloudWatch; see _log_capture_enabled() for
        # the env-var override.
        log_capture_on = self._log_capture_enabled()
        if not log_capture_on:
            self.log(
                f"launcher-log tailer DISABLED "
                f"(trading_mode={self.config.trading_mode}, "
                f"IBGATEWAY_LOG_CAPTURE={os.getenv('IBGATEWAY_LOG_CAPTURE', 'paper-only')}); "
                f"set IBGATEWAY_LOG_CAPTURE=true to force-enable"
            )

        # Start tcpdump-based capture of IBKR wire-protocol traffic on
        # the API ports. This is the **only** way to capture per-message
        # request/response detail with IB Gateway 10.45 — the GUI's
        # ``Show API messages`` tab shows it but the gateway never
        # writes it to disk in any plaintext file (verified empirically:
        # the ``Create API message log file`` toggle lives in the
        # encrypted ibg.xml settings unreachable from outside the GUI,
        # and neither ibgateway.*.ibgzenc nor the GUI ``Export Logs``
        # action includes the per-message records).
        #
        # We do NOT gate this call — the binary's presence in the image
        # IS the gate. Default builds (``ENABLE_TCPDUMP=false``) don't
        # install tcpdump, so ``start()`` finds nothing on PATH, returns
        # False, and logs one WARNING line without disturbing boot.
        # Diagnostic builds (``--build-arg ENABLE_TCPDUMP=true``) do
        # install it, and the consumer-side deploy guard refuses to
        # roll those images to production via CI — operators have to
        # use the manual AWS CLI deploy path with explicit
        # authorization. Trading-mode is not consulted: if you took
        # the deliberate steps to build a diagnostic image AND deploy
        # it manually, the capture turning on is the expected outcome.
        try:
            self.api_traffic_capture = ApiTrafficCapture()
            if self.api_traffic_capture.start():
                self.log(
                    f"api-traffic-capture: tcpdump pid={self.api_traffic_capture.pid} "
                    f"streaming -> stdout (diagnostic image)"
                )
            else:
                self.log(
                    "api-traffic-capture: disabled — tcpdump not installed "
                    "(production-default image). Build with "
                    "--build-arg ENABLE_TCPDUMP=true and deploy manually "
                    "to enable wire-protocol capture."
                )
        except Exception as e:
            self.log(f"WARNING: failed to start api-traffic-capture: {e}")

        # Start IB Gateway
        self.log("=== Starting IB Gateway ===")
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        # Heads-up to Slack BEFORE Popen so the user knows an MFA push is
        # imminent. The launch_reason() suffix tells them WHO triggered it
        # (ECS task, CI workflow, local dev, etc.) so a stray push isn't a
        # mystery. No-op if SLACK_WEBHOOK_URL is unset; never raises.
        notify_slack(
            f"Cold start [{launch_reason()}]: launching IB Gateway Java "
            "process. MFA push incoming."
        )
        try:
            self.ibgateway_process = subprocess.Popen(
                ["/opt/ibgateway/ibgateway"],
                env=env
            )
            self.log(f"IB Gateway started (PID: {self.ibgateway_process.pid})")

            # Start the api-log tailer. It polls ``~/Jts`` every 30s and
            # spawns ``tail -F`` for each new plaintext log file as it
            # appears — both ``launcher.log`` at the top level and the
            # per-account ``api.YYYYMMDD.log`` once IB Gateway logs in.
            # Output streams into IBGATEWAY_LAUNCHER_LOG_SINK, which the
            # orchestrator already tails to stdout, so each line lands
            # in CloudWatch. Gated on trading mode by
            # _log_capture_enabled() — independent of the
            # ApiTrafficCapture above (which is gated on the
            # ``ENABLE_TCPDUMP`` build arg). Launcher.log doesn't need
            # extra kernel privileges so the gating need only worry
            # about leaking real balances in live mode.
            if log_capture_on:
                def _on_tail_started(path):
                    self.log(f"api-log-tailer: streaming {path} -> stdout")
                self.api_log_tailer = ApiLogTailer(
                    sink_path=IBGATEWAY_LAUNCHER_LOG_SINK,
                    on_tail_started=_on_tail_started,
                )
                self.api_log_tailer.start()

            # Check if process crashed immediately
            time.sleep(2)  # Give it a moment to start
            if self.ibgateway_process.poll() is not None:
                exit_code = self.ibgateway_process.returncode
                self.log(f"ERROR: IB Gateway process exited immediately with code {exit_code}")
                return 1
        except Exception as e:
            self.log(f"ERROR: Failed to start IB Gateway: {e}")
            return 1

        # Determine CLI script path (needed for both automation and screenshot server)
        # Try /ibgateway_manager_cli.py first (Docker container path), then fallback to script location
        cli_script = "/ibgateway_manager_cli.py"
        if not Path(cli_script).exists():
            # Try to find it relative to this module
            script_dir = Path(__file__).resolve().parent.parent.parent
            potential_path = script_dir / "ibgateway_manager_cli.py"
            if potential_path.exists():
                cli_script = str(potential_path)

        if skip_automation:
            self.log("=== Skipping automation (--no-automation flag set) ===")
        else:

            # Start automation in background
            try:
                with open("/tmp/automate-ibgateway.log", "w") as log_f:
                    self.automation_process = subprocess.Popen(
                        [sys.executable, "-u", cli_script, "automate-ibgateway"],
                        stdout=log_f,
                        stderr=subprocess.STDOUT
                    )
                self.log(f"Automation script started (PID: {self.automation_process.pid})")
            except Exception as e:
                self.log(f"ERROR: Failed to start automation: {e}")
                return 1

        # Start screenshot HTTP server in background
        self.log(f"=== Starting screenshot HTTP server on port {self.config.screenshot_port} ===")
        try:
            with open("/tmp/screenshot-server.log", "w") as log_f:
                self.screenshot_process = subprocess.Popen(
                    [sys.executable, "-u", cli_script, "screenshot-server", "--port", str(self.config.screenshot_port)],
                    stdout=log_f,
                    stderr=subprocess.STDOUT
                )
            self.log(f"Screenshot server started (PID: {self.screenshot_process.pid})")
        except Exception as e:
            self.log(f"ERROR: Failed to start screenshot server: {e}")
            return 1

        if not self._wait_for_screenshot_service():
            return 1

        # Check if screenshot process crashed
        if self.screenshot_process and self.screenshot_process.poll() is not None:
            exit_code = self.screenshot_process.returncode
            self.log(f"ERROR: Screenshot server process exited with code {exit_code}")
            if Path("/tmp/screenshot-server.log").exists():
                log_content = Path("/tmp/screenshot-server.log").read_text()
                if log_content:
                    self.log(f"Screenshot server log: {log_content[-1000:]}")
            return 1

        # Start MCP server in background
        if skip_mcp:
            self.log("=== Skipping MCP server (--no-mcp flag set) ===")
        else:
            self.log(
                f"=== Starting MCP server on {self.config.mcp_host}:{self.config.mcp_port} ==="
            )
            try:
                mcp_env = os.environ.copy()
                mcp_env["MCP_HOST"] = self.config.mcp_host
                mcp_env["MCP_PORT"] = str(self.config.mcp_port)
                with open("/tmp/mcp-server.log", "w") as log_f:
                    self.mcp_process = subprocess.Popen(
                        [sys.executable, "-u", cli_script, "mcp-server"],
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        env=mcp_env,
                    )
                self.log(f"MCP server started (PID: {self.mcp_process.pid})")
            except Exception as e:
                self.log(f"WARNING: Failed to start MCP server: {e}")

            self._wait_for_mcp_server()
            if self.mcp_process and self.mcp_process.poll() is not None:
                # MCP is part of the gateway contract: if it can't start, the
                # container is in an unexpected state and we want CI / ECS to
                # see that rather than silently degrading. Set SKIP_MCP=1 (or
                # the --no-mcp flag) for an explicit escape hatch.
                self.log(
                    f"ERROR: MCP server exited with code {self.mcp_process.returncode}"
                )
                if Path("/tmp/mcp-server.log").exists():
                    log_content = Path("/tmp/mcp-server.log").read_text()
                    if log_content:
                        self.log(f"MCP server log:\n{log_content[-2000:]}")
                self.log(
                    "Aborting startup. To bypass intentionally, set SKIP_MCP=1 "
                    "or pass --no-mcp."
                )
                self.mcp_process = None
                return 1

        # Wait for automation to complete (only if automation was started)
        if not skip_automation:
            if not self._wait_for_automation():
                self.log("ERROR: Automation failed to complete")
                return 1

        # Start port forwarding in background
        self.log("=== Starting socat port forwarding ===")
        self.port_forwarder = PortForwarder(self.config, self.verbose)
        if not self.port_forwarder.start_background():
            self.log("ERROR: Port forwarding failed to start")
            return 1
        self.log(f"Port forwarding started")

        if not self._wait_for_port_forwarding():
            self.log("ERROR: Port forwarding did not become ready")
            return 1

        # Verify all services
        self._verify_all_services()

        startup_rc = self._maybe_run_startup_action()
        if startup_rc != 0:
            return startup_rc

        self.log("")
        self.log("=== All services ready ===")

        # Keep running - wait for tail process or processes
        try:
            # Wait for tail process (which will run until killed)
            if self.tail_process:
                self.tail_process.wait()
            else:
                # If no tail process, wait for IB Gateway
                if self.ibgateway_process:
                    self.ibgateway_process.wait()
        except KeyboardInterrupt:
            self._cleanup(None, None)

        return 0

    def _cleanup(self, signum, frame):
        """Clean up all processes on exit."""
        self.log("Shutting down services...")

        # Stop all processes
        if self.ibgateway_process:
            try:
                self.ibgateway_process.terminate()
            except Exception:
                pass

        if self.automation_process:
            try:
                self.automation_process.terminate()
            except Exception:
                pass

        if self.screenshot_process:
            try:
                self.screenshot_process.terminate()
            except Exception:
                pass

        if self.mcp_process:
            try:
                self.mcp_process.terminate()
            except Exception:
                pass

        if self.port_forwarder:
            try:
                for process in self.port_forwarder.processes:
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        try:
                            process.kill()
                        except Exception:
                            pass
            except Exception:
                pass

        if self.tail_process:
            try:
                self.tail_process.terminate()
            except Exception:
                pass

        if self.api_log_tailer:
            try:
                self.api_log_tailer.stop()
            except Exception:
                pass

        if self.api_traffic_capture:
            try:
                self.api_traffic_capture.stop()
            except Exception:
                pass

        # Stop service managers
        self.novnc.stop()
        self.vnc.stop()
        self.window_manager.stop()
        self.xvfb.stop()

        sys.exit(0)
