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
        
        # Validate API type
        if self.api_type not in ["FIX", "IB_API"]:
            raise ValueError(f"IB_API_TYPE must be 'FIX' or 'IB_API', got: {self.api_type}")
        
        # Validate trading mode
        if self.trading_mode not in ["LIVE", "PAPER"]:
            raise ValueError(f"IB_TRADING_MODE must be 'LIVE' or 'PAPER', got: {self.trading_mode}")
    
    def print_config(self):
        """Print current configuration."""
        print("--- IB Gateway Configuration ---")
        print(f"Username: {self.username if self.username else '(not set)'}")
        print(f"Password: {'***' if self.password else '(not set)'}")
        print(f"API Type: {self.api_type}")
        print(f"Trading Mode: {self.trading_mode}")
        print(f"Display: {self.display}")
        print(f"Resolution: {self.resolution}")
        print(f"Screenshot Directory: {self.screenshot_dir}")
        print(f"Screenshot Port: {self.screenshot_port}")
        print()

