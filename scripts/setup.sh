#!/bin/bash
set -x  # Enable debug output for bash script

# Determine if we need sudo (not running as root)
if [ "$EUID" -eq 0 ]; then
    # Running as root (e.g., in Docker), no sudo needed
    APT_CMD="apt-get"
else
    # Not root, use sudo if available
    if command -v sudo >/dev/null 2>&1; then
        APT_CMD="sudo apt-get"
    else
        # No sudo available, try without (will fail if not root)
        APT_CMD="apt-get"
    fi
fi

# Update and install basic tools
$APT_CMD update && $APT_CMD install -y \
    xvfb \
    xterm \
    dbus-x11 \
    python3 \
    python3-pip \
    python3-numpy \
    net-tools \
    curl \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    socat

# Install Poetry
pip3 install --no-cache-dir poetry

# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"

# Configure Poetry
poetry config virtualenvs.create false

# Note: poetry.lock is optional - poetry install works without it
# Use --no-root to skip installing the package itself (only install dependencies)
poetry install --no-interaction --no-ansi --no-root

# Make ibgateway_cli.py executable if it exists
# Try common locations (Docker root, workspace root, current directory)
for cli_path in /ibgateway_cli.py /workspace/ibgateway_cli.py ./ibgateway_cli.py; do
    if [ -f "$cli_path" ]; then
        chmod +x "$cli_path"
        IBGATEWAY_CLI="$cli_path"
        break
    fi
done

# Install IB Gateway using CLI tool (if found)
if [ -n "$IBGATEWAY_CLI" ]; then
    python3 "$IBGATEWAY_CLI" install
else
    echo "Warning: ibgateway_cli.py not found in expected locations"
fi