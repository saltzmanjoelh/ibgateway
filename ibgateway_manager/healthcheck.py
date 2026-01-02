"""
Docker HEALTHCHECK helper for IB Gateway.

Container should only be considered healthy once IB Gateway is actually accepting
TCP connections on the internal API port:
  - LIVE  -> 127.0.0.1:4001
  - PAPER -> 127.0.0.1:4002
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HealthcheckConfig:
    host: str
    port: int
    timeout_seconds: float


def _port_for_trading_mode(trading_mode: str) -> int:
    mode = (trading_mode or "").strip().upper()
    if mode == "LIVE":
        return 4001
    if mode == "PAPER":
        return 4002
    raise ValueError(f"IB_TRADING_MODE must be LIVE or PAPER (got {trading_mode!r})")


def build_config_from_env() -> HealthcheckConfig:
    trading_mode = os.getenv("IB_TRADING_MODE", "PAPER")
    port = _port_for_trading_mode(trading_mode)

    # Keep this very small by default; Docker's healthcheck retry loop handles rest.
    timeout_s_raw = os.getenv("IBGATEWAY_HEALTHCHECK_TIMEOUT_SECONDS", "1.5").strip()
    try:
        timeout_s = float(timeout_s_raw)
    except ValueError as exc:
        raise ValueError(
            "IBGATEWAY_HEALTHCHECK_TIMEOUT_SECONDS must be a number "
            f"(got {timeout_s_raw!r})"
        ) from exc

    return HealthcheckConfig(host="127.0.0.1", port=port, timeout_seconds=timeout_s)


def check_tcp_listening(cfg: HealthcheckConfig) -> bool:
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout_seconds):
            return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    _ = argv  # reserved; keep signature stable for future flags if needed
    try:
        cfg = build_config_from_env()
    except Exception as exc:
        print(f"[HEALTHCHECK] invalid config: {exc}", file=sys.stderr, flush=True)
        return 1

    ok = check_tcp_listening(cfg)
    if ok:
        return 0

    # Provide a tiny bit of context for debugging `docker inspect` health logs.
    print(
        f"[HEALTHCHECK] not ready: tcp://{cfg.host}:{cfg.port} (timeout={cfg.timeout_seconds}s)",
        file=sys.stderr,
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


