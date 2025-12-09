#!/bin/bash
set -x  # Enable debug output for bash script

# Update and install basic tools
apt-get update && apt-get install -y \
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
pip3 install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Note: poetry.lock is optional - poetry install works without it
# Use --no-root to skip installing the package itself (only install dependencies)
poetry install --no-interaction --no-ansi --no-root && \
    chmod +x /ibgateway_cli.py

# Install IB Gateway using CLI tool
python3 /ibgateway_cli.py install