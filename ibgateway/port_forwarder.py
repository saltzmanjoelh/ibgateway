"""
Port forwarding functionality using socat.
"""

import signal
import subprocess
import time
from typing import List

from .config import Config


class PortForwarder:
    """Handles port forwarding using socat."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.live_port = 4001
        self.paper_port = 4002
        self.forward_live_port = 4003
        self.forward_paper_port = 4004
        self.processes: List[subprocess.Popen] = []
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[PORT-FORWARD] {message}")
        else:
            print(message)
    
    def check_port_listening(self, port: int) -> bool:
        """Check if a port is listening."""
        try:
            result = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f":{port} " in result.stdout
            
            # Try ss as fallback
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True,
                text=True
            )
            return f":{port} " in result.stdout
        except Exception:
            return False
    
    def wait_for_ports(self, timeout: int = 60) -> bool:
        """Wait for IB Gateway ports to be available."""
        self.log("Waiting for IB Gateway ports to be available...")
        
        elapsed = 0
        while elapsed < timeout:
            if self.check_port_listening(self.live_port) and self.check_port_listening(self.paper_port):
                self.log("✓ IB Gateway ports are ready")
                return True
            
            time.sleep(1)
            elapsed += 1
        
        self.log(f"WARNING: IB Gateway ports not available after {timeout}s, starting forwarding anyway")
        return False
    
    def start_background(self) -> bool:
        """Start socat port forwarding in background mode (non-blocking)."""
        self.log("--- Starting socat port forwarding ---")
        self.log(f"Forwarding {self.forward_live_port} -> 127.0.0.1:{self.live_port} (Live Trading)")
        self.log(f"Forwarding {self.forward_paper_port} -> 127.0.0.1:{self.paper_port} (Paper Trading)")
        
        # Wait for ports (non-blocking, will start anyway)
        self.wait_for_ports()
        
        # Start Live Trading forwarding
        self.log(f"Starting socat forwarding for Live Trading ({self.forward_live_port} -> 127.0.0.1:{self.live_port})...")
        try:
            live_process = subprocess.Popen(
                ["socat", f"TCP-LISTEN:{self.forward_live_port},fork,reuseaddr", f"TCP:127.0.0.1:{self.live_port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes.append(live_process)
            self.log(f"✓ Live Trading forwarding started (PID: {live_process.pid})")
        except Exception as e:
            self.log(f"ERROR: Failed to start Live Trading forwarding: {e}")
            return False
        
        # Start Paper Trading forwarding
        self.log(f"Starting socat forwarding for Paper Trading ({self.forward_paper_port} -> 127.0.0.1:{self.paper_port})...")
        try:
            paper_process = subprocess.Popen(
                ["socat", f"TCP-LISTEN:{self.forward_paper_port},fork,reuseaddr", f"TCP:127.0.0.1:{self.paper_port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes.append(paper_process)
            self.log(f"✓ Paper Trading forwarding started (PID: {paper_process.pid})")
        except Exception as e:
            self.log(f"ERROR: Failed to start Paper Trading forwarding: {e}")
            return False
        
        # Verify forwarding
        time.sleep(1)
        if self.check_port_listening(self.forward_live_port) and self.check_port_listening(self.forward_paper_port):
            self.log("✓ Port forwarding is active")
            self.log(f"  - Live Trading: 0.0.0.0:{self.forward_live_port} -> 127.0.0.1:{self.live_port}")
            self.log(f"  - Paper Trading: 0.0.0.0:{self.forward_paper_port} -> 127.0.0.1:{self.paper_port}")
        else:
            self.log("WARNING: Port forwarding may not be active, check logs")
        
        return True
    
    def start_forwarding(self) -> int:
        """Start socat port forwarding (blocking mode for standalone use)."""
        if not self.start_background():
            return 1
        
        self.log("--- Port forwarding ready ---")
        
        # Set up signal handlers for cleanup
        signal.signal(signal.SIGTERM, self._cleanup)
        signal.signal(signal.SIGINT, self._cleanup)
        
        # Keep running
        try:
            for process in self.processes:
                process.wait()
        except KeyboardInterrupt:
            self._cleanup(None, None)
        
        return 0
    
    def _cleanup(self, signum, frame):
        """Clean up processes on exit."""
        self.log("Cleaning up port forwarding processes...")
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

