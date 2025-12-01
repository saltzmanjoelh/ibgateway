#!/bin/bash
# Script to automate IB Gateway GUI interactions
# This uses xdotool to control the IB Gateway window
#
# Environment Variables:
#   IB_API_TYPE: "FIX" or "IB_API" (default: "IB_API")
#   IB_TRADING_MODE: "LIVE" or "PAPER" (default: "PAPER")
#
# Example usage:
#   IB_API_TYPE=FIX IB_TRADING_MODE=LIVE /automate-ibgateway.sh

set -e
export DISPLAY=:99

# Configuration from environment variables with defaults
IB_API_TYPE="${IB_API_TYPE:-IB_API}"  # Default: IB_API
IB_TRADING_MODE="${IB_TRADING_MODE:-PAPER}"  # Default: PAPER

# Normalize values to uppercase
IB_API_TYPE=$(echo "$IB_API_TYPE" | tr '[:lower:]' '[:upper:]')
IB_TRADING_MODE=$(echo "$IB_TRADING_MODE" | tr '[:lower:]' '[:upper:]')

# Validate values
if [ "$IB_API_TYPE" != "FIX" ] && [ "$IB_API_TYPE" != "IB_API" ]; then
    echo "ERROR: IB_API_TYPE must be 'FIX' or 'IB_API', got: $IB_API_TYPE"
    exit 1
fi

if [ "$IB_TRADING_MODE" != "LIVE" ] && [ "$IB_TRADING_MODE" != "PAPER" ]; then
    echo "ERROR: IB_TRADING_MODE must be 'LIVE' or 'PAPER', got: $IB_TRADING_MODE"
    exit 1
fi

echo "=== IB Gateway Automation Configuration ==="
echo "API Type: $IB_API_TYPE"
echo "Trading Mode: $IB_TRADING_MODE"
echo ""

# Button coordinates (relative to content window, approximately 790x610)
# These coordinates are estimates and may need adjustment based on actual window layout
FIX_BUTTON_X=500
FIX_BUTTON_Y=300
IB_API_BUTTON_X=700
IB_API_BUTTON_Y=300

# Trading Mode section: y ~250-300
LIVE_TRADING_BUTTON_X=500
LIVE_TRADING_BUTTON_Y=340
PAPER_TRADING_BUTTON_X=700
PAPER_TRADING_BUTTON_Y=300

# Function to safely click at coordinates
click_at_coordinates() {
    local content_window=$1
    local x=$2
    local y=$3
    local button_name=$4
    
    echo "Clicking $button_name at coordinates ($x, $y)"
    
    # Move mouse to the button location
    xdotool mousemove --window "$content_window" "$x" "$y"
    sleep 0.3
    
    # Click
    xdotool click --window "$content_window" 1
    sleep 0.5
    
    echo "✓ Clicked $button_name"
}

# Function to click API Type button
click_api_type_button() {
    local content_window=$1
    
    echo ""
    echo "=== Configuring API Type: $IB_API_TYPE ==="
    
    if [ "$IB_API_TYPE" = "FIX" ]; then
        click_at_coordinates "$content_window" "$FIX_BUTTON_X" "$FIX_BUTTON_Y" "FIX CTCI"
    else
        click_at_coordinates "$content_window" "$IB_API_BUTTON_X" "$IB_API_BUTTON_Y" "IB API"
    fi
}

# Function to click Trading Mode button
click_trading_mode_button() {
    local content_window=$1
    
    echo ""
    echo "=== Configuring Trading Mode: $IB_TRADING_MODE ==="
    
    if [ "$IB_TRADING_MODE" = "LIVE" ]; then
        click_at_coordinates "$content_window" "$LIVE_TRADING_BUTTON_X" "$LIVE_TRADING_BUTTON_Y" "Live Trading"
    else
        click_at_coordinates "$content_window" "$PAPER_TRADING_BUTTON_X" "$PAPER_TRADING_BUTTON_Y" "Paper Trading"
    fi
}

# Function to find the IB Gateway content window
find_ibgateway_window() {
    local timeout=60
    local elapsed=0
    local window_id=""
    
    echo "Waiting for IB Gateway window to appear..."
    
    while [ $elapsed -lt $timeout ]; do
        # Try multiple search methods to find IB Gateway window
        window_id=$(xdotool search --class "install4j-ibgateway-GWClient" 2>/dev/null | head -1)
        if [ -z "$window_id" ]; then
            window_id=$(xdotool search --name "IBKR Gateway" 2>/dev/null | head -1)
        fi
        if [ -z "$window_id" ]; then
            window_id=$(xdotool search --all --name "IB" 2>/dev/null | head -1)
        fi
        
        if [ -n "$window_id" ]; then
            echo "✓ IB Gateway window found! Window ID: $window_id"
            echo "$window_id"
            return 0
        fi
        
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    echo "ERROR: IB Gateway window not found after ${timeout}s"
    return 1
}

# Main execution
main() {
    # Find the IB Gateway window
    CONTENT_WINDOW=$(find_ibgateway_window)
    if [ -z "$CONTENT_WINDOW" ]; then
        exit 1
    fi
    
    echo ""
    echo "Content window ID: $CONTENT_WINDOW"
    
    # Wait a bit for the window to fully render
    echo "Waiting for window to fully render..."
    sleep 2
    
    # Click API Type button
    click_api_type_button "$CONTENT_WINDOW"
    
    # Click Trading Mode button
    click_trading_mode_button "$CONTENT_WINDOW"
    
    echo ""
    echo "=== Configuration Complete ==="
    echo "API Type: $IB_API_TYPE"
    echo "Trading Mode: $IB_TRADING_MODE"
    echo ""
    echo "Note: If buttons were not clicked correctly, you may need to adjust"
    echo "the coordinates in this script based on your actual window layout."
}

# Run main function
main
