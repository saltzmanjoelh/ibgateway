"""
Service managers for Xvfb, VNC, and noVNC.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from .config import Config


class XvfbManager:
    """Manages Xvfb virtual display."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.process: Optional[subprocess.Popen] = None
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[XVFB] {message}", flush=True)
        else:
            print(message, flush=True)
    
    def cleanup_locks(self):
        """Clean up stale X11 locks."""
        lock_path = Path("/tmp/.X99-lock")
        socket_path = Path("/tmp/.X11-unix/X99")
        
        if lock_path.exists():
            try:
                lock_path.unlink()
                self.log(f"Removed stale lock: {lock_path}")
            except Exception as e:
                self.log(f"Warning: Could not remove lock: {e}")
        
        if socket_path.exists():
            try:
                socket_path.unlink()
                self.log(f"Removed stale socket: {socket_path}")
            except Exception as e:
                self.log(f"Warning: Could not remove socket: {e}")
    
    def ensure_machine_id(self):
        """Generate machine-id if it doesn't exist (required for dbus)."""
        machine_id_path = Path("/etc/machine-id")
        if not machine_id_path.exists():
            try:
                result = subprocess.run(
                    ["dbus-uuidgen"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                machine_id_path.write_text(result.stdout.strip())
                self.log("Generated machine-id")
            except Exception as e:
                self.log(f"Warning: Could not generate machine-id: {e}")
    
    def start(self) -> bool:
        """Start Xvfb process."""
        self.cleanup_locks()
        self.ensure_machine_id()
        
        self.log(f"=== Starting Xvfb on display {self.config.display} ===")
        
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        try:
            self.process = subprocess.Popen(
                [
                    "Xvfb",
                    self.config.display,
                    "-screen", "0",
                    f"{self.config.resolution}x24",
                    "-ac",
                    "+extension", "GLX",
                    "+render",
                    "-noreset"
                ],
                env=env
            )
            self.log(f"Xvfb started (PID: {self.process.pid})")
            return True
        except Exception as e:
            self.log(f"ERROR: Failed to start Xvfb: {e}")
            return False
    
    def wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for Xvfb to be ready."""
        self.log("Waiting for Xvfb to be ready...")
        
        for i in range(timeout):
            if self.process and self.process.poll() is not None:
                self.log("ERROR: Xvfb process exited")
                return False
            
            # Check if display socket exists
            socket_paths = [
                Path(f"/tmp/.X11-unix/{self.config.display.replace(':', 'X')}"),
                Path("/tmp/.X11-unix/X0")
            ]
            
            for socket_path in socket_paths:
                if socket_path.exists() and socket_path.is_socket():
                    self.log("✓ Xvfb is ready")
                    return True
            
            # If process is running, consider it ready after a few seconds
            if self.process and i >= 3:
                self.log("✓ Xvfb is ready (process running)")
                return True
            
            time.sleep(1)
        
        self.log("ERROR: Xvfb failed to start")
        return False
    
    def stop(self):
        """Stop Xvfb process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.log("Xvfb stopped")
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class VNCManager:
    """Manages x11vnc server."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.process: Optional[subprocess.Popen] = None
        self.log_file = "/tmp/x11vnc.log"
        self.port = 5901
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[VNC] {message}", flush=True)
        else:
            print(message, flush=True)
    
    def start(self) -> bool:
        """Start x11vnc server."""
        self.log(f"=== Starting x11vnc on port {self.port} ===")
        
        # Ensure log file exists
        Path(self.log_file).touch()
        
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        try:
            with open(self.log_file, "a") as log_f:
                self.process = subprocess.Popen(
                    [
                        "x11vnc",
                        "-display", self.config.display,
                        "-noxdamage",
                        "-forever",
                        "-shared",
                        "-rfbport", str(self.port),
                        "-bg",
                        "-o", self.log_file
                    ],
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT
                )
            self.log(f"x11vnc started (PID: {self.process.pid})")
            return True
        except Exception as e:
            self.log(f"ERROR: Failed to start x11vnc: {e}")
            return False
    
    def wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for VNC server to be ready."""
        self.log("Waiting for VNC server to be ready...")
        
        # When using -bg, x11vnc forks and the parent process exits immediately
        # So we need to wait a moment before checking, then verify the actual x11vnc process
        time.sleep(2)  # Give x11vnc time to fork and start
        
        for i in range(timeout):
            # Check if the actual x11vnc process is running (not the parent Popen process)
            try:
                # Check for x11vnc process listening on our port
                result = subprocess.run(
                    ["pgrep", "-f", f"x11vnc.*{self.port}"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Process exists, now check if port is listening
                    pass
            except Exception:
                pass
            
            # Check if port is listening
            try:
                result = subprocess.run(
                    ["netstat", "-tlnp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and f":{self.port} " in result.stdout:
                    self.log("✓ VNC server is ready")
                    return True
                
                # Try ss as fallback
                result = subprocess.run(
                    ["ss", "-tlnp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and f":{self.port} " in result.stdout:
                    self.log("✓ VNC server is ready")
                    return True
            except Exception:
                pass
            
            time.sleep(1)
        
        self.log("ERROR: VNC server failed to start")
        # Check log file for errors
        if Path(self.log_file).exists():
            log_content = Path(self.log_file).read_text()
            if log_content:
                self.log(f"Last log entries: {log_content[-500:]}")  # Last 500 chars
        return False
    
    def stop(self):
        """Stop x11vnc process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.log("x11vnc stopped")
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class NoVNCManager:
    """Manages websockify/noVNC proxy."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.process: Optional[subprocess.Popen] = None
        self.log_file = "/tmp/websockify.log"
        self.web_port = 5900
        self.vnc_port = 5901
        self.web_dir = "/opt/novnc"
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[NOVNC] {message}", flush=True)
        else:
            print(message, flush=True)
    
    def _find_websockify(self) -> Optional[list]:
        """Find websockify command or module."""
        # Try command first
        try:
            result = subprocess.run(
                ["which", "websockify"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.log(f"websockify found: {result.stdout.strip()}")
                return ["websockify"]
        except Exception:
            pass
        
        # Fallback to python module
        self.log("websockify not in PATH, will use python3 -m websockify")
        return ["python3", "-m", "websockify"]
    
    def start(self) -> bool:
        """Start websockify/noVNC proxy."""
        self.log(f"=== Starting noVNC proxy with verbose logging ===")
        
        # Ensure log file exists
        Path(self.log_file).touch()
        
        websockify_cmd = self._find_websockify()
        if not websockify_cmd:
            self.log("ERROR: Could not find websockify")
            return False
        
        self.log(f"Starting websockify: listening on {self.web_port} (web), connecting to localhost:{self.vnc_port} (VNC)")
        
        try:
            with open(self.log_file, "a") as log_f:
                self.process = subprocess.Popen(
                    websockify_cmd + [
                        f"--web={self.web_dir}",
                        str(self.web_port),
                        f"localhost:{self.vnc_port}",
                        "-v", "-v", "-v",
                        f"--log-file={self.log_file}"
                    ],
                    stdout=log_f,
                    stderr=subprocess.STDOUT
                )
            self.log(f"Websockify started (PID: {self.process.pid})")
            return True
        except Exception as e:
            self.log(f"ERROR: Failed to start websockify: {e}")
            return False
    
    def wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for noVNC proxy to be ready."""
        self.log("Waiting for noVNC proxy to be ready...")
        
        for i in range(timeout):
            if self.process and self.process.poll() is not None:
                self.log("ERROR: websockify process exited")
                return False
            
            # Check if port is listening
            try:
                result = subprocess.run(
                    ["netstat", "-tlnp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and f":{self.web_port} " in result.stdout:
                    self.log("✓ noVNC proxy is ready")
                    return True
                
                # Try ss as fallback
                result = subprocess.run(
                    ["ss", "-tlnp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and f":{self.web_port} " in result.stdout:
                    self.log("✓ noVNC proxy is ready")
                    return True
            except Exception:
                pass
            
            time.sleep(1)
        
        self.log("ERROR: noVNC proxy failed to start")
        return False
    
    def stop(self):
        """Stop websockify process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.log("websockify stopped")
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class WindowManager:
    """Manages window manager (xterm)."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.process: Optional[subprocess.Popen] = None
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[WM] {message}", flush=True)
        else:
            print(message, flush=True)
    
    def start(self) -> bool:
        """Start xterm window manager."""
        self.log("=== Starting window manager ===")
        
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        try:
            self.process = subprocess.Popen(
                ["xterm", "-geometry", "80x24+0+0", "-e", "/bin/bash"],
                env=env
            )
            self.log(f"Window manager started (PID: {self.process.pid})")
            return True
        except Exception as e:
            self.log(f"ERROR: Failed to start window manager: {e}")
            return False
    
    def stop(self):
        """Stop window manager."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

