"""
Port forwarding functionality (pure Python TCP forwarder).
"""

import signal
import time
import socket
import socketserver
import threading
from typing import List, Optional, Tuple

from .config import Config


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _ForwardHandler(socketserver.BaseRequestHandler):
    """TCP proxy handler forwarding to a fixed upstream."""

    upstream: Tuple[str, int]

    def handle(self) -> None:
        upstream_host, upstream_port = self.upstream
        try:
            with socket.create_connection((upstream_host, upstream_port), timeout=2.0) as upstream:
                self.request.settimeout(2.0)
                upstream.settimeout(2.0)

                # Relay both directions until either side closes.
                stop = threading.Event()

                def _pipe(src: socket.socket, dst: socket.socket) -> None:
                    try:
                        while not stop.is_set():
                            try:
                                data = src.recv(65536)
                            except socket.timeout:
                                continue
                            if not data:
                                break
                            dst.sendall(data)
                    finally:
                        stop.set()
                        try:
                            dst.shutdown(socket.SHUT_RDWR)
                        except Exception:
                            pass

                t1 = threading.Thread(target=_pipe, args=(self.request, upstream), daemon=True)
                t2 = threading.Thread(target=_pipe, args=(upstream, self.request), daemon=True)
                t1.start()
                t2.start()
                t1.join()
                t2.join()
        except Exception:
            # Best-effort: if upstream is down, just drop the connection.
            return


class PortForwarder:
    """Handles port forwarding using a pure-Python TCP proxy."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.live_port = getattr(config, "ib_live_port", 4001)
        self.paper_port = getattr(config, "ib_paper_port", 4002)
        self.forward_live_port = getattr(config, "forward_live_port", 4003)
        self.forward_paper_port = getattr(config, "forward_paper_port", 4004)
        self._servers: List[_ThreadingTCPServer] = []
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._sleep_scale = float(getattr(config, "sleep_scale", 1.0) or 1.0)
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[PORT-FORWARD] {message}")
        else:
            print(message)

    def _sleep(self, seconds: float) -> None:
        scaled = seconds * self._sleep_scale
        if scaled <= 0:
            return
        time.sleep(scaled)
    
    def check_port_listening(self, port: int) -> bool:
        """Check if a port is listening."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                return s.connect_ex(("127.0.0.1", int(port))) == 0
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
            
            self._sleep(1)
            elapsed += 1
        
        self.log(f"WARNING: IB Gateway ports not available after {timeout}s, starting forwarding anyway")
        return False
    
    def start_forwarding(self, *, run_seconds: Optional[float] = None) -> int:
        """Start TCP port forwarding.

        If run_seconds is provided, the forwarder runs for that duration then exits.
        """
        self.log("=== Starting TCP port forwarding ===")
        self.log(f"Forwarding {self.forward_live_port} -> 127.0.0.1:{self.live_port} (Live Trading)")
        self.log(f"Forwarding {self.forward_paper_port} -> 127.0.0.1:{self.paper_port} (Paper Trading)")
        
        # Wait for ports
        self.wait_for_ports()

        # Start Live Trading forwarding server
        self.log(f"Starting forwarding for Live Trading ({self.forward_live_port} -> 127.0.0.1:{self.live_port})...")
        live_server = self._start_server(self.forward_live_port, ("127.0.0.1", self.live_port))
        self.log("✓ Live Trading forwarding started")

        # Start Paper Trading forwarding server
        self.log(f"Starting forwarding for Paper Trading ({self.forward_paper_port} -> 127.0.0.1:{self.paper_port})...")
        paper_server = self._start_server(self.forward_paper_port, ("127.0.0.1", self.paper_port))
        self.log("✓ Paper Trading forwarding started")

        # Verify forwarding
        self._sleep(0.2)
        if self.check_port_listening(self.forward_live_port) and self.check_port_listening(self.forward_paper_port):
            self.log("✓ Port forwarding is active")
            self.log(f"  - Live Trading: 0.0.0.0:{self.forward_live_port} -> 127.0.0.1:{self.live_port}")
            self.log(f"  - Paper Trading: 0.0.0.0:{self.forward_paper_port} -> 127.0.0.1:{self.paper_port}")
            self.log("=== Port forwarding ready ===")
        else:
            self.log("WARNING: Port forwarding may not be active, check logs")
        
        # Set up signal handlers for cleanup
        try:
            signal.signal(signal.SIGTERM, self._cleanup)
            signal.signal(signal.SIGINT, self._cleanup)
        except ValueError:
            # Signal handlers can only be set in the main thread.
            pass

        try:
            if run_seconds is not None:
                self._sleep(float(run_seconds))
                self._cleanup(None, None)
                return 0

            # Keep running
            while not self._stop_event.is_set():
                self._sleep(0.5)
        except KeyboardInterrupt:
            self._cleanup(None, None)

        return 0

    def _start_server(self, listen_port: int, upstream: Tuple[str, int]) -> _ThreadingTCPServer:
        handler_cls = type(
            f"ForwardHandler_{listen_port}",
            (_ForwardHandler,),
            {"upstream": upstream},
        )
        srv: _ThreadingTCPServer = _ThreadingTCPServer(("0.0.0.0", int(listen_port)), handler_cls)
        self._servers.append(srv)
        t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        self._threads.append(t)
        t.start()
        return srv
    
    def _cleanup(self, signum, frame):
        """Clean up processes on exit."""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.log("Cleaning up port forwarding servers...")
        for srv in list(self._servers):
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        self._servers.clear()

