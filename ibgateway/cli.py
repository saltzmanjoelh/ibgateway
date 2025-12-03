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
        
        # test-automation subcommand
        test_automation_parser = subparsers.add_parser("test-automation", help="Test automation")
        test_automation_parser.add_argument("--container-name", default="ibgateway-test", help="Docker container name")
        test_automation_parser.add_argument("--api-type", choices=["FIX", "IB_API"], help="API type to test")
        test_automation_parser.add_argument("--trading-mode", choices=["LIVE", "PAPER"], help="Trading mode to test")
        test_automation_parser.add_argument("--ci", action="store_true", help="CI mode (simplified output)")
        
        # test-screenshot-service subcommand
        test_screenshot_parser = subparsers.add_parser("test-screenshot-service", help="Test screenshot service")
        test_screenshot_parser.add_argument("--container-name", default="ibgateway-test", help="Docker container name")
        test_screenshot_parser.add_argument("--port", type=int, default=8080, help="Screenshot service port")
        
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
        
        elif parsed_args.command == "test-automation":
            return self._test_automation(
                parsed_args.container_name,
                parsed_args.api_type,
                parsed_args.trading_mode,
                parsed_args.ci,
                verbose
            )
        
        elif parsed_args.command == "test-screenshot-service":
            return self._test_screenshot_service(
                parsed_args.container_name,
                parsed_args.port,
                verbose
            )
        
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
    
    def _test_automation(self, container_name: str, api_type: Optional[str], trading_mode: Optional[str], ci_mode: bool, verbose: bool) -> int:
        """Test automation with Docker container."""
        import urllib.request
        import urllib.error
        
        # Determine test configurations
        configs = []
        if api_type and trading_mode:
            configs = [(api_type, trading_mode)]
        else:
            configs = [("IB_API", "PAPER"), ("FIX", "LIVE")]
        
        screenshot_dir = "/tmp/test-screenshots" if ci_mode else "/tmp/ibgateway-automation-tests"
        os.makedirs(screenshot_dir, exist_ok=True)
        
        passed = 0
        failed = 0
        
        for api_type_val, trading_mode_val in configs:
            test_name = f"{api_type_val}_{trading_mode_val}"
            container_name_test = f"{container_name}-{test_name.lower().replace('_', '-')}"
            
            print(f"\n=== Testing: {test_name} (API: {api_type_val}, Mode: {trading_mode_val}) ===")
            
            # Cleanup previous container
            self._docker_stop_remove(container_name_test)
            
            # Start container
            print("Starting container...")
            docker_cmd = [
                "docker", "run", "-d",
                "--name", container_name_test,
                "--platform", "linux/amd64",
                "-p", "5900:5900",
                "-p", "8080:8080",
                "-e", f"IB_API_TYPE={api_type_val}",
                "-e", f"IB_TRADING_MODE={trading_mode_val}",
                "ibgateway-test:latest"
            ]
            
            try:
                subprocess.run(docker_cmd, check=True)
            except subprocess.CalledProcessError:
                print("ERROR: Failed to start container")
                failed += 1
                continue
            
            # Wait for services
            print("Waiting for services to start...")
            sleep_time = 15 if ci_mode else 20
            time.sleep(sleep_time)
            
            # Check container is running
            if not self._docker_is_running(container_name_test):
                print("ERROR: Container is not running")
                self._docker_logs(container_name_test)
                failed += 1
                continue
            
            # Wait for screenshot service
            print("Waiting for screenshot service...")
            screenshot_port = 8080
            if not self._wait_for_service(f"http://localhost:{screenshot_port}/", timeout=30):
                print("ERROR: Screenshot service not available")
                self._docker_logs(container_name_test)
                failed += 1
                continue
            
            # Wait for IB Gateway window
            print("Waiting for IB Gateway window...")
            window_id = self._wait_for_ibgateway_window(container_name_test, timeout=90)
            
            # Wait for automation to complete
            print("Waiting for automation to complete...")
            time.sleep(15)
            
            # Take verification screenshot
            print("Taking verification screenshot...")
            screenshot_path = self._take_screenshot_via_api(screenshot_port, screenshot_dir, test_name)
            
            if not screenshot_path:
                print("WARNING: Failed to take screenshot")
            
            # Check logs for automation
            print("Checking automation logs...")
            logs = self._docker_logs(container_name_test)
            automation_found = False
            
            if api_type_val.lower() in logs.lower() and trading_mode_val.lower() in logs.lower():
                automation_found = True
            if "configuration complete" in logs.lower():
                automation_found = True
            
            if automation_found:
                print(f"✓ Test passed: {test_name}")
                passed += 1
            else:
                print(f"✗ Test failed: {test_name}")
                failed += 1
            
            # Cleanup
            self._docker_stop_remove(container_name_test)
        
        # Summary
        print("\n==========================================")
        print("Test Results")
        print("==========================================")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"\nScreenshots saved in: {screenshot_dir}")
        
        return 0 if failed == 0 else 1
    
    def _test_screenshot_service(self, container_name: str, port: int, verbose: bool) -> int:
        """Test screenshot service."""
        import urllib.request
        import urllib.error
        
        print("=== Testing Screenshot Service ===")
        print(f"Container: {container_name}")
        print(f"Port: {port}")
        print()
        
        # Check if container is running
        if not self._docker_is_running(container_name):
            print(f"ERROR: Container '{container_name}' is not running")
            print(f"Start it with:")
            print(f"  docker run -d --name {container_name} --platform linux/amd64 -p 5900:5900 -p {port}:{port} ibgateway-test:latest")
            return 1
        
        print("✓ Container is running")
        print()
        
        # Wait for service
        print("Waiting for screenshot service to be ready...")
        if not self._wait_for_service(f"http://localhost:{port}/", timeout=30):
            print("ERROR: Screenshot service failed to start")
            self._docker_logs(container_name)
            return 1
        
        print("✓ Screenshot service is accessible")
        print()
        
        # Test endpoints
        base_url = f"http://localhost:{port}"
        
        # Test root endpoint
        print("Testing GET /")
        if not self._test_endpoint(f"{base_url}/"):
            return 1
        print("✓ Root endpoint works")
        print()
        
        # Test taking screenshot
        print("Testing GET /screenshot")
        response = self._get_json(f"{base_url}/screenshot")
        if not response or not response.get("success"):
            print("ERROR: Screenshot endpoint failed")
            return 1
        
        screenshot_url = response.get("url")
        screenshot_filename = response.get("filename")
        print(f"✓ Screenshot taken: {screenshot_filename}")
        print(f"  URL: {response.get('full_url')}")
        print()
        
        # Test viewing screenshot
        print(f"Testing GET {screenshot_url}")
        screenshot_data = self._get_data(f"{base_url}{screenshot_url}")
        if not screenshot_data:
            print("ERROR: Failed to download screenshot")
            return 1
        
        # Save to temp file and verify
        temp_path = "/tmp/test-screenshot.png"
        with open(temp_path, "wb") as f:
            f.write(screenshot_data)
        
        # Check if it's a valid PNG (basic check)
        if screenshot_data[:8] != b'\x89PNG\r\n\x1a\n':
            print("ERROR: Screenshot is not a valid PNG")
            return 1
        
        print("✓ Screenshot image downloaded and is valid PNG")
        print(f"  Saved to: {temp_path}")
        print()
        
        # Test listing screenshots
        print("Testing GET /screenshots")
        screenshots = self._get_json(f"{base_url}/screenshots")
        if not screenshots or not screenshots.get("success"):
            print("ERROR: Screenshot list endpoint failed")
            return 1
        
        count = screenshots.get("count", 0)
        print(f"✓ Screenshot list works (found {count} screenshots)")
        print()
        
        # Test latest screenshot endpoint
        print("Testing GET /screenshot/latest")
        latest = self._get_json(f"{base_url}/screenshot/latest")
        if not latest or not latest.get("success"):
            print("ERROR: Latest screenshot endpoint failed")
            return 1
        
        print("✓ Latest screenshot endpoint works")
        print(f"  Latest: {latest.get('filename')}")
        print(f"  URL: {latest.get('full_url')}")
        print()
        
        # Verify screenshot tools
        print("Verifying screenshot tools are installed...")
        if not self._docker_exec(container_name, ["which", "scrot"]):
            print("ERROR: scrot not found")
            return 1
        if not self._docker_exec(container_name, ["which", "import"]):
            print("ERROR: import (imagemagick) not found")
            return 1
        
        print("✓ Screenshot tools (scrot, imagemagick) are installed")
        print()
        
        # Test screenshot CLI directly
        print("Testing screenshot CLI directly...")
        if not self._docker_exec(container_name, ["python3", "-m", "ibgateway.cli", "screenshot", "--output", "/tmp/test-direct.png"]):
            print("ERROR: Screenshot CLI failed")
            return 1
        
        if not self._docker_exec(container_name, ["test", "-f", "/tmp/test-direct.png"]):
            print("ERROR: Screenshot file not created")
            return 1
        
        print("✓ Screenshot CLI works")
        print()
        
        print("=== All tests passed! ===")
        return 0
    
    # Helper methods for Docker operations
    def _docker_is_running(self, container_name: str) -> bool:
        """Check if Docker container is running."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True
            )
            return container_name in result.stdout
        except Exception:
            return False
    
    def _docker_stop_remove(self, container_name: str):
        """Stop and remove Docker container."""
        subprocess.run(["docker", "stop", container_name], capture_output=True)
        subprocess.run(["docker", "rm", container_name], capture_output=True)
    
    def _docker_logs(self, container_name: str) -> str:
        """Get Docker container logs."""
        try:
            result = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception:
            return ""
    
    def _docker_exec(self, container_name: str, cmd: List[str]) -> bool:
        """Execute command in Docker container."""
        try:
            result = subprocess.run(
                ["docker", "exec", container_name] + cmd,
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _wait_for_service(self, url: str, timeout: int = 30) -> bool:
        """Wait for HTTP service to be available."""
        import urllib.request
        import urllib.error
        
        for i in range(timeout):
            try:
                urllib.request.urlopen(url, timeout=2)
                return True
            except Exception:
                if i < timeout - 1:
                    time.sleep(1)
        return False
    
    def _wait_for_ibgateway_window(self, container_name: str, timeout: int = 90) -> Optional[str]:
        """Wait for IB Gateway window in Docker container."""
        for i in range(timeout):
            # Try multiple search methods
            window_id = self._docker_exec_get_output(
                container_name,
                ["xdotool", "search", "--class", "install4j-ibgateway-GWClient"],
                env={"DISPLAY": ":99"}
            )
            if not window_id:
                window_id = self._docker_exec_get_output(
                    container_name,
                    ["xdotool", "search", "--name", "IBKR Gateway"],
                    env={"DISPLAY": ":99"}
                )
            if not window_id:
                window_id = self._docker_exec_get_output(
                    container_name,
                    ["xdotool", "search", "--all", "--name", "IB"],
                    env={"DISPLAY": ":99"}
                )
            
            if window_id:
                print(f"✓ IB Gateway window found! Window ID: {window_id}")
                return window_id.strip().split()[0] if window_id else None
            
            if i % 10 == 0 and i > 0:
                print(f"  Attempt {i}/{timeout}: Window not found yet...")
            
            time.sleep(1)
        
        print(f"WARNING: IB Gateway window not found after {timeout}s")
        return None
    
    def _docker_exec_get_output(self, container_name: str, cmd: List[str], env: Optional[Dict] = None) -> Optional[str]:
        """Execute command in Docker container and get output."""
        try:
            docker_cmd = ["docker", "exec"]
            if env:
                for k, v in env.items():
                    docker_cmd.extend(["-e", f"{k}={v}"])
            docker_cmd.extend([container_name] + cmd)
            
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None
    
    def _take_screenshot_via_api(self, port: int, output_dir: str, label: str) -> Optional[str]:
        """Take screenshot via API and save to output directory."""
        import urllib.request
        import json
        
        try:
            response = urllib.request.urlopen(f"http://localhost:{port}/screenshot", timeout=10)
            data = json.loads(response.read().decode())
            
            if data.get("success"):
                screenshot_url = data.get("url")
                filename = data.get("filename")
                
                # Download screenshot
                screenshot_response = urllib.request.urlopen(f"http://localhost:{port}{screenshot_url}", timeout=10)
                output_path = os.path.join(output_dir, f"{label}-{filename}")
                
                with open(output_path, "wb") as f:
                    f.write(screenshot_response.read())
                
                return output_path
        except Exception as e:
            print(f"ERROR: Failed to take screenshot via API: {e}")
            return None
    
    def _test_endpoint(self, url: str) -> bool:
        """Test HTTP endpoint."""
        import urllib.request
        
        try:
            urllib.request.urlopen(url, timeout=5)
            return True
        except Exception:
            return False
    
    def _get_json(self, url: str) -> Optional[Dict]:
        """Get JSON from URL."""
        import urllib.request
        import json
        
        try:
            response = urllib.request.urlopen(url, timeout=10)
            return json.loads(response.read().decode())
        except Exception:
            return None
    
    def _get_data(self, url: str) -> Optional[bytes]:
        """Get binary data from URL."""
        import urllib.request
        
        try:
            response = urllib.request.urlopen(url, timeout=10)
            return response.read()
        except Exception:
            return None


def main():
    """Main entry point."""
    cli = IBGatewayCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()

