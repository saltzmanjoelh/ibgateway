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

# Start noVNC proxy with verbose logging
# websockify listens on 5900 (web access) and proxies to VNC on 5901
# Runs in background - output logged to file and tailed for container logs
echo "=== Starting noVNC proxy with verbose logging ==="
# Create log file and tail it in background so we can see it in docker logs
touch /tmp/websockify.log
tail -f /tmp/websockify.log &

# Use websockify as installed Python package
# Format: websockify --web=<web_dir> <listen_port> <vnc_host>:<vnc_port>
# Run in background - output goes to log file which is tailed for container logs
echo "Starting websockify: listening on 5900 (web), connecting to localhost:5901 (VNC)"
# Try websockify command first, fallback to python module if not found
if command -v websockify &> /dev/null; then
    websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log &
else
    python3 -m websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log &
fi
WEBSOCKIFY_PID=$!
echo "Websockify started (PID: $WEBSOCKIFY_PID)"
sleep 2

# Debug: Show environment
echo "=== Environment ==="
echo "RESOLUTION=$RESOLUTION"
echo "USER=$USER"
echo "DISPLAY=$DISPLAY"

/opt/ibgateway/ibgateway &

# Wait for IB Gateway window to appear, then automate configuration
echo "=== Waiting for IB Gateway to start, then automating configuration ==="
sleep 5
python3 -m ibgateway.cli automate &
AUTOMATE_PID=$!
echo "Automation script started (PID: $AUTOMATE_PID)"

# Start screenshot HTTP server on port 8080
echo "=== Starting screenshot HTTP server on port 8080 ==="
python3 -m ibgateway.cli screenshot-server --port 8080 &
sleep 1
echo "Screenshot service available at: http://localhost:8080/"

# Start socat port forwarding for IB Gateway
# IB Gateway only accepts connections from 127.0.0.1, so we forward external ports
echo "=== Starting socat port forwarding ==="
python3 -m ibgateway.cli port-forward &
SOCAT_PID=$!
echo "Socat forwarding started (PID: $SOCAT_PID)"
sleep 2

# Keep container running
# Tail all log files together so we can see output in docker logs
echo "=== All services started, keeping container alive ==="
echo "Container is ready. Logs will be streamed below."
# Keep container alive indefinitely - wait for interrupt signal
while true; do
    sleep 3600
done
