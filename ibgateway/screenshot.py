"""
Screenshot handling functionality.
"""

import os
import subprocess
import time
from typing import Optional, Dict, Any

try:
    from PIL import Image, ImageChops, ImageStat
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

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


def compare_images_pil(
    img1_path: str,
    img2_path: str,
    *,
    threshold: float = 0.01,
    max_diff_percentage: float = 1.0,
) -> Dict[str, Any]:
    """Compare two images with Pillow and return similarity metrics.

    Args:
        img1_path: Reference image path
        img2_path: Current image path
        threshold: Mean pixel diff threshold as a fraction of 255
        max_diff_percentage: Max percentage of pixels that may differ

    Returns:
        Dict containing mean_diff, max_diff, diff_percentage, is_similar, has_changes, is_match
    """
    if not HAS_PIL:
        raise RuntimeError("Pillow is required for image comparison (install Pillow).")

    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)

    if img1.size != img2.size:
        raise ValueError(f"Images have different sizes: {img1.size} vs {img2.size}")

    if img1.mode != "RGB":
        img1 = img1.convert("RGB")
    if img2.mode != "RGB":
        img2 = img2.convert("RGB")

    # Work in grayscale for easy pixel-diff counting.
    diff = ImageChops.difference(img1, img2).convert("L")
    stat = ImageStat.Stat(diff)

    mean_diff = float(stat.mean[0])
    hist = diff.histogram()  # 256 bins
    max_diff = int(max(i for i, count in enumerate(hist) if count))

    total_pixels = img1.size[0] * img1.size[1]
    zero_pixels = int(hist[0])
    different_pixels = total_pixels - zero_pixels
    diff_percentage = (different_pixels / total_pixels) * 100 if total_pixels else 0.0

    is_similar = mean_diff < (255.0 * threshold)
    has_changes = diff_percentage > max_diff_percentage
    is_match = is_similar and (not has_changes)

    return {
        "mean_diff": mean_diff,
        "max_diff": max_diff,
        "diff_percentage": diff_percentage,
        "is_similar": is_similar,
        "has_changes": has_changes,
        "is_match": is_match,
    }

