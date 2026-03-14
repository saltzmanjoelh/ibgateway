"""
Docker HEALTHCHECK helper for IB Gateway.

Primary check: visual analysis via the screenshot server's /health endpoint,
which captures a screenshot and classifies the Connection Status table cell colors.

Fallback: TCP connection test to the internal API port (used when the screenshot
server is not yet available during container startup):
  - LIVE  -> 127.0.0.1:4001
  - PAPER -> 127.0.0.1:4002
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
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


def check_visual_health(timeout: float) -> tuple[str, dict | None]:
    """Call the screenshot server's /health endpoint for a visual status check.

    Returns (status_str, detail_dict_or_None) where status_str is one of:
      "healthy"     - API connected, all farms green
      "degraded"    - API connected, some farms inactive (yellow) — still OK
      "unhealthy"   - a red cell detected, or API not connected
      "unavailable" - screenshot server not yet up; caller should fall back to TCP
    """
    url = "http://127.0.0.1:8080/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return body.get("overall", "unhealthy"), body
    except urllib.error.HTTPError as exc:
        # 503 means the server is up but the gateway is unhealthy
        try:
            body = json.loads(exc.read().decode())
            return body.get("overall", "unhealthy"), body
        except Exception:
            return "unhealthy", None
    except (urllib.error.URLError, OSError):
        # Server not listening yet — fall back to TCP
        return "unavailable", None
    except Exception:
        return "unhealthy", None


def main(argv: list[str] | None = None) -> int:
    _ = argv  # reserved; keep signature stable for future flags if needed
    try:
        cfg = build_config_from_env()
    except Exception as exc:
        print(f"[HEALTHCHECK] invalid config: {exc}", file=sys.stderr, flush=True)
        return 1

    # --- Visual check (preferred) ---
    visual_status, detail = check_visual_health(timeout=cfg.timeout_seconds)

    screenshot_path = detail.get("screenshot_path") if detail else None
    screenshot_info = f" | screenshot: {screenshot_path}" if screenshot_path else ""

    if visual_status == "healthy":
        print(f"[HEALTHCHECK] healthy{screenshot_info}", file=sys.stderr, flush=True)
        return 0

    if visual_status == "degraded":
        rows = detail.get("rows", []) if detail else []
        summary = ", ".join(f"{r['name']}={r['color']}" for r in rows)
        print(f"[HEALTHCHECK] degraded: {summary}{screenshot_info}", file=sys.stderr, flush=True)
        return 0

    if visual_status == "unhealthy":
        error_msg = detail.get("error") if detail else None
        rows = detail.get("rows", []) if detail else []
        summary = ", ".join(f"{r['name']}={r['color']}" for r in rows) if rows else "no row data"
        print(
            f"[HEALTHCHECK] unhealthy (visual): {summary}{screenshot_info}"
            + (f" | error: {error_msg}" if error_msg else ""),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # visual_status == "unavailable": screenshot server not yet up, fall back to TCP
    ok = check_tcp_listening(cfg)
    if ok:
        print(f"[HEALTHCHECK] healthy (tcp fallback): {cfg.host}:{cfg.port}", file=sys.stderr, flush=True)
        return 0

    print(
        f"[HEALTHCHECK] not ready: tcp://{cfg.host}:{cfg.port} (timeout={cfg.timeout_seconds}s)"
        " and visual check unavailable",
        file=sys.stderr,
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


