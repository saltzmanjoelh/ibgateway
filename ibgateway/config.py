"""
Configuration management for IB Gateway CLI.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


class Config:
    """Configuration management with .env file and environment variable support."""
    
    def __init__(self):
        self.load_config()
    
    def load_config(self):
        """Load configuration from .env file and environment variables."""
        # Try to load .env file from script directory or current directory
        script_dir = Path(__file__).parent.parent
        env_files = [
            script_dir / ".env",
            Path(".env"),
            Path.cwd() / ".env"
        ]
        
        for env_file in env_files:
            if env_file.exists() and HAS_DOTENV:
                load_dotenv(env_file)
                break
        
        # Configuration values (env vars override .env file)
        self.username = os.getenv("IB_USERNAME", "")
        self.password = os.getenv("IB_PASSWORD", "")
        self.api_type = os.getenv("IB_API_TYPE", "IB_API").upper()
        self.trading_mode = os.getenv("IB_TRADING_MODE", "PAPER").upper()
        self.display = os.getenv("DISPLAY", ":99")
        self.resolution = os.getenv("RESOLUTION", "1024x768")
        self.screenshot_dir = os.getenv("SCREENSHOT_DIR", "/tmp/screenshots")
        self.screenshot_port = int(os.getenv("SCREENSHOT_PORT", "8080"))

        # Tooling/config overrides for hermetic execution (useful for tests/CI).
        self.xdotool_bin = os.getenv("XDOTOOL_BIN", "xdotool")
        self.xdotool_timeout = float(os.getenv("XDOTOOL_TIMEOUT", "10"))
        self.sleep_scale = float(os.getenv("IBGATEWAY_SLEEP_SCALE", "1"))
        self.window_search_timeout = int(os.getenv("IBGATEWAY_WINDOW_TIMEOUT", "60"))

        # Screenshot backend controls.
        # - "auto" (default): try scrot/import, then fallback to Pillow placeholder.
        # - "python": always generate a placeholder PNG via Pillow.
        self.screenshot_backend = os.getenv("SCREENSHOT_BACKEND", "auto").lower()
        self.screenshot_allow_fallback = os.getenv("SCREENSHOT_ALLOW_FALLBACK", "1") not in ("0", "false", "no")

        # Port forwarding configuration.
        self.ib_live_port = int(os.getenv("IB_LIVE_PORT", "4001"))
        self.ib_paper_port = int(os.getenv("IB_PAPER_PORT", "4002"))
        self.forward_live_port = int(os.getenv("IB_FORWARD_LIVE_PORT", "4003"))
        self.forward_paper_port = int(os.getenv("IB_FORWARD_PAPER_PORT", "4004"))

        # CLI command overrides.
        self.curl_bin = os.getenv("CURL_BIN", "curl")
        self.xvfb_bin = os.getenv("XVFB_BIN", "Xvfb")
        self.ibgateway_bin = os.getenv("IBGATEWAY_BIN", "/opt/ibgateway/ibgateway")
        
        # Validate API type
        if self.api_type not in ["FIX", "IB_API"]:
            raise ValueError(f"IB_API_TYPE must be 'FIX' or 'IB_API', got: {self.api_type}")
        
        # Validate trading mode
        if self.trading_mode not in ["LIVE", "PAPER"]:
            raise ValueError(f"IB_TRADING_MODE must be 'LIVE' or 'PAPER', got: {self.trading_mode}")
    
    def print_config(self):
        """Print current configuration."""
        print("=== IB Gateway Configuration ===")
        print(f"Username: {self.username if self.username else '(not set)'}")
        print(f"Password: {'***' if self.password else '(not set)'}")
        print(f"API Type: {self.api_type}")
        print(f"Trading Mode: {self.trading_mode}")
        print(f"Display: {self.display}")
        print(f"Resolution: {self.resolution}")
        print(f"Screenshot Directory: {self.screenshot_dir}")
        print(f"Screenshot Port: {self.screenshot_port}")
        print()

