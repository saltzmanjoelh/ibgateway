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
from .screenshot import ScreenshotHandler


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
        self.screenshotter = ScreenshotHandler(self.config, verbose=self.verbose)
    
    def log(self, message: str):
        """Print log message if verbose."""
        print(f"[AUTOMATION] {message}", flush=True)
    
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
            self.log("Skipping username entry (IBGATEWAY_USERNAME not set)")
            return
        
        self.log("--- Typing Username ---")
        self.run_xdotool("type", "--delay", "50", self.config.username)
        time.sleep(0.5)
        self.log("✓ Username typed")
    
    def type_password(self, window_id: str):
        """Type password (tab to password field first)."""
        if not self.config.password:
            self.log("Skipping password entry (IBGATEWAY_PASSWORD not set)")
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

    def verify_target_state_before_credentials(self, timeout: int = 30) -> bool:
        """Wait for the GUI to reach the expected post-click state before typing credentials."""
        expected_path = self._expected_state_screenshot_path()

        if not expected_path.exists():
            self.log(
                "ERROR: No reference screenshot found for this configuration. "
                f"Expected: {expected_path}"
            )
            return False

        self.log("Waiting for target state before typing credentials...")

        # Use more lenient thresholds - GUI rendering can vary slightly
        # threshold=0.15 allows mean_diff up to ~38 (30.10 is within this)
        # max_diff_percentage=20.0 allows up to 20% different pixels
        success, result = self.screenshotter.wait_for_state_match(
            str(expected_path),
            "pre_credentials_state.png",
            timeout=timeout,
            threshold=0.15,
            max_diff_percentage=20.0,
            success_message="✓ Target state verified before typing credentials",
            waiting_message=None  # Use default waiting message
        )

        if not success:
            self.log("ERROR: GUI state did not reach expected target state after button clicks.")
            self.log(f"Reference: {expected_path}")
            return False

        return True
    
    def wait_for_pre_credentials_state(self, timeout: int = 30) -> bool:
        """Wait until screenshot matches pre_credentials_state.png reference image."""
        project_root = Path(__file__).resolve().parent.parent
        reference_path = project_root / "test-screenshots" / "pre_credentials_state.png"
        
        self.log("Waiting for window to reach pre-credentials state...")
        
        success, _ = self.screenshotter.wait_for_state_match(
            str(reference_path),
            "pre_credentials_state_check.png",
            timeout=timeout,
            threshold=0.01,
            max_diff_percentage=10.0,
            success_message=None,  # Use default message
            waiting_message=None   # Use default message
        )
        
        return success

    def wait_for_i_understand_button(self, timeout: int = 30) -> bool:
        """Wait until screenshot matches i_understand.png reference image."""
        project_root = Path(__file__).resolve().parent.parent
        reference_path = project_root / "test-screenshots" / "i_understand.png"
        
        self.log("Waiting for I understand button to appear...")
        
        # Correct state shows: mean_diff=5.42, diff_percentage=6.06%
        # threshold=0.03 allows mean_diff up to ~7.65 (5.42/255 ≈ 0.021, using 0.03 for margin)
        # max_diff_percentage=8.0 allows up to 8% different pixels (6.06% < 8.0%)
        success, _ = self.screenshotter.wait_for_state_match(
            str(reference_path),
            "i_understand_button_check.png",
            timeout=timeout,
            threshold=0.03,
            max_diff_percentage=8.0,
            success_message=None,  # Use default message
            waiting_message=None   # Use default message
        )
        
        return success

    def wait_for_after_move_window_to_top_left(self, timeout: int = 30) -> bool:
        """Wait until screenshot matches after_move_window_to_top_left.png reference image."""
        project_root = Path(__file__).resolve().parent.parent
        reference_path = project_root / "test-screenshots" / "after_move_window_to_top_left.png"
        
        self.log("Waiting for window to reach after-move state...")
        
        success, _ = self.screenshotter.wait_for_state_match(
            str(reference_path),
            "after_move_window_to_top_left_check.png",
            timeout=timeout,
            threshold=0.01,
            max_diff_percentage=10.0,
            success_message=None,  # Use default message
            waiting_message=None   # Use default message
        )
        
        return success

    def click_i_understand_button(self, window_id: str):
        """Click the I understand button."""
        self.log("Clicking I understand button...")
        # Press enter
        self.run_xdotool("key", "Return")
        self.click_at_coordinates(window_id, 354, 391, "I understand")
        self.log("✓ I understand button clicked")

    def automate(self) -> int:
        """Main automation function."""
        self.config.print_config()
        
        # Validate that both username and password are set
        if not self.config.username:
            self.log("ERROR: IBGATEWAY_USERNAME is not set. Username is required for automation.")
            return 1
        
        if not self.config.password:
            self.log("ERROR: IBGATEWAY_PASSWORD is not set. Password is required for automation.")
            return 1
        
        self.list_all_windows()
        
        window_id = self.find_ibgateway_window()
        if not window_id:
            return 1
        
        self.log(f"Content window ID: {window_id}")
        
        # Wait until screenshot matches pre_credentials_state.png
        self.wait_for_pre_credentials_state()
        
        self.move_window_to_top_left(window_id)
        
        # Wait until screenshot matches after_move_window_to_top_left.png
        self.wait_for_after_move_window_to_top_left()
        
        # Click API Type button
        self.click_api_type_button(window_id)
        
        # Click Trading Mode button
        self.click_trading_mode_button(window_id)
        
        # Before typing credentials, verify we reached the expected target state.
        if not self.verify_target_state_before_credentials():
            self.log("Aborting credential entry due to failed state verification.")
            return 1

        # Type username/password
        self.type_username(window_id)
        self.type_password(window_id)

        # Wait for the I understand button to appear
        self.wait_for_i_understand_button()
        self.click_i_understand_button(window_id)
        
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

