#!/bin/bash
# CI-friendly test script for IB Gateway automation
# Simplified version that works well in GitHub Actions
# Tests that automation runs successfully and takes verification screenshots

set -e

CONTAINER_NAME=${1:-ibgateway-test}
SCREENSHOT_PORT=${SCREENSHOT_PORT:-8080}
SCREENSHOT_DIR="/tmp/test-screenshots"
mkdir -p "$SCREENSHOT_DIR"

echo "=== Testing IB Gateway Automation (CI Mode) ==="
echo "Container: $CONTAINER_NAME"
echo "Screenshot directory: $SCREENSHOT_DIR"
echo ""

# Function to take a screenshot
take_screenshot() {
    local label=$1
    local output_file="$SCREENSHOT_DIR/${label}.png"
    
    echo "Taking screenshot: $label"
    
    # Wait a bit for the service to be ready
    sleep 2
    
    RESPONSE=$(curl -f -s "http://localhost:$SCREENSHOT_PORT/screenshot" 2>/dev/null || echo "")
    
    if [ -z "$RESPONSE" ]; then
        echo "ERROR: Failed to take screenshot for $label"
        return 1
    fi
    
    # Extract screenshot URL
    if command -v jq &> /dev/null; then
        SCREENSHOT_URL=$(echo "$RESPONSE" | jq -r '.url' 2>/dev/null || echo "")
    else
        SCREENSHOT_URL=$(echo "$RESPONSE" | grep -o '"/screenshots/[^"]*"' | tr -d '"' | head -1)
    fi
    
    if [ -n "$SCREENSHOT_URL" ]; then
        curl -f -s -o "$output_file" "http://localhost:$SCREENSHOT_PORT$SCREENSHOT_URL" 2>/dev/null || return 1
        
        if [ -f "$output_file" ] && [ -s "$output_file" ]; then
            local file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file" 2>/dev/null || echo "0")
            echo "✓ Screenshot saved: $output_file (${file_size} bytes)"
            return 0
        fi
    fi
    
    echo "ERROR: Failed to save screenshot for $label"
    return 1
}

# Function to test a configuration
test_configuration() {
    local api_type=$1
    local trading_mode=$2
    local test_name="${api_type}_${trading_mode}"
    
    echo ""
    echo "--- Testing: $test_name (API: $api_type, Mode: $trading_mode) ---"
    
    # Cleanup previous container
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    
    # Start container
    echo "Starting container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --platform linux/amd64 \
        -p 5900:5900 \
        -p "$SCREENSHOT_PORT:$SCREENSHOT_PORT" \
        -e IB_API_TYPE="$api_type" \
        -e IB_TRADING_MODE="$trading_mode" \
        ibgateway-test:latest
    
    # Wait for services
    echo "Waiting for services to start..."
    sleep 15
    
    # Check screenshot service
    for i in {1..30}; do
        if curl -f -s "http://localhost:$SCREENSHOT_PORT/" > /dev/null 2>&1; then
            echo "✓ Screenshot service ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "ERROR: Screenshot service not available"
            docker logs "$CONTAINER_NAME"
            return 1
        fi
        sleep 1
    done
    
    # Wait for IB Gateway window
    echo "Waiting for IB Gateway window..."
    for i in {1..60}; do
        if docker exec "$CONTAINER_NAME" xdotool search --name "IBKR Gateway" 2>/dev/null | grep -q .; then
            echo "✓ IB Gateway window found"
            break
        fi
        if [ $i -eq 60 ]; then
            echo "ERROR: IB Gateway window not found"
            docker logs "$CONTAINER_NAME" | tail -50
            return 1
        fi
        sleep 1
    done
    
    # Wait for automation to complete
    echo "Waiting for automation to complete..."
    sleep 15
    
    # Take verification screenshot
    if take_screenshot "$test_name"; then
        echo "✓ Test passed: $test_name"
        
        # Check logs for automation messages
        if docker logs "$CONTAINER_NAME" 2>&1 | grep -qi "configuration complete\|api type.*$api_type\|trading mode.*$trading_mode"; then
            echo "✓ Automation logs verified"
        else
            echo "WARNING: Automation logs not clearly visible"
            docker logs "$CONTAINER_NAME" | grep -i "automation\|configuration\|api\|trading" | tail -10 || true
        fi
        
        return 0
    else
        echo "✗ Test failed: $test_name"
        docker logs "$CONTAINER_NAME" | tail -50
        return 1
    fi
}

# Check if image exists
if ! docker images | grep -q "ibgateway-test.*latest"; then
    echo "ERROR: Docker image 'ibgateway-test:latest' not found"
    exit 1
fi

# Run tests
PASSED=0
FAILED=0

# Test default configuration
if test_configuration "IB_API" "PAPER"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Test alternative configuration
if test_configuration "FIX" "LIVE"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Cleanup
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Summary
echo ""
echo "=========================================="
echo "Test Results"
echo "=========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""
echo "Screenshots saved in: $SCREENSHOT_DIR"
ls -lh "$SCREENSHOT_DIR" || true
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All automation tests passed!"
    exit 0
else
    echo "✗ Some automation tests failed"
    exit 1
fi
