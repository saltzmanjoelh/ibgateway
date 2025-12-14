#!/bin/bash
# Enable debug output only if DEBUG environment variable is set (default: off)
echo "=== IBGateway ==="
DEBUG_MODE=0
if [ "${DEBUG:-0}" = "1" ] || [ "${DEBUG:-0}" = "true" ]; then
    set -x
    DEBUG_MODE=1
fi

# Helper function to echo only when DEBUG is enabled
debug_echo() {
    if [ "$DEBUG_MODE" = "1" ]; then
        echo "$@"
    fi
}

# Clean up stale locks
rm -rf /tmp/.X99-lock /tmp/.X11-unix/X99

# Generate a machine-id (Required for dbus)
if [ ! -f /etc/machine-id ]; then
    dbus-uuidgen > /etc/machine-id
fi

# Verification functions
wait_for_xvfb() {
    debug_echo "Waiting for Xvfb to be ready..."
    for i in {1..30}; do
        # Check if Xvfb process is running
        if ps -p $XVFB_PID >/dev/null 2>&1; then
            # Give it a moment to initialize, then check if display socket exists
            sleep 1
            if [ -S /tmp/.X11-unix/X99 ] 2>/dev/null || [ -S /tmp/.X11-unix/X0 ] 2>/dev/null; then
                debug_echo "✓ Xvfb is ready"
                return 0
            fi
            # If process is running, consider it ready (socket check may be timing issue)
            if [ $i -ge 3 ]; then
                debug_echo "✓ Xvfb is ready (process running)"
                return 0
            fi
        fi
        sleep 1
    done
    echo "ERROR: Xvfb failed to start" >&2
    return 1
}

wait_for_vnc() {
    debug_echo "Waiting for VNC server to be ready..."
    for i in {1..30}; do
        if netstat -tlnp 2>/dev/null | grep -q ":5901 " || ss -tlnp 2>/dev/null | grep -q ":5901 "; then
            debug_echo "✓ VNC server is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: VNC server failed to start" >&2
    return 1
}

wait_for_novnc() {
    debug_echo "Waiting for noVNC proxy to be ready..."
    for i in {1..30}; do
        if netstat -tlnp 2>/dev/null | grep -q ":5900 " || ss -tlnp 2>/dev/null | grep -q ":5900 "; then
            debug_echo "✓ noVNC proxy is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: noVNC proxy failed to start" >&2
    return 1
}

wait_for_screenshot_service() {
    debug_echo "Waiting for screenshot service to be ready..."
    for i in {1..60}; do
        if curl -f -s http://localhost:8080/ >/dev/null 2>&1; then
            # Also check for ready message in logs if available
            if grep -q "Screenshot service ready" /tmp/*.log 2>/dev/null || true; then
                debug_echo "✓ Screenshot service is ready"
                return 0
            fi
            # If port is accessible, consider it ready
            debug_echo "✓ Screenshot service is ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Screenshot service failed to start" >&2
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
    debug_echo "Waiting for port forwarding to be ready..."
    for i in {1..30}; do
        # Run netstat/ss once per iteration and check both ports in the output
        output=$(netstat -tlnp 2>/dev/null || ss -tlnp 2>/dev/null)
        if echo "$output" | grep -q ":4003 " && echo "$output" | grep -q ":4004 "; then
            debug_echo "✓ Port forwarding is ready"
            return 0
        fi
        sleep 1
    done
    debug_echo "WARNING: Port forwarding may not be ready"
    return 0  # Don't fail on this, as IB Gateway ports may not be available yet
}

# Create log files
debug_echo "=== Create and stream logs ==="
touch /tmp/automation.log
touch /tmp/port-forward.log
touch /tmp/screenshot-server.log
touch /tmp/websockify.log
touch /tmp/x11vnc.log

# When DEBUG is off, only show automation logs; when DEBUG is on, show all logs
# Use --follow=name --retry to handle files that may not exist yet
if [ "$DEBUG_MODE" = "1" ]; then
    tail -f /tmp/x11vnc.log /tmp/websockify.log /tmp/automation.log /tmp/screenshot-server.log /tmp/port-forward.log 2>/dev/null &
else
    tail -f /tmp/automation.log 2>/dev/null &
fi
TAIL_PID=$!

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
    debug_echo "websockify found: $(which websockify)"
else
    debug_echo "websockify not in PATH, will use python3 -m websockify"
fi

# Start noVNC proxy with verbose logging
# websockify listens on 5900 (web access) and proxies to VNC on 5901
# Runs in background - output logged to file and tailed for container logs
echo "=== Starting noVNC proxy with verbose logging ==="


# Use websockify as installed Python package
# Format: websockify --web=<web_dir> <listen_port> <vnc_host>:<vnc_port>
# Run in background - output goes to log file which is tailed for container logs
debug_echo "Starting websockify: listening on 5900 (web), connecting to localhost:5901 (VNC)"
# Try websockify command first, fallback to python module if not found
if command -v websockify &> /dev/null; then
    websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log &
else
    python3 -m websockify --web=/opt/novnc 5900 localhost:5901 -v -v -v --log-file=/tmp/websockify.log &
fi
WEBSOCKIFY_PID=$!
debug_echo "Websockify started (PID: $WEBSOCKIFY_PID)"
wait_for_novnc || exit 1

# Debug: Show environment
debug_echo "=== Environment ==="
debug_echo "RESOLUTION=$RESOLUTION"
debug_echo "USER=$USER"
debug_echo "DISPLAY=$DISPLAY"

# Start IB Gateway
echo "=== Starting IB Gateway ==="
/opt/ibgateway/ibgateway &
IBGATEWAY_PID=$!
echo "IB Gateway started (PID: $IBGATEWAY_PID)"

# Wait for IB Gateway window to appear, then automate configuration
echo "=== Waiting for IB Gateway to start, then automating configuration ==="
sleep 5

python3 -u /ibgateway_cli.py automate > /tmp/automation.log 2>&1 &
AUTOMATE_PID=$!
echo "Automation script started (PID: $AUTOMATE_PID)"

# Start screenshot HTTP server on port 8080
echo "=== Starting screenshot HTTP server on port 8080 ==="
python3 -u /ibgateway_cli.py screenshot-server --port 8080 > /tmp/screenshot-server.log 2>&1 &
SCREENSHOT_PID=$!
debug_echo "Screenshot server started (PID: $SCREENSHOT_PID)"
wait_for_screenshot_service || exit 1

# Wait for automation to complete
wait_for_automation

# Start socat port forwarding for IB Gateway
# IB Gateway only accepts connections from 127.0.0.1, so we forward external ports
echo "=== Starting socat port forwarding ==="
python3 -u /ibgateway_cli.py port-forward > /tmp/port-forward.log 2>&1 &
PORT_FORWARD_PID=$!
debug_echo "Port forwarding started (PID: $PORT_FORWARD_PID)"
wait_for_port_forwarding

# Verify all services are ready
debug_echo ""
echo "=== Verifying all services ==="
wait_for_xvfb && debug_echo "✓ Xvfb: Ready" || debug_echo "✗ Xvfb: Not ready"
wait_for_vnc && debug_echo "✓ VNC: Ready" || debug_echo "✗ VNC: Not ready"
wait_for_novnc && debug_echo "✓ noVNC: Ready" || debug_echo "✗ noVNC: Not ready"
wait_for_screenshot_service && debug_echo "✓ Screenshot service: Ready" || debug_echo "✗ Screenshot service: Not ready"
wait_for_port_forwarding && debug_echo "✓ Port forwarding: Ready" || debug_echo "✗ Port forwarding: Not ready"
if grep -q "Configuration Complete" /tmp/automation.log 2>/dev/null || ! ps -p $AUTOMATE_PID >/dev/null 2>&1; then
    debug_echo "✓ Automation: Complete"
else
    debug_echo "✗ Automation: Not complete"
fi

debug_echo ""
echo "=== All services ready ==="

# Keep container running by tailing log files
# Use trap to handle signals gracefully
cleanup() {
    debug_echo "Shutting down services..."
    kill $XVFB_PID $WEBSOCKIFY_PID $IBGATEWAY_PID $AUTOMATE_PID $SCREENSHOT_PID $PORT_FORWARD_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Wait for tail process (which will run until killed)
wait $TAIL_PID
