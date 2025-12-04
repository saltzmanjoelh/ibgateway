#!/usr/bin/env python3
"""
IB Gateway CLI Tool Entry Point
"""

import sys
from ibgateway.cli import IBGatewayCLI


def main():
    """Main entry point."""
    cli = IBGatewayCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()
