"""
IB Gateway GUI automation handler using xdotool.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .config import Config
from .screenshot import ScreenshotHandler, compare_images_pil


class AutomationHandler:
    """Handles IB Gateway GUI automation using xdotool."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        
        # Button coordinates (relative to content window)
        self.FIX_BUTTON_X = 311
        self.FIX_BUTTON_Y = 212
        self.IB_API_BUTTON_X = 510
        self.IB_API_BUTTON_Y = 212
        self.LIVE_TRADING_BUTTON_X = 311
        self.LIVE_TRADING_BUTTON_Y = 212
        self.PAPER_TRADING_BUTTON_X = 506
        self.PAPER_TRADING_BUTTON_Y = 229
    
    def log(self, message: str):
        """Print log message if verbose."""
        if self.verbose:
            print(f"[AUTOMATION] {message}", flush=True)
        else:
            print(message, flush=True)
    
    def run_xdotool(self, *args) -> Optional[str]:
        """Run xdotool command and return output."""
        cmd = ["xdotool"] + list(args)
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except subprocess.TimeoutExpired:
            self.log(f"Timeout running: {' '.join(cmd)}")
            return None
        except Exception as e:
            self.log(f"Error running xdotool: {e}")
            return None
    
    def find_ibgateway_window(self, timeout: int = 60) -> Optional[str]:
        """Find IB Gateway window using multiple search methods."""
        self.log("Waiting for IB Gateway window to appear...")
        
        elapsed = 0
        while elapsed < timeout:
            # Try multiple search methods
            window_id = self.run_xdotool("search", "--name", "IBKR Gateway")
            if window_id:
                self.log(f"✓ IB Gateway window found! Window ID: {window_id}")
                return window_id.split()[0] if window_id else None
            
            time.sleep(1)
            elapsed += 1
        
        self.log(f"ERROR: IB Gateway window not found after {timeout}s")
        return None
    
    def click_at_coordinates(self, window_id: str, x: int, y: int, button_name: str):
        """Click at coordinates in the specified window."""
        self.log(f"Clicking {button_name} at coordinates ({x}, {y})")
        
        # Move mouse to location
        self.run_xdotool("mousemove", str(x), str(y))
        time.sleep(0.3)
        
        # Click
        self.run_xdotool("click", "1")
        self.run_xdotool("click", "1")
        time.sleep(0.5)
        
        self.log(f"✓ Clicked {button_name}")
    
    def click_api_type_button(self, window_id: str):
        """Click the API type button (FIX or IB_API)."""
        self.log(f"--- Configuring API Type: {self.config.api_type} ---")
        
        if self.config.api_type == "FIX":
            self.click_at_coordinates(
                window_id,
                self.FIX_BUTTON_X,
                self.FIX_BUTTON_Y,
                "FIX CTCI"
            )
        else:
            self.click_at_coordinates(
                window_id,
                self.IB_API_BUTTON_X,
                self.IB_API_BUTTON_Y,
                "IB API"
            )
    
    def click_trading_mode_button(self, window_id: str):
        """Click the trading mode button (LIVE or PAPER)."""
        self.log(f"--- Configuring Trading Mode: {self.config.trading_mode} ---")
        
        if self.config.trading_mode == "LIVE":
            self.click_at_coordinates(
                window_id,
                self.LIVE_TRADING_BUTTON_X,
                self.LIVE_TRADING_BUTTON_Y,
                "Live Trading"
            )
        else:
            self.click_at_coordinates(
                window_id,
                self.PAPER_TRADING_BUTTON_X,
                self.PAPER_TRADING_BUTTON_Y,
                "Paper Trading"
            )
        time.sleep(1)
    
    def type_username(self, window_id: str):
        """Type username into the focused field."""
        if not self.config.username:
            self.log("Skipping username entry (IB_USERNAME not set)")
            return
        
        self.log("--- Typing Username ---")
        self.run_xdotool("type", "--delay", "50", self.config.username)
        time.sleep(0.5)
        self.log("✓ Username typed")
    
    def type_password(self, window_id: str):
        """Type password (tab to password field first)."""
        if not self.config.password:
            self.log("Skipping password entry (IB_PASSWORD not set)")
            return
        
        self.log("--- Typing Password ---")
        self.run_xdotool("key", "Tab")
        time.sleep(0.3)
        self.run_xdotool("type", "--delay", "50", self.config.password)
        time.sleep(0.5)
        self.log("✓ Password typed")
        self.run_xdotool("key", "Return")
    
    def list_all_windows(self):
        """List all windows with their IDs and names."""
        self.log("--- Listing All Windows ---")
        window_ids_output = self.run_xdotool("search", "--all", ".")
        if not window_ids_output:
            self.log("No windows found")
            return
        
        window_ids = [wid.strip() for wid in window_ids_output.split('\n') if wid.strip()]
        if not window_ids:
            self.log("No windows found")
            return
        
        for wid in window_ids:
            name = self.run_xdotool("getwindowname", wid) or "(no name)"
            class_name = self.run_xdotool("getwindowclassname", wid) or "(no class)"
            self.log(f"  Window ID: {wid} | Name: '{name}' | Class: '{class_name}'")
        self.log("")
    
    def move_window_to_top_left(self, window_id: str):
        """Move window to top-left corner (0, 0)."""
        self.log(f"Moving window {window_id} to top-left corner (0, 0)")
        self.run_xdotool("windowmove", window_id, "0", "0")
        time.sleep(0.5)
        self.log("✓ Window moved to top-left corner")

    def _expected_state_screenshot_path(self) -> Path:
        """Return reference screenshot path for current config."""
        project_root = Path(__file__).resolve().parent.parent
        ref_dir = project_root / "test-screenshots"

        api_prefix = "fix" if self.config.api_type == "FIX" else "ibapi"
        mode_suffix = "live" if self.config.trading_mode == "LIVE" else "paper"
        return ref_dir / f"{api_prefix}-{mode_suffix}.png"

    def verify_target_state_before_credentials(self) -> bool:
        """Verify the GUI is in the expected post-click state before typing credentials."""
        expected_path = self._expected_state_screenshot_path()

        if not expected_path.exists():
            self.log(
                "ERROR: No reference screenshot found for this configuration. "
                f"Expected: {expected_path}"
            )
            return False

        screenshotter = ScreenshotHandler(self.config, verbose=self.verbose)
        current_path = os.path.join(self.config.screenshot_dir, "pre_credentials_state.png")
        current = screenshotter.take_screenshot(current_path)
        if not current:
            self.log("ERROR: Failed to capture screenshot for state verification")
            return False

        try:
            result = compare_images_pil(str(expected_path), current, threshold=0.01, max_diff_percentage=1.0)
        except Exception as e:
            self.log(f"ERROR: Failed to compare screenshots: {e}")
            self.log(f"Reference: {expected_path}")
            self.log(f"Current:   {current}")
            return False

        if not result["is_match"]:
            self.log("ERROR: GUI state does not match expected target state after button clicks.")
            self.log(f"Reference: {expected_path}")
            self.log(f"Current:   {current}")
            self.log(
                "Comparison metrics: "
                f"mean_diff={result['mean_diff']:.2f}, "
                f"max_diff={result['max_diff']}, "
                f"diff_percentage={result['diff_percentage']:.2f}%"
            )
            return False

        self.log(
            "✓ Target state verified before typing credentials "
            f"(mean_diff={result['mean_diff']:.2f}, diff_percentage={result['diff_percentage']:.2f}%)"
        )
        return True
    
    def wait_for_pre_credentials_state(self, timeout: int = 30) -> bool:
        """Wait until screenshot matches pre_credentials_state.png reference image."""
        project_root = Path(__file__).resolve().parent.parent
        reference_path = project_root / "test-screenshots" / "pre_credentials_state.png"
        
        if not reference_path.exists():
            self.log(
                f"WARNING: Reference screenshot not found: {reference_path}. "
                "Skipping pre-credentials state check."
            )
            return True  # Don't fail if reference doesn't exist
        
        self.log("Waiting for window to reach pre-credentials state...")
        screenshotter = ScreenshotHandler(self.config, verbose=self.verbose)
        
        elapsed = 0
        while elapsed < timeout:
            current_path = os.path.join(self.config.screenshot_dir, "pre_credentials_state_check.png")
            current = screenshotter.take_screenshot(current_path)
            if not current:
                self.log("ERROR: Failed to capture screenshot for state check")
                time.sleep(1)
                elapsed += 1
                continue
            
            try:
                result = compare_images_pil(str(reference_path), current, threshold=0.01, max_diff_percentage=5.0)
                
                if result["is_match"]:
                    self.log(
                        f"✓ Pre-credentials state reached "
                        f"(mean_diff={result['mean_diff']:.2f}, diff_percentage={result['diff_percentage']:.2f}%)"
                    )
                    return True
                
                # Log progress every 5 seconds
                if elapsed % 5 == 0:
                    self.log(
                        f"Waiting... (mean_diff={result['mean_diff']:.2f}, "
                        f"diff_percentage={result['diff_percentage']:.2f}%)"
                    )
            except Exception as e:
                self.log(f"WARNING: Failed to compare screenshots: {e}")
            
            time.sleep(1)
            elapsed += 1
        
        self.log(f"WARNING: Pre-credentials state not reached after {timeout}s, continuing anyway...")
        return False  # Don't fail, but log warning
    
    def automate(self) -> int:
        """Main automation function."""
        self.config.print_config()
        self.list_all_windows()
        
        window_id = self.find_ibgateway_window()
        if not window_id:
            return 1
        
        self.log(f"Content window ID: {window_id}")
        
        # Wait until screenshot matches pre_credentials_state.png
        self.wait_for_pre_credentials_state()
        
        self.move_window_to_top_left(window_id)
        self.log("Waiting for window to fully render...")
        time.sleep(2)
        
        # Click API Type button
        self.click_api_type_button(window_id)
        
        # Click Trading Mode button
        self.click_trading_mode_button(window_id)
        
        # Before typing credentials, verify we reached the expected target state.
        if self.config.username or self.config.password:
            if not self.verify_target_state_before_credentials():
                self.log("Aborting credential entry due to failed state verification.")
                return 1

        # Type username/password if provided
        self.type_username(window_id)
        self.type_password(window_id)
        
        self.log("")
        self.log("--- Configuration Complete ---")
        self.log(f"API Type: {self.config.api_type}")
        self.log(f"Trading Mode: {self.config.trading_mode}")
        
        return 0
    
    def run_ibgateway(self) -> int:
        """Run IB Gateway with minimal setup (Xvfb + IB Gateway)."""
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        self.log("--- Starting Xvfb ---")
        xvfb_process = subprocess.Popen(
            ["Xvfb", self.config.display, "-screen", "0", f"{self.config.resolution}x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
            env=env
        )
        time.sleep(2)
        
        self.log("--- Starting IB Gateway ---")
        ibgateway_process = subprocess.Popen(
            ["/opt/ibgateway/ibgateway"],
            env=env
        )
        time.sleep(15)
        
        # Keep running
        try:
            ibgateway_process.wait()
        except KeyboardInterrupt:
            xvfb_process.terminate()
            ibgateway_process.terminate()
        
        return 0

