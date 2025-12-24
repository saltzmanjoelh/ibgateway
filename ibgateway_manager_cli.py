#!/usr/bin/env python3
"""
IB Gateway CLI Tool Entry Point
"""

import sys
from ibgateway_manager.automate_ibgateway import AutomationHandler
from ibgateway_manager.cli import IBGatewayCLI
from ibgateway_manager.config import Config


def main():
    """Main entry point."""
    cli = IBGatewayCLI()
    sys.exit(cli.run_command())

    # config = Config()
    # automator = AutomationHandler(config)
    # window_id = automator.wait_for_i_understand_button()
    # if window_id:
    #     automator.click_i_understand_button(window_id=window_id)
    # else:
    #     print("No IB Gateway window found.", file=sys.stderr)


if __name__ == "__main__":
    main()
