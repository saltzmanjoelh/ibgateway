"""
IB Gateway GUI automation handler using xdotool.
"""

import os
import subprocess
import time
from typing import Optional

from .config import Config


class AutomationHandler:
    """Handles IB Gateway GUI automation using xdotool."""
    
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        
        # Button coordinates (relative to content window)
        self.FIX_BUTTON_X = 500
        self.FIX_BUTTON_Y = 300
        self.IB_API_BUTTON_X = 700
        self.IB_API_BUTTON_Y = 300
        self.LIVE_TRADING_BUTTON_X = 500
        self.LIVE_TRADING_BUTTON_Y = 340
        self.PAPER_TRADING_BUTTON_X = 700
        self.PAPER_TRADING_BUTTON_Y = 300
    
    def log(self, message: str):
        """Print log message if verbose."""
        if self.verbose:
            print(f"[AUTOMATION] {message}")
        else:
            print(message)
    
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
            window_id = self.run_xdotool("search", "--class", "install4j-ibgateway-GWClient")
            if not window_id:
                window_id = self.run_xdotool("search", "--name", "IBKR Gateway")
            if not window_id:
                window_id = self.run_xdotool("search", "--all", "--name", "IB")
            
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
        self.run_xdotool("mousemove", "--window", window_id, str(x), str(y))
        time.sleep(0.3)
        
        # Click
        self.run_xdotool("click", "--window", window_id, "1")
        time.sleep(0.5)
        
        self.log(f"✓ Clicked {button_name}")
    
    def click_api_type_button(self, window_id: str):
        """Click the API type button (FIX or IB_API)."""
        self.log(f"=== Configuring API Type: {self.config.api_type} ===")
        
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
        self.log(f"=== Configuring Trading Mode: {self.config.trading_mode} ===")
        
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
        
        self.log("=== Typing Username ===")
        self.run_xdotool("type", "--window", window_id, "--delay", "50", self.config.username)
        time.sleep(0.5)
        self.log("✓ Username typed")
    
    def type_password(self, window_id: str):
        """Type password (tab to password field first)."""
        if not self.config.password:
            self.log("Skipping password entry (IB_PASSWORD not set)")
            return
        
        self.log("=== Typing Password ===")
        self.run_xdotool("key", "--window", window_id, "Tab")
        time.sleep(0.3)
        self.run_xdotool("type", "--window", window_id, "--delay", "50", self.config.password)
        time.sleep(0.5)
        self.log("✓ Password typed")
    
    def automate(self) -> int:
        """Main automation function."""
        self.config.print_config()
        
        window_id = self.find_ibgateway_window()
        if not window_id:
            return 1
        
        self.log(f"Content window ID: {window_id}")
        self.log("Waiting for window to fully render...")
        time.sleep(2)
        
        # Click API Type button
        self.click_api_type_button(window_id)
        
        # Click Trading Mode button
        self.click_trading_mode_button(window_id)
        
        # Type username if provided
        self.type_username(window_id)
        
        # Type password if provided
        self.type_password(window_id)
        
        self.log("")
        self.log("=== Configuration Complete ===")
        self.log(f"API Type: {self.config.api_type}")
        self.log(f"Trading Mode: {self.config.trading_mode}")
        
        return 0

