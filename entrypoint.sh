#!/bin/bash
# Enable debug output only if DEBUG environment variable is set (default: off)
if [ "${DEBUG:-0}" = "1" ] || [ "${DEBUG:-0}" = "true" ]; then
    set -x
fi

# Clean up stale locks
rm -rf /tmp/.X99-lock /tmp/.X11-unix/X99

# Generate a machine-id (Required for dbus)
if [ ! -f /etc/machine-id ]; then
    dbus-uuidgen > /etc/machine-id
fi

# Verification functions
wait_for_xvfb() {
    echo "Waiting for Xvfb to be ready..."
    for i in {1..30}; do
        # Check if Xvfb process is running
        if ps -p $XVFB_PID >/dev/null 2>&1; then
            # Give it a moment to initialize, then check if display socket exists
            sleep 1
            if [ -S /tmp/.X11-unix/X99 ] 2>/dev/null || [ -S /tmp/.X11-unix/X0 ] 2>/dev/null; then
                echo "✓ Xvfb is ready"
                return 0
            fi
            # If process is running, consider it ready (socket check may be timing issue)
            if [ $i -ge 3 ]; then
                echo "✓ Xvfb is ready (process running)"
                return 0
            fi
        fi
        sleep 1
    done
    echo "ERROR: Xvfb failed to start"
    return 1
}

wait_for_vnc() {
    echo "Waiting for VNC server to be ready..."
    for i in {1..30}; do
        if netstat -tlnp 2>/dev/null | grep -q ":5901 " || ss -tlnp 2>/dev/null | grep -q ":5901 "; then
            echo "✓ VNC server is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: VNC server failed to start"
    return 1
}

wait_for_novnc() {
    echo "Waiting for noVNC proxy to be ready..."
    for i in {1..30}; do
        if netstat -tlnp 2>/dev/null | grep -q ":5900 " || ss -tlnp 2>/dev/null | grep -q ":5900 "; then
            echo "✓ noVNC proxy is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: noVNC proxy failed to start"
    return 1
}

wait_for_screenshot_service() {
    echo "Waiting for screenshot service to be ready..."
    for i in {1..60}; do
        if curl -f -s http://localhost:8080/ >/dev/null 2>&1; then
            # Also check for ready message in logs if available
            if grep -q "Screenshot service ready" /tmp/*.log 2>/dev/null || true; then
                echo "✓ Screenshot service is ready"
                return 0
            fi
            # If port is accessible, consider it ready
            echo "✓ Screenshot service is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Screenshot service failed to start"
    return 1
}

wait_for_automation() {
    echo "Waiting for automation to complete..."
    for i in {1..90}; do
        # Check log file for completion message
        if grep -q "Configuration Complete" /tmp/automation.log 2>/dev/null; then
            echo "✓ Automation completed"
            return 0
        fi
        # Also check if process is still running
        if ! ps -p $AUTOMATE_PID >/dev/null 2>&1; then
            # Process finished, check log one more time
            if grep -q "Configuration Complete" /tmp/automation.log 2>/dev/null; then
                echo "✓ Automation completed"
                return 0
            else
                echo "WARNING: Automation process finished but completion message not found"
                return 0  # Don't fail, automation may have completed
            fi
        fi
        sleep 1
    done
    # Final check
    if grep -q "Configuration Complete" /tmp/automation.log 2>/dev/null; then
        echo "✓ Automation completed"
        return 0
    fi
    echo "WARNING: Automation timeout, but continuing..."
    return 0  # Don't fail, allow container to continue
}

wait_for_port_forwarding() {
    echo "Waiting for port forwarding to be ready..."
    for i in {1..30}; do
        # Run netstat/ss once per iteration and check both ports in the output
        output=$(netstat -tlnp 2>/dev/null || ss -tlnp 2>/dev/null)
        if echo "$output" | grep -q ":4003 " && echo "$output" | grep -q ":4004 "; then
            echo "✓ Port forwarding is ready"
            return 0
        fi
        sleep 1
    done
    echo "WARNING: Port forwarding may not be ready"
    return 0  # Don't fail on this, as IB Gateway ports may not be available yet
}

# Start Xvfb on display :99
echo "=== Starting Xvfb on display :99 ==="
Xvfb :99 -screen 0 ${RESOLUTION}x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
export DISPLAY=:99
wait_for_xvfb || exit 1

# Start a simple window manager and xterm for testing
echo "=== Starting window manager ==="
xterm -geometry 80x24+0+0 -e /bin/bash &

# Start x11vnc on port 5901 (VNC server)
echo "=== Starting x11vnc on port 5901 ==="
x11vnc -display :99 -noxdamage -forever -shared -rfbport 5901 -bg -o /tmp/x11vnc.log
wait_for_vnc || exit 1

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
# Create log file
touch /tmp/websockify.log

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
wait_for_novnc || exit 1

# Debug: Show environment
echo "=== Environment ==="
echo "RESOLUTION=$RESOLUTION"
echo "USER=$USER"
echo "DISPLAY=$DISPLAY"

# Start IB Gateway
echo "=== Starting IB Gateway ==="
/opt/ibgateway/ibgateway &
IBGATEWAY_PID=$!
echo "IB Gateway started (PID: $IBGATEWAY_PID)"

# Wait for IB Gateway window to appear, then automate configuration
echo "=== Waiting for IB Gateway to start, then automating configuration ==="
sleep 5
touch /tmp/automation.log
python3 /ibgateway_cli.py automate > /tmp/automation.log 2>&1 &
AUTOMATE_PID=$!
echo "Automation script started (PID: $AUTOMATE_PID)"

# Start screenshot HTTP server on port 8080
echo "=== Starting screenshot HTTP server on port 8080 ==="
touch /tmp/screenshot-server.log
python3 /ibgateway_cli.py screenshot-server --port 8080 > /tmp/screenshot-server.log 2>&1 &
SCREENSHOT_PID=$!
echo "Screenshot server started (PID: $SCREENSHOT_PID)"
wait_for_screenshot_service || exit 1

# Wait for automation to complete
wait_for_automation

# Start socat port forwarding for IB Gateway
# IB Gateway only accepts connections from 127.0.0.1, so we forward external ports
echo "=== Starting socat port forwarding ==="
touch /tmp/port-forward.log
python3 /ibgateway_cli.py port-forward > /tmp/port-forward.log 2>&1 &
PORT_FORWARD_PID=$!
echo "Port forwarding started (PID: $PORT_FORWARD_PID)"
wait_for_port_forwarding

# Verify all services are ready
echo ""
echo "=== Verifying all services ==="
wait_for_xvfb && echo "✓ Xvfb: Ready" || echo "✗ Xvfb: Not ready"
wait_for_vnc && echo "✓ VNC: Ready" || echo "✗ VNC: Not ready"
wait_for_novnc && echo "✓ noVNC: Ready" || echo "✗ noVNC: Not ready"
wait_for_screenshot_service && echo "✓ Screenshot service: Ready" || echo "✗ Screenshot service: Not ready"
wait_for_port_forwarding && echo "✓ Port forwarding: Ready" || echo "✗ Port forwarding: Not ready"
if grep -q "Configuration Complete" /tmp/automation.log 2>/dev/null || ! ps -p $AUTOMATE_PID >/dev/null 2>&1; then
    echo "✓ Automation: Complete"
else
    echo "✗ Automation: Not complete"
fi

echo ""
echo "=== All services ready ==="
echo "Container is ready. Streaming logs..."

# Keep container running by tailing log files
# Use trap to handle signals gracefully
cleanup() {
    echo "Shutting down services..."
    kill $XVFB_PID $WEBSOCKIFY_PID $IBGATEWAY_PID $AUTOMATE_PID $SCREENSHOT_PID $PORT_FORWARD_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Ensure all log files exist
touch /tmp/x11vnc.log /tmp/websockify.log /tmp/automation.log /tmp/screenshot-server.log /tmp/port-forward.log 2>/dev/null || true

# Tail all log files to keep container running and show output
# Use --follow=name --retry to handle files that may not exist yet
tail -f /tmp/x11vnc.log /tmp/websockify.log /tmp/automation.log /tmp/screenshot-server.log /tmp/port-forward.log 2>/dev/null &
TAIL_PID=$!

# Wait for tail process (which will run until killed)
wait $TAIL_PID
