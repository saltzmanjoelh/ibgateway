"""
Screenshot handling functionality.
"""

import os
import subprocess
import time
from typing import Optional

from .config import Config


class ScreenshotHandler:
    """Handles screenshot operations."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
    
    def log(self, message: str):
        """Print log message."""
        if self.verbose:
            print(f"[SCREENSHOT] {message}")
        else:
            print(message)
    
    def validate_path(self, path: str) -> bool:
        """Validate screenshot output path for security."""
        if ".." in path:
            self.log("ERROR: Directory traversal not allowed in output path")
            return False
        
        # Resolve to absolute path
        try:
            resolved = os.path.realpath(path)
            screenshot_dir = os.path.realpath(self.config.screenshot_dir)
            
            # Allow paths within screenshot_dir or /tmp/
            if not (resolved.startswith(screenshot_dir) or resolved.startswith("/tmp/")):
                self.log(f"ERROR: Output path must be within {self.config.screenshot_dir} or /tmp/")
                return False
        except Exception:
            pass
        
        return True
    
    def take_screenshot(self, output_path: Optional[str] = None) -> Optional[str]:
        """Take a screenshot using scrot or imagemagick."""
        os.makedirs(self.config.screenshot_dir, exist_ok=True)
        
        # Generate default output path if not provided
        if not output_path:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.config.screenshot_dir, f"screenshot_{timestamp}.png")
        else:
            if not self.validate_path(output_path):
                return None
        
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        # Try scrot first, then imagemagick
        if self._command_exists("scrot"):
            self.log("Taking screenshot with scrot...")
            cmd = ["scrot", "-z", output_path]
        elif self._command_exists("import"):
            self.log("Taking screenshot with imagemagick...")
            cmd = ["import", "-window", "root", output_path]
        else:
            self.log("ERROR: No screenshot tool available (scrot or imagemagick)")
            return None
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=10
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                self.log(f"Screenshot saved to: {output_path}")
                return output_path
            else:
                self.log(f"ERROR: Screenshot failed: {result.stderr}")
                return None
        except Exception as e:
            self.log(f"ERROR: Error taking screenshot: {e}")
            return None
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        return subprocess.run(
            ["which", command],
            capture_output=True
        ).returncode == 0

