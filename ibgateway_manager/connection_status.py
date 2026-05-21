"""
Visual connection status checker for IB Gateway.

Analyzes a screenshot of the IB Gateway UI to determine the connection status
by sampling pixel colors in the Connection Status table's Status column.

Status cells are classified by their background color:
  green  -> connected / ON (healthy)
  yellow -> inactive / warning (degraded — farms wake on demand)
  red    -> error / disconnected (unhealthy for api_server/farms;
            only DEGRADED for api_client — see _compute_overall)
  unknown -> could not classify

The row coordinates are NOT hard-coded to an absolute window position:
the Status table is located at runtime by scanning the Status column for
the coloured band, so the check survives the gateway window sitting at a
different vertical offset.
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
# Layout constants
#
# The Connection Status table has up to four rows; the Status column is a
# wide coloured cell. We sample a column near its midpoint (x≈685) and
# locate the rows vertically at runtime — see _locate_row_centers().
# ---------------------------------------------------------------------------
_ROW_NAMES: List[str] = [
    "api_server",
    "market_data_farm",
    "historical_data_farm",
    "api_client",  # only present once a client has connected this session
]

_STATUS_COLUMN_X = 685       # x within the Status column's coloured cell
_ROW_PITCH = 23              # vertical distance between table rows (px)
_ROW_OFFSET = 12             # first row centre, below the detected band top
_SCAN_TOP, _SCAN_BOTTOM = 90, 460   # vertical search window for the table
_SATURATION_MIN = 45         # min channel spread for a pixel to count "coloured"

# Number of pixels to average around the sample center (7×7 block).
_SAMPLE_RADIUS = 3


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class CellColor(str, Enum):
    GREEN   = "green"    # green channel clearly dominant — connected / ON
    YELLOW  = "yellow"   # red + green both high, blue low — inactive / warning
    RED     = "red"      # red channel clearly dominant — error / disconnected
    UNKNOWN = "unknown"  # gray / no clear colour


class OverallStatus(str, Enum):
    HEALTHY   = "healthy"    # API + farms green — exit 0
    DEGRADED  = "degraded"   # API green; a farm yellow OR api_client not connected — exit 0
    UNHEALTHY = "unhealthy"  # API not green, or a data farm red — exit 1


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
    """Classify an RGB pixel as green, yellow, red, or unknown.

    Uses channel DOMINANCE rather than brittle absolute thresholds: the
    gateway renders status cells anywhere from a dark [0,121,0] green to a
    bright [109,206,109], and a fixed ``g > 150`` test misses the dark end.
    """
    spread = max(r, g, b) - min(r, g, b)
    if spread < _SATURATION_MIN:
        return CellColor.UNKNOWN  # gray / no clear colour
    # Yellow: red AND green both bright, blue low.
    if r > 130 and g > 130 and b < 110:
        return CellColor.YELLOW
    # Red: red channel dominant.
    if r >= g and r >= b:
        return CellColor.RED
    # Green: green channel dominant.
    if g >= r and g >= b:
        return CellColor.GREEN
    return CellColor.UNKNOWN


def _sample_rgb(img: "Image.Image", cx: int, cy: int, radius: int = _SAMPLE_RADIUS) -> Tuple[int, int, int]:
    """Average RGB over a small box centred on (cx, cy)."""
    box = (cx - radius, cy - radius, cx + radius + 1, cy + radius + 1)
    region = img.crop(box).convert("RGB")
    stat = ImageStat.Stat(region)
    return tuple(int(v) for v in stat.mean[:3])  # type: ignore[return-value]


def _is_colored(rgb: Tuple[int, int, int]) -> bool:
    """True when a pixel is clearly coloured (not gray UI chrome)."""
    return max(rgb) - min(rgb) >= _SATURATION_MIN


def _locate_row_centers(img: "Image.Image") -> Optional[List[int]]:
    """Find the y-centres of the status rows.

    Scans the Status column for the top of the coloured status band (three
    consecutive coloured rows), then steps down by the fixed row pitch.
    Returns one y per row in _ROW_NAMES, or None if the table isn't found.
    """
    x = _STATUS_COLUMN_X
    run = 0
    for y in range(_SCAN_TOP, _SCAN_BOTTOM):
        if _is_colored(_sample_rgb(img, x, y, radius=1)):
            run += 1
            if run >= 3:
                top = y - run + 1
                return [
                    top + _ROW_OFFSET + i * _ROW_PITCH
                    for i in range(len(_ROW_NAMES))
                ]
        else:
            run = 0
    return None


def _compute_overall(rows: List[RowStatus]) -> OverallStatus:
    """Determine overall health from the list of row statuses.

    api_server must be green and no data farm may be red. A disconnected
    api_client (red / yellow) is DEGRADED, never UNHEALTHY — the gateway is
    still usable, a client just isn't attached.
    """
    by_name = {r.name: r.color for r in rows}

    api = by_name.get("api_server")
    if api != CellColor.GREEN:
        return OverallStatus.UNHEALTHY

    # A red data farm is a genuine failure.
    for farm in ("market_data_farm", "historical_data_farm"):
        if by_name.get(farm) == CellColor.RED:
            return OverallStatus.UNHEALTHY

    required = ("api_server", "market_data_farm", "historical_data_farm")
    all_required_green = all(
        by_name.get(name) == CellColor.GREEN for name in required
    )
    api_client = by_name.get("api_client")

    if all_required_green and api_client in (CellColor.GREEN, CellColor.UNKNOWN, None):
        # api_client UNKNOWN/absent == no api_client row rendered — fine.
        return OverallStatus.HEALTHY

    # API green + a farm yellow, or api_client disconnected — usable but degraded.
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

    centers = _locate_row_centers(img)
    if centers is None:
        return ConnectionStatus(
            overall=OverallStatus.UNHEALTHY,
            rows=[],
            screenshot_path=path,
            error="Could not locate the Connection Status table in the screenshot",
            timestamp=ts,
        )

    rows: List[RowStatus] = []
    for name, cy in zip(_ROW_NAMES, centers):
        rgb = _sample_rgb(img, _STATUS_COLUMN_X, cy)
        rows.append(RowStatus(name=name, color=_classify_rgb(*rgb), sample_rgb=rgb))

    return ConnectionStatus(
        overall=_compute_overall(rows),
        rows=rows,
        screenshot_path=path,
        error=None,
        timestamp=ts,
    )
