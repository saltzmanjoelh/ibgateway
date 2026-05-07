"""
Main CLI interface for IB Gateway operations.
"""

import argparse
import os
import subprocess
import sys
import time
from typing import Optional, Dict, List

from .config import Config
from .automate_ibgateway import AutomationHandler
from .screenshot import ScreenshotHandler
from .screenshot_server import ScreenshotServer
from .port_forwarder import PortForwarder
from .orchestrator import ServiceOrchestrator


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

        # automate-ibgateway subcommand
        automate_parser = subparsers.add_parser("automate-ibgateway", help="Automate IB Gateway GUI configuration")
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

        # mcp-server subcommand
        mcp_parser = subparsers.add_parser("mcp-server", help="Start the MCP server (Streamable HTTP)")
        mcp_parser.add_argument("--port", type=int, help="Port to listen on (default: 8090)")
        mcp_parser.add_argument("--host", help="Host to bind (default: 127.0.0.1)")

        # compare-screenshots subcommand
        compare_parser = subparsers.add_parser("compare-screenshots", help="Compare two screenshots")
        compare_parser.add_argument("image1", help="First image path")
        compare_parser.add_argument("image2", help="Second image path")
        compare_parser.add_argument("--threshold", type=float, default=0.01, help="Similarity threshold")

        # test-screenshot subcommand
        test_parser = subparsers.add_parser("test-screenshot", help="Take a screenshot and compare with test image")
        test_parser.add_argument("test_image", help="Path to test/reference screenshot")
        test_parser.add_argument("--threshold", type=float, default=0.01, help="Similarity threshold")

        # start-services subcommand
        start_parser = subparsers.add_parser("start-services", help="Start all IB Gateway services (orchestrator)")
        start_parser.add_argument("--username", help="IB Gateway username (overrides env var)")
        start_parser.add_argument("--password", help="IB Gateway password (overrides env var)")
        start_parser.add_argument("--api-type", choices=["FIX", "IB_API"], help="API type (overrides env var)")
        start_parser.add_argument("--trading-mode", choices=["LIVE", "PAPER"], help="Trading mode (overrides env var)")
        start_parser.add_argument("--no-automation", action="store_true", help="Skip automation (start services only)")
        start_parser.add_argument("--no-mcp", action="store_true", help="Skip starting the MCP server")

        # install-ibgateway subcommand
        install_parser = subparsers.add_parser("install-ibgateway", help="Install IB Gateway")
        install_parser.add_argument(
            "--latest",
            action="store_true",
            help="Use latest version instead of stable (default: stable)"
        )

        # start-ibgateway subcommand
        start_ibgateway_parser = subparsers.add_parser("start-ibgateway", help="Start IB Gateway (minimal setup)")

        # port-forward subcommand
        port_forward_parser = subparsers.add_parser("port-forward", help="Start port forwarding")

        return parser

    def run_command(self, args: Optional[List[str]] = None) -> int:
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
        if hasattr(parsed_args, "port") and parsed_args.port and parsed_args.command == "screenshot-server":
            self.config.screenshot_port = parsed_args.port

        # Route to appropriate handler
        if parsed_args.command == "start-services":
            # Update config from command line args if provided
            if hasattr(parsed_args, "username") and parsed_args.username:
                self.config.username = parsed_args.username
            if hasattr(parsed_args, "password") and parsed_args.password:
                self.config.password = parsed_args.password
            if hasattr(parsed_args, "api_type") and parsed_args.api_type:
                self.config.api_type = parsed_args.api_type.upper()
            if hasattr(parsed_args, "trading_mode") and parsed_args.trading_mode:
                self.config.trading_mode = parsed_args.trading_mode.upper()
            no_automation = getattr(parsed_args, "no_automation", False)
            no_mcp = getattr(parsed_args, "no_mcp", False)
            orchestrator = ServiceOrchestrator(self.config, verbose)
            return orchestrator.start(skip_automation=no_automation, skip_mcp=no_mcp)

        elif parsed_args.command == "automate-ibgateway":
            handler = AutomationHandler(self.config, verbose)
            return handler.automate()

        elif parsed_args.command == "screenshot":
            handler = ScreenshotHandler(self.config, verbose)
            output_path = getattr(parsed_args, "output", None)
            result = handler.take_screenshot(output_path)
            return 0 if result else 1

        elif parsed_args.command == "screenshot-server":
            port = parsed_args.port or self.config.screenshot_port
            return ScreenshotServer.run_server(self.config, port, verbose)

        elif parsed_args.command == "mcp-server":
            from .mcp_server import run as run_mcp
            if getattr(parsed_args, "port", None):
                self.config.mcp_port = parsed_args.port
                os.environ["MCP_PORT"] = str(parsed_args.port)
            if getattr(parsed_args, "host", None):
                self.config.mcp_host = parsed_args.host
                os.environ["MCP_HOST"] = parsed_args.host
            return run_mcp(self.config)

        elif parsed_args.command == "compare-screenshots":
            handler = ScreenshotHandler(self.config, verbose)
            return handler.compare_screenshots(
                parsed_args.image1,
                parsed_args.image2,
                parsed_args.threshold
            )

        elif parsed_args.command == "test-screenshot":
            handler = ScreenshotHandler(self.config, verbose)
            return handler.test_screenshot(
                parsed_args.test_image,
                parsed_args.threshold
            )

        elif parsed_args.command == "install-ibgateway":
            use_latest = getattr(parsed_args, "latest", False)
            return self._install_ibgateway(verbose, use_latest)

        elif parsed_args.command == "start-ibgateway":
            handler = AutomationHandler(self.config, verbose)
            return handler.run_ibgateway()

        elif parsed_args.command == "port-forward":
            handler = PortForwarder(self.config, verbose)
            return handler.start_forwarding()

        return 1

    def _install_ibgateway(self, verbose: bool, use_latest: bool = False) -> int:
        """Install IB Gateway.

        Args:
            verbose: Enable verbose output
            use_latest: If True, use latest version; if False, use stable (default)
        """
        version = "latest" if use_latest else "stable"
        print(f"--- Starting IB Gateway installation ({version} version) ---")

        installer_url = f"https://download2.interactivebrokers.com/installers/ibgateway/{version}-standalone/ibgateway-{version}-standalone-linux-x64.sh"
        installer_path = "/tmp/install-ibgateway.sh"
        log_path = "/tmp/install-ibgateway.log"

        try:
            # Download installer. IBKR's mirror occasionally drops the
            # connection mid-body (curl exit 56) which used to fail the
            # whole image build. --retry-all-errors + bounded backoff lets
            # the build self-heal across those flakes; -fL fails fast on
            # HTTP errors and follows redirects; --connect-timeout caps
            # TLS-handshake hangs.
            print(f"Downloading installer from {installer_url}...")
            subprocess.run(
                [
                    "curl", "-fL", "-o", installer_path,
                    "--retry", "5",
                    "--retry-delay", "5",
                    "--retry-all-errors",
                    "--retry-max-time", "300",
                    "--connect-timeout", "30",
                    "--max-time", "600",
                    installer_url,
                ],
                check=True,
            )

            # Make executable
            os.chmod(installer_path, 0o755)

            # Run installer
            print("Running installer...")
            result = subprocess.run(
                [installer_path, "-q", "-f", log_path],
                check=True
            )

            # Verify IB Gateway installation
            ibgateway_exec = self._find_ibgateway_executable()
            if not ibgateway_exec:
                print("ERROR: IB Gateway executable not found in expected location")
                print("Searched locations:")
                for p in self._candidate_ibgateway_paths():
                    print(f"  - {p}")
                return 1
            print(f"✓ IB Gateway found at: {ibgateway_exec}")

            try:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
            except Exception as cleanup_exc:
                print(f"WARNING: Failed to clean up installer file: {cleanup_exc}")

            print("--- IB Gateway installation completed ---")
            print(f"Installation log available at {log_path}")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Installation failed: {e}")
            return 1
        except Exception as e:
            print(f"ERROR: {e}")
            return 1

    def _candidate_ibgateway_paths(self) -> List[str]:
        """Common places IB Gateway installs across Docker + GitHub Actions + local.

        Note: The standalone installer chooses a user-writable location on GitHub
        Actions runners (e.g. /home/runner/ibgateway), while our Docker image uses
        /opt/ibgateway.
        """
        candidates: List[str] = []

        # Allow callers/CI to override explicitly.
        explicit_exec = os.environ.get("IBGATEWAY_EXECUTABLE") or os.environ.get("IBGATEWAY_PATH")
        if explicit_exec:
            candidates.append(explicit_exec)

        explicit_home = os.environ.get("IBGATEWAY_HOME")
        if explicit_home:
            candidates.append(os.path.join(explicit_home, "ibgateway"))

        # Docker (root) default in this repo.
        candidates.append("/opt/ibgateway/ibgateway")

        # Common non-root install locations (GitHub Actions runner uses $HOME/ibgateway).
        home = os.path.expanduser("~")
        candidates.append(os.path.join(home, "ibgateway", "ibgateway"))

        user = os.environ.get("USER")
        if user:
            candidates.append(f"/home/{user}/ibgateway/ibgateway")

        # De-duplicate while preserving order.
        seen = set()
        ordered: List[str] = []
        for p in candidates:
            if p and p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered

    def _find_ibgateway_executable(self) -> Optional[str]:
        for path in self._candidate_ibgateway_paths():
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None
