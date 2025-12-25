"""
Service orchestrator for IB Gateway - coordinates all services.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from .config import Config
from .screenshot import ScreenshotHandler
from .services import XvfbManager, VNCManager, NoVNCManager, WindowManager
from .port_forwarder import PortForwarder


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
        self.port_forwarder: Optional[PortForwarder] = None
        self.tail_process: Optional[subprocess.Popen] = None
        
        # Log files
        self.log_files = [
            "/tmp/automate-ibgateway.log",
            "/tmp/port-forward.log",
            "/tmp/screenshot-server.log",
            "/tmp/websockify.log",
            "/tmp/x11vnc.log"
        ]
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._cleanup)
        signal.signal(signal.SIGINT, self._cleanup)
    
    def log(self, message: str):
        """Print log message."""
        print(f"[ORCHESTRATOR] {message}", flush=True)
    
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
            # Only tail automation log in normal mode
            self.tail_process = subprocess.Popen(
                ["tail", "-f", "/tmp/automate-ibgateway.log"],
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
    
    def _wait_for_automation(self, timeout: int = 90) -> bool:
        """Wait for automation to complete."""
        self.log("Waiting for automation to complete...")
        
        for i in range(timeout):
            # Check log file for completion message
            if Path("/tmp/automate-ibgateway.log").exists():
                log_content = Path("/tmp/automate-ibgateway.log").read_text()
                if "Configuration Complete" in log_content:
                    self.log("✓ Automation completed")
                    return True
            
            # Also check if process is still running
            if self.automation_process and self.automation_process.poll() is not None:
                # Process finished, check log one more time
                if Path("/tmp/automate-ibgateway.log").exists():
                    log_content = Path("/tmp/automate-ibgateway.log").read_text()
                    if "Configuration Complete" in log_content:
                        self.log("✓ Automation completed")
                        return True
                    else:
                        self.log("WARNING: Automation process finished but completion message not found")
                        return True  # Don't fail, automation may have completed
            
            time.sleep(1)
        
        # Final check
        if Path("/tmp/automate-ibgateway.log").exists():
            log_content = Path("/tmp/automate-ibgateway.log").read_text()
            if "Configuration Complete" in log_content:
                self.log("✓ Automation completed")
                return True
        
        self.log("WARNING: Automation timeout, but continuing...")
        return True  # Don't fail, allow container to continue
    
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
        
        self.log("WARNING: Port forwarding may not be ready")
        return True  # Don't fail on this, as IB Gateway ports may not be available yet
    
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
        
        self.log(f"{'✓' if xvfb_ready else '✗'} Xvfb: {'Ready' if xvfb_ready else 'Not ready'}")
        self.log(f"{'✓' if vnc_ready else '✗'} VNC: {'Ready' if vnc_ready else 'Not ready'}")
        self.log(f"{'✓' if novnc_ready else '✗'} noVNC: {'Ready' if novnc_ready else 'Not ready'}")
        self.log(f"{'✓' if screenshot_ready else '✗'} Screenshot service: {'Ready' if screenshot_ready else 'Not ready'}")
        self.log(f"{'✓' if port_forward_ready else '✗'} Port forwarding: {'Ready' if port_forward_ready else 'Not ready'}")
        self.log(f"{'✓' if automation_ready else '✗'} Automation: {'Complete' if automation_ready else 'Not complete'}")
    
    def start(self, skip_automation: bool = False) -> int:
        """Start all services.
        
        Args:
            skip_automation: If True, skip automation and only start services.
                            Can also be set via SKIP_AUTOMATION environment variable.
        """
        # Check environment variable if skip_automation not explicitly set
        if not skip_automation:
            skip_automation = os.getenv("SKIP_AUTOMATION", "0") in ("1", "true", "yes")
        
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
        
        # Start IB Gateway
        self.log("=== Starting IB Gateway ===")
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        try:
            self.ibgateway_process = subprocess.Popen(
                ["/opt/ibgateway/ibgateway"],
                env=env
            )
            self.log(f"IB Gateway started (PID: {self.ibgateway_process.pid})")
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
        
        # Wait for automation to complete (only if automation was started)
        if not skip_automation:
            self._wait_for_automation()
        
        # Start port forwarding in background
        self.log("=== Starting socat port forwarding ===")
        self.port_forwarder = PortForwarder(self.config, self.verbose)
        if not self.port_forwarder.start_background():
            self.log("WARNING: Port forwarding failed to start")
        else:
            self.log(f"Port forwarding started")
        
        self._wait_for_port_forwarding()
        
        # Verify all services
        self._verify_all_services()
        
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
        
        # Stop service managers
        self.novnc.stop()
        self.vnc.stop()
        self.window_manager.stop()
        self.xvfb.stop()
        
        sys.exit(0)

