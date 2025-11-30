#!/bin/bash
# Local test script for screenshot service
# Usage: ./test-screenshot-service.sh [container_name]

set -e

CONTAINER_NAME=${1:-ibgateway-test}
SCREENSHOT_PORT=${SCREENSHOT_PORT:-8080}

echo "=== Testing Screenshot Service ==="
echo "Container: $CONTAINER_NAME"
echo "Port: $SCREENSHOT_PORT"
echo ""

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "ERROR: Container '$CONTAINER_NAME' is not running"
    echo "Start it with:"
    echo "  docker run -d --name $CONTAINER_NAME --platform linux/amd64 -p 5900:5900 -p $SCREENSHOT_PORT:$SCREENSHOT_PORT ibgateway-test:latest"
    exit 1
fi

echo "✓ Container is running"
echo ""

# Wait for service to be ready
echo "Waiting for screenshot service to be ready..."
for i in {1..30}; do
    if curl -f -s "http://localhost:$SCREENSHOT_PORT/" > /dev/null 2>&1; then
        echo "✓ Screenshot service is accessible"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Screenshot service failed to start"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    sleep 1
done
echo ""

# Test root endpoint
echo "Testing GET /"
curl -f -s "http://localhost:$SCREENSHOT_PORT/" > /dev/null || exit 1
echo "✓ Root endpoint works"
echo ""

# Test taking a screenshot
echo "Testing GET /screenshot"
RESPONSE=$(curl -f -s "http://localhost:$SCREENSHOT_PORT/screenshot")
echo "Response: $RESPONSE"
if command -v jq &> /dev/null; then
    echo "$RESPONSE" | jq -e '.success == true' || exit 1
    SCREENSHOT_URL=$(echo "$RESPONSE" | jq -r '.url')
    SCREENSHOT_FILENAME=$(echo "$RESPONSE" | jq -r '.filename')
    FULL_URL=$(echo "$RESPONSE" | jq -r '.full_url')
else
    # Fallback if jq is not available
    SCREENSHOT_URL=$(echo "$RESPONSE" | grep -o '"/screenshots/[^"]*"' | tr -d '"')
    SCREENSHOT_FILENAME=$(basename "$SCREENSHOT_URL")
    FULL_URL="http://localhost:$SCREENSHOT_PORT$SCREENSHOT_URL"
fi
echo "✓ Screenshot taken: $SCREENSHOT_FILENAME"
echo "  URL: $FULL_URL"
echo ""

# Test viewing the screenshot
echo "Testing GET $SCREENSHOT_URL"
curl -f -s -o /tmp/test-screenshot.png "http://localhost:$SCREENSHOT_PORT$SCREENSHOT_URL" || exit 1
if command -v file &> /dev/null; then
    file /tmp/test-screenshot.png | grep -q "PNG image" || exit 1
fi
echo "✓ Screenshot image downloaded and is valid PNG"
echo "  Saved to: /tmp/test-screenshot.png"
echo ""

# Test listing screenshots
echo "Testing GET /screenshots"
SCREENSHOTS=$(curl -f -s "http://localhost:$SCREENSHOT_PORT/screenshots")
if command -v jq &> /dev/null; then
    echo "$SCREENSHOTS" | jq -e '.success == true' || exit 1
    COUNT=$(echo "$SCREENSHOTS" | jq -r '.count')
    echo "✓ Screenshot list works (found $COUNT screenshots)"
else
    echo "$SCREENSHOTS"
    echo "✓ Screenshot list endpoint responded"
fi
echo ""

# Test latest screenshot endpoint
echo "Testing GET /screenshot/latest"
LATEST=$(curl -f -s "http://localhost:$SCREENSHOT_PORT/screenshot/latest")
if command -v jq &> /dev/null; then
    echo "$LATEST" | jq -e '.success == true' || exit 1
    LATEST_FILENAME=$(echo "$LATEST" | jq -r '.filename')
    LATEST_URL=$(echo "$LATEST" | jq -r '.full_url')
    echo "✓ Latest screenshot endpoint works"
    echo "  Latest: $LATEST_FILENAME"
    echo "  URL: $LATEST_URL"
else
    echo "$LATEST"
    echo "✓ Latest screenshot endpoint responded"
fi
echo ""

# Verify screenshot tools
echo "Verifying screenshot tools are installed..."
docker exec "$CONTAINER_NAME" which scrot > /dev/null || exit 1
docker exec "$CONTAINER_NAME" which import > /dev/null || exit 1
echo "✓ Screenshot tools (scrot, imagemagick) are installed"
echo ""

# Test screenshot service script directly
echo "Testing screenshot-service.sh script..."
docker exec "$CONTAINER_NAME" /screenshot-service.sh /tmp/test-direct.png > /dev/null || exit 1
docker exec "$CONTAINER_NAME" test -f /tmp/test-direct.png || exit 1
echo "✓ Screenshot service script works"
echo ""

echo "=== All tests passed! ==="
echo ""
echo "You can view screenshots at:"
echo "  http://localhost:$SCREENSHOT_PORT/"
echo "  http://localhost:$SCREENSHOT_PORT/screenshots"
echo ""
echo "Latest screenshot:"
if command -v jq &> /dev/null; then
    LATEST_URL=$(curl -s "http://localhost:$SCREENSHOT_PORT/screenshot/latest" | jq -r '.full_url')
    echo "  $LATEST_URL"
fi
