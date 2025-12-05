"""
Main CLI interface for IB Gateway operations.
"""

import argparse
import os
import subprocess
import sys
import time
from typing import Optional, Dict, List
from http.server import HTTPServer

try:
    from PIL import Image, ImageChops, ImageStat
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from .config import Config
from .automation import AutomationHandler
from .screenshot import ScreenshotHandler
from .screenshot_server import ScreenshotServer
from .port_forwarder import PortForwarder


class IBGatewayCLI:
    """Main CLI class for IB Gateway operations."""
    
    def __init__(self):
        self.config = Config()
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser with subcommands."""
        parser = argparse.ArgumentParser(
            description="IB Gateway CLI Tool - Unified interface for automation, screenshots, and testing"
        )
        parser.add_argument(
            "-v", "--verbose",
            action="store_true",
            help="Enable verbose output"
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
        
        # automate subcommand
        automate_parser = subparsers.add_parser("automate", help="Automate IB Gateway GUI configuration")
        automate_parser.add_argument("--username", help="IB Gateway username (overrides env var)")
        automate_parser.add_argument("--password", help="IB Gateway password (overrides env var)")
        automate_parser.add_argument("--api-type", choices=["FIX", "IB_API"], help="API type (overrides env var)")
        automate_parser.add_argument("--trading-mode", choices=["LIVE", "PAPER"], help="Trading mode (overrides env var)")
        
        # screenshot subcommand
        screenshot_parser = subparsers.add_parser("screenshot", help="Take a screenshot")
        screenshot_parser.add_argument("--output", "-o", help="Output file path")
        
        # screenshot-server subcommand
        server_parser = subparsers.add_parser("screenshot-server", help="Start HTTP screenshot server")
        server_parser.add_argument("--port", "-p", type=int, help="Port to listen on (default: 8080)")
        
        # compare-screenshots subcommand
        compare_parser = subparsers.add_parser("compare-screenshots", help="Compare two screenshots")
        compare_parser.add_argument("image1", help="First image path")
        compare_parser.add_argument("image2", help="Second image path")
        compare_parser.add_argument("--threshold", type=float, default=0.01, help="Similarity threshold")
        
        # install subcommand
        install_parser = subparsers.add_parser("install", help="Install IB Gateway")
        
        # run subcommand
        run_parser = subparsers.add_parser("run", help="Run IB Gateway")
        
        # port-forward subcommand
        port_forward_parser = subparsers.add_parser("port-forward", help="Start port forwarding")
        
        return parser
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """Run the CLI with given arguments."""
        parsed_args = self.parser.parse_args(args)
        
        if not parsed_args.command:
            self.parser.print_help()
            return 1
        
        verbose = parsed_args.verbose
        
        # Update config from command line args if provided
        if hasattr(parsed_args, "username") and parsed_args.username:
            self.config.username = parsed_args.username
        if hasattr(parsed_args, "password") and parsed_args.password:
            self.config.password = parsed_args.password
        if hasattr(parsed_args, "api_type") and parsed_args.api_type:
            self.config.api_type = parsed_args.api_type.upper()
        if hasattr(parsed_args, "trading_mode") and parsed_args.trading_mode:
            self.config.trading_mode = parsed_args.trading_mode.upper()
        if hasattr(parsed_args, "port") and parsed_args.port:
            self.config.screenshot_port = parsed_args.port
        
        # Route to appropriate handler
        if parsed_args.command == "automate":
            handler = AutomationHandler(self.config, verbose)
            return handler.automate()
        
        elif parsed_args.command == "screenshot":
            handler = ScreenshotHandler(self.config, verbose)
            output_path = getattr(parsed_args, "output", None)
            result = handler.take_screenshot(output_path)
            return 0 if result else 1
        
        elif parsed_args.command == "screenshot-server":
            return self._run_screenshot_server(parsed_args.port or self.config.screenshot_port, verbose)
        
        elif parsed_args.command == "compare-screenshots":
            return self._compare_screenshots(
                parsed_args.image1,
                parsed_args.image2,
                parsed_args.threshold
            )
        
        elif parsed_args.command == "install":
            return self._install_ibgateway(verbose)
        
        elif parsed_args.command == "run":
            return self._run_ibgateway(verbose)
        
        elif parsed_args.command == "port-forward":
            handler = PortForwarder(self.config, verbose)
            return handler.start_forwarding()
        
        return 1
    
    def _run_screenshot_server(self, port: int, verbose: bool) -> int:
        """Run the screenshot HTTP server."""
        ScreenshotServer.screenshot_handler = ScreenshotHandler(self.config, verbose)
        ScreenshotServer.screenshot_dir = self.config.screenshot_dir
        
        server = HTTPServer(("0.0.0.0", port), ScreenshotServer)
        print(f"Screenshot server starting on port {port}")
        print(f"Screenshots directory: {self.config.screenshot_dir}")
        print(f"Access the service at: http://localhost:{port}/")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nScreenshot server shutting down...")
            server.shutdown()
        
        return 0
    
    def _compare_screenshots(self, img1_path: str, img2_path: str, threshold: float) -> int:
        """Compare two screenshots."""
        if not os.path.exists(img1_path):
            print(f"ERROR: Image not found: {img1_path}")
            return 1
        
        if not os.path.exists(img2_path):
            print(f"ERROR: Image not found: {img2_path}")
            return 1
        
        print(f"Comparing images:")
        print(f"  Image 1: {img1_path}")
        print(f"  Image 2: {img2_path}")
        print()
        
        # Simple file size comparison
        size1 = os.path.getsize(img1_path)
        size2 = os.path.getsize(img2_path)
        size_diff = abs(size1 - size2)
        size_diff_percent = abs(size1 - size2) / max(size1, size2) * 100 if max(size1, size2) > 0 else 0
        
        print("File size comparison:")
        print(f"  Image 1 size: {size1} bytes")
        print(f"  Image 2 size: {size2} bytes")
        print(f"  Size difference: {size_diff} bytes ({size_diff_percent:.2f}%)")
        print()
        
        # PIL comparison if available
        if HAS_PIL:
            result = self._compare_images_pil(img1_path, img2_path, threshold)
            if result:
                print("Image content comparison:")
                print(f"  Mean pixel difference: {result['mean_diff']:.2f}")
                print(f"  Max pixel difference: {result['max_diff']}")
                print(f"  Different pixels: {result['diff_percentage']:.2f}%")
                print()
                
                if result['has_changes']:
                    print("✓ Images are different (changes detected)")
                    if result['is_similar']:
                        print("  Note: Changes are relatively small")
                    else:
                        print("  Note: Significant changes detected")
                    return 0
                else:
                    print("⚠ Images are very similar (minimal changes)")
                    return 1
        else:
            print("WARNING: PIL/Pillow not available. Install for detailed comparison:")
            print("  pip install Pillow")
            print()
            print("Using file size comparison only.")
            if size_diff_percent > 5:
                print("✓ Files are different (size difference > 5%)")
                return 0
            else:
                print("⚠ Files are similar (size difference < 5%)")
                return 1
        
        return 0
    
    def _compare_images_pil(self, img1_path: str, img2_path: str, threshold: float) -> Optional[Dict]:
        """Compare images using PIL."""
        if not HAS_PIL:
            return None
        
        try:
            img1 = Image.open(img1_path)
            img2 = Image.open(img2_path)
            
            if img1.size != img2.size:
                print(f"WARNING: Images have different sizes: {img1.size} vs {img2.size}")
                return None
            
            if img1.mode != 'RGB':
                img1 = img1.convert('RGB')
            if img2.mode != 'RGB':
                img2 = img2.convert('RGB')
            
            diff = ImageChops.difference(img1, img2)
            stat = ImageStat.Stat(diff)
            
            mean_diff = sum(stat.mean) / len(stat.mean)
            max_diff = max(stat.extrema[0][1], stat.extrema[1][1], stat.extrema[2][1])
            
            if HAS_NUMPY:
                diff_array = np.array(diff)
                different_pixels = np.sum(np.any(diff_array > 0, axis=2))
                total_pixels = diff_array.shape[0] * diff_array.shape[1]
                diff_percentage = (different_pixels / total_pixels) * 100
            else:
                diff_percentage = 0
            
            return {
                'mean_diff': mean_diff,
                'max_diff': max_diff,
                'diff_percentage': diff_percentage,
                'is_similar': mean_diff < (255 * threshold),
                'has_changes': diff_percentage > 1.0
            }
        except Exception as e:
            print(f"ERROR comparing images: {e}")
            return None
    
    def _install_ibgateway(self, verbose: bool) -> int:
        """Install IB Gateway."""
        print("=== Starting IB Gateway installation ===")
        
        installer_url = "https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh"
        installer_path = "/tmp/install-ibgateway.sh"
        log_path = "/tmp/install-ibgateway.log"
        
        try:
            # Download installer
            print(f"Downloading installer from {installer_url}...")
            subprocess.run(
                ["curl", installer_url, "-o", installer_path],
                check=True
            )
            
            # Make executable
            os.chmod(installer_path, 0o755)
            
            # Run installer
            print("Running installer...")
            result = subprocess.run(
                [installer_path, "-q", "-f", log_path],
                check=True
            )
            
            print("=== IB Gateway installation completed ===")
            print(f"Installation log available at {log_path}")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Installation failed: {e}")
            return 1
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    
    def _run_ibgateway(self, verbose: bool) -> int:
        """Run IB Gateway."""
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        
        print("=== Starting Xvfb ===")
        xvfb_process = subprocess.Popen(
            ["Xvfb", self.config.display, "-screen", "0", f"{self.config.resolution}x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
            env=env
        )
        time.sleep(2)
        
        print("=== Starting IB Gateway ===")
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


def main():
    """Main entry point."""
    cli = IBGatewayCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()

