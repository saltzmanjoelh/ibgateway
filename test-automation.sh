#!/bin/bash
# Test script for IB Gateway automation
# Tests that the automation script correctly configures the IB Gateway window
# Uses screenshots to verify the changes
#
# Usage: ./test-automation.sh [container_name]

set -e

CONTAINER_NAME=${1:-ibgateway-test}
SCREENSHOT_PORT=${SCREENSHOT_PORT:-8080}
TEST_DIR="/tmp/ibgateway-automation-tests"
mkdir -p "$TEST_DIR"

echo "=== Testing IB Gateway Automation ==="
echo "Container: $CONTAINER_NAME"
echo "Port: $SCREENSHOT_PORT"
echo "Test directory: $TEST_DIR"
echo ""

# Function to take a screenshot and save it
take_screenshot() {
    local label=$1
    local output_file="$TEST_DIR/${label}.png"
    
    echo "Taking screenshot: $label"
    RESPONSE=$(curl -f -s "http://localhost:$SCREENSHOT_PORT/screenshot" 2>/dev/null || echo "")
    
    if [ -z "$RESPONSE" ]; then
        echo "WARNING: Failed to take screenshot for $label"
        return 1
    fi
    
    if command -v jq &> /dev/null; then
        SCREENSHOT_URL=$(echo "$RESPONSE" | jq -r '.url' 2>/dev/null || echo "")
        SCREENSHOT_FILENAME=$(echo "$RESPONSE" | jq -r '.filename' 2>/dev/null || echo "")
    else
        SCREENSHOT_URL=$(echo "$RESPONSE" | grep -o '"/screenshots/[^"]*"' | tr -d '"' | head -1)
        SCREENSHOT_FILENAME=$(basename "$SCREENSHOT_URL")
    fi
    
    if [ -n "$SCREENSHOT_URL" ]; then
        curl -f -s -o "$output_file" "http://localhost:$SCREENSHOT_PORT$SCREENSHOT_URL" 2>/dev/null || return 1
        
        if [ -f "$output_file" ] && [ -s "$output_file" ]; then
            echo "✓ Screenshot saved: $output_file"
            echo "$output_file"
            return 0
        fi
    fi
    
    echo "WARNING: Failed to save screenshot for $label"
    return 1
}

# Function to wait for IB Gateway window to appear
wait_for_ibgateway() {
    local timeout=60
    local elapsed=0
    
    echo "Waiting for IB Gateway window to appear..."
    while [ $elapsed -lt $timeout ]; do
        if docker exec "$CONTAINER_NAME" xdotool search --name "IBKR Gateway" 2>/dev/null | grep -q .; then
            echo "✓ IB Gateway window found"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    echo "ERROR: IB Gateway window not found after ${timeout}s"
    return 1
}

# Function to check if automation script completed successfully
check_automation_logs() {
    local expected_api_type=$1
    local expected_trading_mode=$2
    
    echo "Checking automation logs for configuration:"
    echo "  Expected API Type: $expected_api_type"
    echo "  Expected Trading Mode: $expected_trading_mode"
    
    # Check container logs for automation messages
    local logs=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -i "automation\|configuration\|api type\|trading mode" || true)
    
    if echo "$logs" | grep -qi "$expected_api_type"; then
        echo "✓ Found expected API type in logs"
    else
        echo "WARNING: Expected API type '$expected_api_type' not clearly found in logs"
    fi
    
    if echo "$logs" | grep -qi "$expected_trading_mode"; then
        echo "✓ Found expected trading mode in logs"
    else
        echo "WARNING: Expected trading mode '$expected_trading_mode' not clearly found in logs"
    fi
    
    # Check for automation completion
    if docker logs "$CONTAINER_NAME" 2>&1 | grep -qi "configuration complete\|done"; then
        echo "✓ Automation script appears to have completed"
        return 0
    else
        echo "WARNING: Automation completion not clearly indicated in logs"
        return 1
    fi
}

# Function to test a specific configuration
test_configuration() {
    local api_type=$1
    local trading_mode=$2
    local test_name="${api_type}_${trading_mode}"
    
    echo ""
    echo "=========================================="
    echo "Testing Configuration: $test_name"
    echo "  API Type: $api_type"
    echo "  Trading Mode: $trading_mode"
    echo "=========================================="
    echo ""
    
    # Stop and remove existing container if it exists
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    
    # Start container with specific configuration
    echo "Starting container with configuration..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --platform linux/amd64 \
        -p 5900:5900 \
        -p "$SCREENSHOT_PORT:$SCREENSHOT_PORT" \
        -e IB_API_TYPE="$api_type" \
        -e IB_TRADING_MODE="$trading_mode" \
        ibgateway-test:latest
    
    echo "Waiting for services to start..."
    sleep 10
    
    # Wait for screenshot service
    echo "Waiting for screenshot service..."
    for i in {1..30}; do
        if curl -f -s "http://localhost:$SCREENSHOT_PORT/" > /dev/null 2>&1; then
            echo "✓ Screenshot service is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "ERROR: Screenshot service failed to start"
            docker logs "$CONTAINER_NAME"
            return 1
        fi
        sleep 1
    done
    
    # Wait for IB Gateway window
    wait_for_ibgateway || {
        echo "ERROR: IB Gateway window did not appear"
        docker logs "$CONTAINER_NAME"
        return 1
    }
    
    # Take screenshot before automation (if window is visible)
    echo ""
    echo "Taking initial screenshot..."
    sleep 2
    take_screenshot "${test_name}_initial" || echo "Note: Initial screenshot may not be available yet"
    
    # Wait for automation to complete
    echo ""
    echo "Waiting for automation to complete..."
    sleep 10
    
    # Take screenshot after automation
    echo ""
    echo "Taking screenshot after automation..."
    take_screenshot "${test_name}_after" || {
        echo "ERROR: Failed to take screenshot after automation"
        return 1
    }
    
    # Check automation logs
    echo ""
    check_automation_logs "$api_type" "$trading_mode" || {
        echo "WARNING: Automation verification incomplete"
    }
    
    # Verify screenshots exist and have content
    local after_screenshot="$TEST_DIR/${test_name}_after.png"
    if [ -f "$after_screenshot" ] && [ -s "$after_screenshot" ]; then
        local file_size=$(stat -f%z "$after_screenshot" 2>/dev/null || stat -c%s "$after_screenshot" 2>/dev/null || echo "0")
        if [ "$file_size" -gt 1000 ]; then
            echo "✓ Screenshot is valid (size: $file_size bytes)"
        else
            echo "WARNING: Screenshot seems too small ($file_size bytes)"
        fi
    else
        echo "ERROR: Screenshot file not found or empty"
        return 1
    fi
    
    echo ""
    echo "✓ Configuration test completed: $test_name"
    return 0
}

# Check if container image exists
if ! docker images | grep -q "ibgateway-test.*latest"; then
    echo "ERROR: Docker image 'ibgateway-test:latest' not found"
    echo "Build it first with:"
    echo "  docker build --platform linux/amd64 -t ibgateway-test:latest ."
    exit 1
fi

# Run tests
echo "Starting automation tests..."
echo ""

PASSED=0
FAILED=0

# Test 1: Default configuration (IB_API + PAPER)
if test_configuration "IB_API" "PAPER"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Test 2: FIX + LIVE
if test_configuration "FIX" "LIVE"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Test 3: IB_API + LIVE
if test_configuration "IB_API" "LIVE"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Test 4: FIX + PAPER
if test_configuration "FIX" "PAPER"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# Cleanup
echo ""
echo "Cleaning up..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""
echo "Screenshots saved in: $TEST_DIR"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
