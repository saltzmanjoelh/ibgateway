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

# Add Poetry to PATH (persist for current session)
export PATH="$HOME/.local/bin:$PATH"

# Verify Poetry installation
if ! command -v poetry >/dev/null 2>&1; then
    echo "ERROR: Poetry installation failed or not in PATH"
    exit 1
fi

echo "Poetry installed: $(poetry --version)"

# Configure Poetry
poetry config virtualenvs.create false

# Note: poetry.lock is optional - poetry install works without it
# Use --no-root to skip installing the package itself (only install dependencies)
poetry install --no-interaction --no-ansi --no-root

# Verify Python dependencies are installed
if ! python3 -c "import PIL; import dotenv" 2>/dev/null; then
    echo "WARNING: Some Python dependencies may not be installed correctly"
fi

# Make ibgateway_cli.py executable if it exists
# Try common locations (Docker root, workspace root, current directory)
IBGATEWAY_CLI=""
for cli_path in /ibgateway_cli.py /workspace/ibgateway_cli.py ./ibgateway_cli.py; do
    if [ -f "$cli_path" ]; then
        chmod +x "$cli_path"
        IBGATEWAY_CLI="$cli_path"
        echo "Found IB Gateway CLI at: $cli_path"
        break
    fi
done

# Install IB Gateway using CLI tool (if found)
if [ -n "$IBGATEWAY_CLI" ]; then
    echo "=== Installing IB Gateway ==="
    python3 "$IBGATEWAY_CLI" install
    
    # Verify IB Gateway installation
    # Check common installation locations
    IBGATEWAY_EXEC=""
    for ibg_path in /opt/ibgateway/ibgateway /home/$USER/ibgateway/ibgateway "$HOME/ibgateway/ibgateway"; do
        if [ -f "$ibg_path" ] && [ -x "$ibg_path" ]; then
            IBGATEWAY_EXEC="$ibg_path"
            echo "✓ IB Gateway found at: $IBGATEWAY_EXEC"
            break
        fi
    done
    
    if [ -z "$IBGATEWAY_EXEC" ]; then
        echo "WARNING: IB Gateway executable not found in expected locations"
        echo "Installation may have completed but executable location is unknown"
    fi
else
    echo "Warning: ibgateway_cli.py not found in expected locations"
    echo "Searched: /ibgateway_cli.py /workspace/ibgateway_cli.py ./ibgateway_cli.py"
fi

# Create necessary directories
echo "=== Creating necessary directories ==="
mkdir -p /tmp/screenshots
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

# Generate machine-id for dbus if needed
if [ ! -f /etc/machine-id ] && [ -w /etc/machine-id ] 2>/dev/null; then
    echo "Generating machine-id for dbus..."
    dbus-uuidgen > /etc/machine-id 2>/dev/null || true
fi

echo ""
echo "=== Setup Complete ==="
echo "Poetry: $(poetry --version 2>/dev/null || echo 'not available')"
if [ -n "$IBGATEWAY_EXEC" ]; then
    echo "IB Gateway: Installed at $IBGATEWAY_EXEC"
else
    echo "IB Gateway: Installation attempted (verify manually)"
fi
echo "Screenshot directory: /tmp/screenshots"
echo ""
echo "To use IB Gateway CLI, ensure Poetry is in PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "To run automation:"
echo "  export DISPLAY=:99"
echo "  python3 $IBGATEWAY_CLI automate"