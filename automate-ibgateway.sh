#!/bin/bash
# Script to automate IB Gateway GUI interactions
# This uses xdotool to control the IB Gateway window
#
# Configuration can be provided via:
#   - .env file (if present in script directory)
#   - Environment variables (override .env values)
#
# Environment Variables:
#   IB_USERNAME: IB Gateway username
#   IB_PASSWORD: IB Gateway password
#   IB_API_TYPE: "FIX" or "IB_API" (default: "IB_API")
#   IB_TRADING_MODE: "LIVE" or "PAPER" (default: "PAPER")
#
# Example usage:
#   IB_API_TYPE=FIX IB_TRADING_MODE=LIVE /automate-ibgateway.sh
#
# Example .env file:
#   IB_USERNAME=myusername
#   IB_PASSWORD=mypassword
#   IB_API_TYPE=IB_API
#   IB_TRADING_MODE=PAPER

set -e
export DISPLAY=:99

# Function to load .env file if it exists
load_env_file() {
    local env_file="${1:-.env}"
    
    if [ -f "$env_file" ]; then
        echo "Loading configuration from .env file: $env_file"
        
        # Read .env file line by line
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip empty lines and comments
            if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
                continue
            fi
            
            # Remove leading/trailing whitespace
            line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            
            # Skip if still empty after trimming
            [ -z "$line" ] && continue
            
            # Extract key and value (handle KEY=VALUE format)
            if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
                local key="${BASH_REMATCH[1]}"
                local value="${BASH_REMATCH[2]}"
                
                # Remove quotes if present
                value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                
                # Only set if not already set as environment variable (env vars override .env)
                if [ -z "${!key}" ]; then
                    export "$key=$value"
                    echo "  Loaded: $key"
                else
                    echo "  Skipped: $key (already set as environment variable)"
                fi
            fi
        done < "$env_file"
        echo ""
    else
        echo "No .env file found, using environment variables only"
        echo ""
    fi
}

# Load .env file if it exists (check script directory and current directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
load_env_file "$SCRIPT_DIR/.env" || load_env_file ".env" || true

# Configuration from environment variables with defaults
IB_USERNAME="${IB_USERNAME:-}"
IB_PASSWORD="${IB_PASSWORD:-}"
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
if [ -n "$IB_USERNAME" ]; then
    echo "Username: $IB_USERNAME"
else
    echo "Username: (not set)"
fi
if [ -n "$IB_PASSWORD" ]; then
    echo "Password: ***"
else
    echo "Password: (not set)"
fi
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

# Function to type username into the focused field
type_username() {
    local content_window=$1
    
    if [ -z "$IB_USERNAME" ]; then
        echo "Skipping username entry (IB_USERNAME not set)"
        return 0
    fi
    
    echo ""
    echo "=== Typing Username ==="
    echo "Typing username into focused field..."
    
    # Type the username directly into the window
    xdotool type --window "$content_window" --delay 50 "$IB_USERNAME"
    sleep 0.5
    
    echo "✓ Username typed"
}

# Function to type password (tab to password field first)
type_password() {
    local content_window=$1
    
    if [ -z "$IB_PASSWORD" ]; then
        echo "Skipping password entry (IB_PASSWORD not set)"
        return 0
    fi
    
    echo ""
    echo "=== Typing Password ==="
    echo "Navigating to password field..."
    
    # Tab to password field
    xdotool key --window "$content_window" Tab
    sleep 0.3
    
    # Type the password
    echo "Typing password..."
    xdotool type --window "$content_window" --delay 50 "$IB_PASSWORD"
    sleep 0.5
    
    echo "✓ Password typed"
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

    # Type username if provided (field already has focus)
    type_username "$CONTENT_WINDOW"
    
    # Type password if provided
    type_password "$CONTENT_WINDOW"
    
    
    echo ""
    echo "=== Configuration Complete ==="
    if [ -n "$IB_USERNAME" ]; then
        echo "Username: $IB_USERNAME"
    fi
    echo "API Type: $IB_API_TYPE"
    echo "Trading Mode: $IB_TRADING_MODE"
    echo ""
    echo "Note: If buttons were not clicked correctly, you may need to adjust"
    echo "the coordinates in this script based on your actual window layout."
}

# Run main function
main
