"""
Visual connection status checker for IB Gateway.

Analyzes a screenshot of the IB Gateway UI to determine the connection status
by sampling pixel colors in the Connection Status table's Status column.

Status cells are classified by their background color:
  green  -> connected / ON (healthy)
  yellow -> inactive / warning (degraded — farms wake on demand)
  red    -> error / disconnected (unhealthy)
  unknown -> could not classify (treated as unhealthy)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

try:
    from PIL import Image, ImageStat
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

from .config import Config
from .screenshot import ScreenshotHandler


# ---------------------------------------------------------------------------
# Row coordinate table
# Coordinates assume the IB Gateway window has been moved to (0, 0).
# Each entry is (row_name, center_x, center_y) within the full display image.
# The Status column spans x≈510-850; we sample at x=685 (midpoint).
# ---------------------------------------------------------------------------
_STATUS_ROWS: List[Tuple[str, int, int]] = [
    ("api_server",           685, 183),
    ("market_data_farm",     685, 207),
    ("historical_data_farm", 685, 230),
    ("api_client",           685, 252),  # only present when clients are connected
]

# Number of pixels to average around the sample center (7×7 block).
_SAMPLE_RADIUS = 3


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class CellColor(str, Enum):
    GREEN   = "green"    # R<150, G>150, B<100 — connected / ON
    YELLOW  = "yellow"   # R>150, G>150, B<100 — inactive / warning
    RED     = "red"      # R>150, G<80,  B<80  — error / disconnected
    UNKNOWN = "unknown"  # does not match any threshold


class OverallStatus(str, Enum):
    HEALTHY   = "healthy"    # All rows green — exit 0
    DEGRADED  = "degraded"   # API green, ≥1 farm yellow — exit 0 (farms wake on demand)
    UNHEALTHY = "unhealthy"  # Any red, or API not green — exit 1


@dataclass
class RowStatus:
    name: str
    color: CellColor
    sample_rgb: Tuple[int, int, int]


@dataclass
class ConnectionStatus:
    overall: OverallStatus
    rows: List[RowStatus]
    screenshot_path: Optional[str]
    error: Optional[str]
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "overall": self.overall.value,
            "rows": [
                {
                    "name": r.name,
                    "color": r.color.value,
                    "sample_rgb": list(r.sample_rgb),
                }
                for r in self.rows
            ],
            "screenshot_path": self.screenshot_path,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Pure helper functions (no I/O — easy to unit-test)
# ---------------------------------------------------------------------------

def _classify_rgb(r: int, g: int, b: int) -> CellColor:
    """Classify an RGB pixel as green, yellow, red, or unknown."""
    if r < 150 and g > 150 and b < 150:
        return CellColor.GREEN
    if r > 150 and g > 150 and b < 100:
        return CellColor.YELLOW
    if r > 150 and g < 80 and b < 80:
        return CellColor.RED
    return CellColor.UNKNOWN


def _sample_rgb(img: "Image.Image", cx: int, cy: int, radius: int = _SAMPLE_RADIUS) -> Tuple[int, int, int]:
    """Average RGB over a small box centred on (cx, cy)."""
    box = (cx - radius, cy - radius, cx + radius + 1, cy + radius + 1)
    region = img.crop(box).convert("RGB")
    stat = ImageStat.Stat(region)
    return tuple(int(v) for v in stat.mean[:3])  # type: ignore[return-value]


def _compute_overall(rows: List[RowStatus]) -> OverallStatus:
    """Determine overall health from the list of row statuses."""
    # Any RED anywhere -> UNHEALTHY
    if any(r.color == CellColor.RED for r in rows):
        return OverallStatus.UNHEALTHY

    api_row = next((r for r in rows if r.name == "api_server"), None)

    # API Server must be GREEN; UNKNOWN or YELLOW is not acceptable
    if api_row is None or api_row.color != CellColor.GREEN:
        return OverallStatus.UNHEALTHY

    # Farm rows: GREEN or YELLOW are both acceptable
    # api_client is optional (only present when clients are connected); unknown is OK there
    required_rows = [r for r in rows if r.name in ("market_data_farm", "historical_data_farm")]
    for row in required_rows:
        if row.color not in (CellColor.GREEN, CellColor.YELLOW):
            return OverallStatus.UNHEALTHY

    _required = {"api_server", "market_data_farm", "historical_data_farm"}
    required_all_green = all(r.color == CellColor.GREEN for r in rows if r.name in _required)
    api_client = next((r for r in rows if r.name == "api_client"), None)
    api_client_ok = api_client is None or api_client.color in (CellColor.GREEN, CellColor.UNKNOWN)

    if required_all_green and api_client_ok:
        return OverallStatus.HEALTHY

    # API is green, at least one required farm is yellow
    return OverallStatus.DEGRADED


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_connection_status(config: Config) -> ConnectionStatus:
    """Take a screenshot and analyse the IB Gateway Connection Status table.

    Returns a ConnectionStatus dataclass describing the overall health and
    the per-row color classification.
    """
    ts = time.time()

    if not HAS_PIL:
        return ConnectionStatus(
            overall=OverallStatus.UNHEALTHY,
            rows=[],
            screenshot_path=None,
            error="PIL/Pillow is not installed — cannot analyse screenshot",
            timestamp=ts,
        )

    handler = ScreenshotHandler(config, verbose=False)
    path = handler.take_screenshot()

    if not path:
        return ConnectionStatus(
            overall=OverallStatus.UNHEALTHY,
            rows=[],
            screenshot_path=None,
            error="Failed to capture screenshot",
            timestamp=ts,
        )

    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        return ConnectionStatus(
            overall=OverallStatus.UNHEALTHY,
            rows=[],
            screenshot_path=path,
            error=f"Failed to open screenshot: {exc}",
            timestamp=ts,
        )

    rows: List[RowStatus] = []
    for name, cx, cy in _STATUS_ROWS:
        rgb = _sample_rgb(img, cx, cy)
        rows.append(RowStatus(name=name, color=_classify_rgb(*rgb), sample_rgb=rgb))

    return ConnectionStatus(
        overall=_compute_overall(rows),
        rows=rows,
        screenshot_path=path,
        error=None,
        timestamp=ts,
    )
