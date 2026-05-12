"""Configure IB Gateway to emit a plaintext API log we can tail to stdout.

IB Gateway's GUI exposes the toggle at:
    Configure → Settings → API → Settings → "Create API message log file"
    Configure → Settings → API → Settings → "Logging Level" (we want Detail)

When enabled, IB Gateway writes plaintext ``api.YYYYMMDD.log`` files
alongside its rotating encrypted ``ibgateway.*.ibgzenc`` files, inside
the per-account Jts subdirectory (e.g.
``~/Jts/<account-encoded-id>/api.20260512.log``).

The toggle persists in ``~/Jts/jts.ini``. We pre-seed the relevant keys
**before** launching the Java process so we don't depend on the user
clicking through the GUI after every fresh task. Idempotent: re-running
only writes the section / keys when they're missing or wrong.

IB Gateway tolerates unknown keys, so we set all known-relevant variants
across versions defensively:

    [Logging]
    LogLevel=5
    LogComponents=ALL
    LogFile=true

    [IBGateway]
    ApiLogLevel=5
    WriteAPIMessages=true

If ``jts.ini`` doesn't exist yet (cold start before first login), we
create a minimal stub with just these sections. IB Gateway fills the
rest in on its first save.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Mapping

_logger = logging.getLogger(__name__)


# Section name → {key: value}. Strings only — jts.ini values are not typed.
_REQUIRED_KEYS: Dict[str, Dict[str, str]] = {
    "Logging": {
        "LogLevel": "5",
        "LogComponents": "ALL",
        "LogFile": "true",
    },
    "IBGateway": {
        "ApiLogLevel": "5",
        "WriteAPIMessages": "true",
    },
}


class JtsLogConfig:
    """Patch (or create) ``~/Jts/jts.ini`` to enable plaintext API logging."""

    def __init__(self, jts_dir: str = "/root/Jts") -> None:
        self.jts_dir = Path(jts_dir)
        self.ini_path = self.jts_dir / "jts.ini"

    def apply(self) -> None:
        """Merge the required logging keys into jts.ini. Idempotent."""
        self.jts_dir.mkdir(parents=True, exist_ok=True)
        existing = self._read()
        merged = self._merge(existing, _REQUIRED_KEYS)
        if merged == existing:
            _logger.info("jts.ini already has required logging keys; no change.")
            return
        self._write(merged)
        _logger.info("Patched %s with API-logging keys.", self.ini_path)

    # ----- internals ----------------------------------------------------

    def _read(self) -> Dict[str, Dict[str, str]]:
        """Parse jts.ini into ``{section: {key: value}}``. Tolerates
        non-existent file and bare lines (which IB Gateway sometimes
        writes outside any section)."""
        if not self.ini_path.is_file():
            return {}
        result: Dict[str, Dict[str, str]] = {}
        current = ""
        # Use a permissive line-by-line parser rather than configparser
        # — jts.ini sometimes has duplicate keys and unusual quoting that
        # configparser rejects. We only care about the few keys we own.
        for raw in self.ini_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                result.setdefault(current, {})
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            result.setdefault(current, {})[key.strip()] = value.strip()
        return result

    def _merge(
        self,
        existing: Mapping[str, Mapping[str, str]],
        required: Mapping[str, Mapping[str, str]],
    ) -> Dict[str, Dict[str, str]]:
        merged: Dict[str, Dict[str, str]] = {
            section: dict(keys) for section, keys in existing.items()
        }
        for section, keys in required.items():
            target = merged.setdefault(section, {})
            for key, value in keys.items():
                target[key] = value
        return merged

    def _write(self, data: Mapping[str, Mapping[str, str]]) -> None:
        """Write back as INI. Preserve section order: existing sections
        first (in their original order via dict insertion order), then
        any new ones we added."""
        lines = []
        for section, keys in data.items():
            if section:
                lines.append(f"[{section}]")
            for key, value in keys.items():
                lines.append(f"{key}={value}")
            lines.append("")  # blank line between sections
        self.ini_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
