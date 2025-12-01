#!/bin/bash
# Script to forward external ports to IB Gateway local ports using socat
# IB Gateway only accepts connections from 127.0.0.1, so we forward:
#   - Port 4003 -> 127.0.0.1:4001 (Live Trading)
#   - Port 4004 -> 127.0.0.1:4002 (Paper Trading)

LIVE_PORT=4001
PAPER_PORT=4002
FORWARD_LIVE_PORT=4003
FORWARD_PAPER_PORT=4004
TIMEOUT=60
elapsed=0

echo "=== Starting socat port forwarding ==="
echo "Forwarding $FORWARD_LIVE_PORT -> 127.0.0.1:$LIVE_PORT (Live Trading)"
echo "Forwarding $FORWARD_PAPER_PORT -> 127.0.0.1:$PAPER_PORT (Paper Trading)"

# Function to check if a port is listening
check_port_listening() {
    local port=$1
    netstat -tlnp 2>/dev/null | grep -q ":$port " || ss -tlnp 2>/dev/null | grep -q ":$port "
}

# Wait for IB Gateway ports to be available
echo "Waiting for IB Gateway ports to be available..."
while [ $elapsed -lt $TIMEOUT ]; do
    if check_port_listening "$LIVE_PORT" && check_port_listening "$PAPER_PORT"; then
        echo "✓ IB Gateway ports are ready"
        break
    fi
    
    sleep 1
    elapsed=$((elapsed + 1))
    
    if [ $elapsed -eq $TIMEOUT ]; then
        echo "WARNING: IB Gateway ports not available after ${TIMEOUT}s, starting forwarding anyway"
        echo "Ports may become available later"
    fi
done

# Start socat forwarding for Live Trading port
echo "Starting socat forwarding for Live Trading ($FORWARD_LIVE_PORT -> 127.0.0.1:$LIVE_PORT)..."
socat TCP-LISTEN:$FORWARD_LIVE_PORT,fork,reuseaddr TCP:127.0.0.1:$LIVE_PORT &
SOCAT_LIVE_PID=$!
echo "✓ Live Trading forwarding started (PID: $SOCAT_LIVE_PID)"

# Start socat forwarding for Paper Trading port
echo "Starting socat forwarding for Paper Trading ($FORWARD_PAPER_PORT -> 127.0.0.1:$PAPER_PORT)..."
socat TCP-LISTEN:$FORWARD_PAPER_PORT,fork,reuseaddr TCP:127.0.0.1:$PAPER_PORT &
SOCAT_PAPER_PID=$!
echo "✓ Paper Trading forwarding started (PID: $SOCAT_PAPER_PID)"

# Verify forwarding is working
sleep 1
if check_port_listening "$FORWARD_LIVE_PORT" && check_port_listening "$FORWARD_PAPER_PORT"; then
    echo "✓ Port forwarding is active"
    echo "  - Live Trading: 0.0.0.0:$FORWARD_LIVE_PORT -> 127.0.0.1:$LIVE_PORT"
    echo "  - Paper Trading: 0.0.0.0:$FORWARD_PAPER_PORT -> 127.0.0.1:$PAPER_PORT"
else
    echo "WARNING: Port forwarding may not be active, check logs"
fi

# Keep script running and handle cleanup on exit
trap "kill $SOCAT_LIVE_PID $SOCAT_PAPER_PID 2>/dev/null; exit" SIGTERM SIGINT

# Wait for processes (they run in background, but we keep script alive)
# Use || true to prevent script from exiting if a process terminates
wait $SOCAT_LIVE_PID $SOCAT_PAPER_PID || true

