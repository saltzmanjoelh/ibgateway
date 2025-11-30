#!/bin/bash
set -x  # Enable debug output for bash script

# Clean up stale locks
rm -rf /tmp/.X99-lock /tmp/.X11-unix/X99

# Generate a machine-id (Required for dbus)
if [ ! -f /etc/machine-id ]; then
    dbus-uuidgen > /etc/machine-id
fi

# Start Xvfb on display :99
echo "=== Starting Xvfb on display :99 ==="
Xvfb :99 -screen 0 ${RESOLUTION}x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99
sleep 2

# Start a simple window manager and xterm for testing
echo "=== Starting window manager ==="
xterm -geometry 80x24+0+0 -e /bin/bash &

# Start x11vnc on port 5901 (VNC server)
echo "=== Starting x11vnc on port 5901 ==="
x11vnc -display :99 -noxdamage -forever -shared -rfbport 5901 -bg -o /tmp/x11vnc.log
sleep 2

# Debug: Check if VNC server is running
echo "=== Checking VNC server status ==="
echo "Checking all listening ports:"
netstat -tlnp || ss -tlnp
echo "Specifically checking port 5901 (VNC server):"
netstat -tlnp | grep 5901 || ss -tlnp | grep 5901 || echo "WARNING: No service listening on port 5901 - VNC server may not be running!"

# Tail x11vnc log in background
tail -f /tmp/x11vnc.log &

# Debug: Check websockify availability
echo "=== Checking websockify installation ==="
if command -v websockify &> /dev/null; then
    echo "websockify found: $(which websockify)"
else
    echo "websockify not in PATH, will use python3 -m websockify"
fi

# Debug: Show environment
echo "=== Environment ==="
echo "RESOLUTION=$RESOLUTION"
echo "USER=$USER"
echo "DISPLAY=$DISPLAY"

/opt/ibgateway/ibgateway &

# Start screenshot HTTP server on port 8080
echo "=== Starting screenshot HTTP server on port 8080 ==="
python3 /screenshot-server.py &
sleep 1
echo "Screenshot service available at: http://localhost:8080/"

# Start noVNC proxy with verbose logging
# websockify listens on 5900 (web access) and proxies to VNC on 5901
# This runs in FOREGROUND to keep the container alive
echo "=== Starting noVNC proxy with verbose logging ==="
# Create log file and tail it in background so we can see it in docker logs
touch /tmp/websockify.log
tail -f /tmp/websockify.log &

# Use websockify as installed Python package
# Format: websockify --web=<web_dir> <listen_port> <vnc_host>:<vnc_port>
# This MUST run in foreground (no &) to keep container running
echo "Starting websockify: listening on 5900 (web), connecting to localhost:5901 (VNC)"
# Try websockify command first, fallback to python module if not found
if command -v websockify &> /dev/null; then
    exec websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log
else
    exec python3 -m websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log
fi

