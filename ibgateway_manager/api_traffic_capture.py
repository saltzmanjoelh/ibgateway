"""Capture IB Gateway API wire-protocol traffic and stream it to stdout.

IB Gateway 10.45 only exposes per-client API protocol messages in its
in-process GUI tabs (the ``Client N`` tabs you can see when ``Show API
messages`` is checked). Neither the encrypted ``ibgateway.*.ibgzenc``
files nor the GUI ``Export Logs`` action persist those per-message
records to disk — verified empirically by triggering a real
``reqHistoricalData`` against a logged-in 10.45 gateway and confirming
neither file contained the request/response wire bytes.

The actual jts.ini-based "Create API message log file" toggle is stored
in an encrypted per-account ``ibg.xml`` file that we cannot patch from
outside the gateway, so we can't drive it programmatically.

This module side-steps the whole thing by tapping the wire directly:
``tcpdump -i any -lAns0 port 4002`` runs as a child process and emits
ASCII-decoded packet payloads for every byte exchanged on the IBKR API
socket. Output is appended to a sink file the orchestrator already
tails to stdout, so each captured byte lands in ``docker logs`` /
CloudWatch within ~100ms. The IBKR wire format is mostly printable
ASCII (semicolon-delimited fields, msgIds as decimal ints, contract
fields as plain strings), so the resulting log lines are immediately
readable — they contain the same ``msgId;version;reqId;contract;...``
records you see in the GUI's ``Client N`` tab.

Requires the container to be built with ``tcpdump`` (see
``dockerfile``). Requires ``NET_RAW`` / ``NET_ADMIN`` Linux capabilities
to sniff — ECS Fargate task definitions for this image need to declare
them in ``linuxParameters.capabilities.add``.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import List, Optional

_logger = logging.getLogger(__name__)


# Stream sink — orchestrator's tail process already includes this path
# in its tail-to-stdout set, so anything written here lands in
# ``docker logs`` (and CloudWatch in deployed setups).
DEFAULT_SINK_PATH = "/tmp/ibgateway-api-traffic.log"


def _default_ports() -> tuple:
    """The TCP port(s) the local IB Gateway's API server listens on.

    Default to 4002 (paper trading — the codebase's default mode).
    Override via ``IBGATEWAY_API_TRAFFIC_PORTS`` env var:
    comma-separated integers, e.g. ``4001`` for live or ``4001,4002``
    for both.

    We intentionally avoid the obvious "4001 or 4002 or 4003 or 4004"
    catch-all because 4001 is also the remote IBKR CCP server port —
    capturing on port 4001 unconditionally would pull in megabytes of
    gateway↔IBKR encrypted TLS noise we can't read anyway. Capturing
    just the LISTENING port keeps the signal-to-noise ratio honest.
    """
    raw = os.getenv("IBGATEWAY_API_TRAFFIC_PORTS", "")
    if not raw.strip():
        return (4002,)
    try:
        return tuple(int(p.strip()) for p in raw.split(",") if p.strip())
    except ValueError:
        _logger.warning(
            "IBGATEWAY_API_TRAFFIC_PORTS=%r is not a comma-separated "
            "integer list; falling back to default 4002.", raw,
        )
        return (4002,)


# Lazily resolved at construction time so tests can monkeypatch the env
# var per-test and the value reflects the runtime environment, not the
# import-time environment.
DEFAULT_PORTS = None  # type: ignore[assignment]  # resolved in __init__


class ApiTrafficCapture:
    """Run ``tcpdump`` against the IBKR API port and pipe output to a sink.

    Lifecycle:
      * ``start()`` — locate ``tcpdump`` on PATH, launch it with stdout
        redirected to the sink file. Non-blocking; the subprocess runs
        independently. Returns ``True`` on success, ``False`` if
        ``tcpdump`` is missing.
      * ``stop()`` — terminate the subprocess. Idempotent.
      * ``is_running()`` — true iff the subprocess is alive.

    The class never raises out of public methods; failures are logged
    and the orchestrator continues without traffic capture. Missing
    traffic visibility is degraded service, not fatal.
    """

    def __init__(
        self,
        sink_path: str = DEFAULT_SINK_PATH,
        ports: Optional[tuple] = None,
        interface: str = "any",
        tcpdump_path: Optional[str] = None,
    ) -> None:
        self.sink_path = Path(sink_path)
        self.ports = tuple(ports) if ports is not None else _default_ports()
        self.interface = interface
        self.tcpdump_path = tcpdump_path
        self._proc: Optional[subprocess.Popen] = None
        self._stop_signaled = threading.Event()

    def start(self) -> bool:
        """Spawn tcpdump. Returns True on success, False if unavailable."""
        path = self.tcpdump_path or shutil.which("tcpdump")
        if not path:
            _logger.warning(
                "api-traffic-capture: tcpdump not found on PATH; "
                "wire-protocol capture disabled."
            )
            return False

        self.sink_path.parent.mkdir(parents=True, exist_ok=True)
        # We append, not truncate — restart cycles preserve previous
        # capture, and the orchestrator's tail -F handles rotation.
        sink = self.sink_path.open("ab")

        # Build the filter expression: 'port 4001 or port 4002 or ...'
        # tcpdump's expression language uses 'or' between terms.
        port_filter = " or ".join(f"port {p}" for p in self.ports)

        # Flags:
        #   -i any   : sniff all interfaces (the IBKR socket lives on
        #              lo when both client and gateway are in-container,
        #              eth0 when a host-mapped client connects)
        #   -l       : line-buffer stdout so each packet flushes
        #              immediately (without this, tcpdump batches and
        #              CloudWatch lags by minutes)
        #   -A       : ASCII-print the payload, no hex column
        #   -n       : no DNS lookups (faster + offline-safe)
        #   -s 0     : capture full packet (default 96-byte snaplen
        #              truncates the IBKR payload)
        argv = [
            path, "-i", self.interface, "-l", "-A", "-n", "-s", "0",
            port_filter,
        ]
        try:
            self._proc = subprocess.Popen(
                argv,
                stdout=sink,
                stderr=subprocess.STDOUT,
            )
        except (OSError, ValueError) as exc:
            # Most commonly: explicitly passed ``tcpdump_path`` points
            # at a non-existent file, or the user lacks the right
            # capabilities to exec tcpdump. Both are degraded service,
            # not fatal.
            _logger.warning(
                "api-traffic-capture: failed to spawn tcpdump (%s); "
                "wire-protocol capture disabled.",
                exc,
            )
            self._proc = None
            return False
        finally:
            # tcpdump inherits the fd; we close our copy so the sink
            # isn't held open by Python for no reason.
            sink.close()

        _logger.info(
            "api-traffic-capture: tcpdump pid=%s capturing %s -> %s",
            self._proc.pid, port_filter, self.sink_path,
        )
        return True

    def stop(self) -> None:
        """Terminate the tcpdump subprocess. Idempotent."""
        self._stop_signaled.set()
        if self._proc is None:
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
        except Exception:
            pass
        try:
            self._proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                self._proc.kill()
            except Exception:
                pass
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None
