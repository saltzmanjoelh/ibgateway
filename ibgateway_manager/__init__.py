"""
IB Gateway CLI Package
Consolidates all IB Gateway automation, screenshot, testing, and management functionality.
"""

__version__ = "1.0.0"

from .cli import IBGatewayCLI
from .config import Config
from .automate_ibgateway import AutomationHandler
from .screenshot import ScreenshotHandler
from .port_forwarder import PortForwarder

__all__ = [
    "IBGatewayCLI",
    "Config",
    "AutomationHandler",
    "ScreenshotHandler",
    "PortForwarder",
]

