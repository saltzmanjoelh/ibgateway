#!/bin/bash
# Script to compare test screenshot with current container screenshot

set -e

# Find the running container
CONTAINER_ID=$(docker ps -q -f ancestor=ibgateway)

if [ -z "$CONTAINER_ID" ]; then
    echo "ERROR: No running container found with ancestor=ibgateway"
    echo "Please start the container first using the 'Docker Run' task"
    exit 1
fi

echo "Found container: $CONTAINER_ID"
echo ""

# Test screenshot path (host)
TEST_SCREENSHOT="test-screenshots/ibapi-paper.png"

# Check if test screenshot exists
if [ ! -f "$TEST_SCREENSHOT" ]; then
    echo "ERROR: Test screenshot not found: $TEST_SCREENSHOT"
    exit 1
fi

# Container paths
CONTAINER_TEST_DIR="/tmp/screenshots"
CONTAINER_TEST_SCREENSHOT="$CONTAINER_TEST_DIR/ibapi-paper.png"

echo "=== Step 1: Copying test screenshot into container ==="
# Create directory in container if it doesn't exist
docker exec $CONTAINER_ID mkdir -p $CONTAINER_TEST_DIR

# Copy test screenshot into container
docker cp "$TEST_SCREENSHOT" "$CONTAINER_ID:$CONTAINER_TEST_SCREENSHOT"
echo "✓ Copied $TEST_SCREENSHOT to container at $CONTAINER_TEST_SCREENSHOT"
echo ""

echo "=== Step 2: Taking current screenshot from container ==="
# Take a new screenshot using HTTP API (uses default naming)
curl -s http://localhost:8080/screenshot > /dev/null
echo "✓ Screenshot taken (using default naming)"

# Get the latest screenshot path from the API
LATEST_RESPONSE=$(curl -s http://localhost:8080/screenshot/latest)
CONTAINER_CURRENT_SCREENSHOT=$(echo "$LATEST_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['screenshot_path'])")

if [ -z "$CONTAINER_CURRENT_SCREENSHOT" ]; then
    echo "ERROR: Failed to get latest screenshot path"
    exit 1
fi

echo "✓ Latest screenshot: $CONTAINER_CURRENT_SCREENSHOT"
echo ""

echo "=== Step 3: Comparing screenshots ==="
# Run comparison
docker exec $CONTAINER_ID python3 /ibgateway_cli.py compare-screenshots \
    "$CONTAINER_TEST_SCREENSHOT" \
    "$CONTAINER_CURRENT_SCREENSHOT"

EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=== Comparison completed ==="
else
    echo "=== Comparison completed with differences ==="
fi

exit $EXIT_CODE

