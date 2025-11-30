#!/bin/bash
# Example script to automate IB Gateway GUI interactions
# This uses xdotool to control the IB Gateway window

set -e
export DISPLAY=:99

# Function to find the actual content window (not the 1x1 parent)
find_content_window() {
    local parent_id=$1
    echo "=== Inspecting window hierarchy for window $parent_id ==="
    
    # Get window tree
    xwininfo -tree -id "$parent_id" 2>/dev/null | head -50
    
    # Find child windows that are actually visible (larger than 1x1)
    echo ""
    echo "=== Searching for content windows ==="
    xdotool search --all --pid $(xdotool getwindowpid "$parent_id" 2>/dev/null || echo "") 2>/dev/null | while read win_id; do
        if [ "$win_id" != "$parent_id" ]; then
            geom=$(xdotool getwindowgeometry --shell "$win_id" 2>/dev/null)
            width=$(echo "$geom" | grep WIDTH | cut -d'=' -f2)
            height=$(echo "$geom" | grep HEIGHT | cut -d'=' -f2)
            name=$(xdotool getwindowname "$win_id" 2>/dev/null || echo "(no name)")
            
            # Only show windows that are reasonably sized
            if [ -n "$width" ] && [ -n "$height" ] && [ "$width" -gt 10 ] && [ "$height" -gt 10 ]; then
                echo "Window $win_id: ${width}x${height} - '$name'"
            fi
        fi
    done
}

# Function to list all windows and their properties
list_window_elements() {
    local window_id=$1
    echo ""
    echo "=== Listing all accessible windows ==="
    
    # Get all windows
    xdotool search --all --desktop 0 2>/dev/null | while read win_id; do
        name=$(xdotool getwindowname "$win_id" 2>/dev/null || echo "(no name)")
        class=$(xdotool getwindowclassname "$win_id" 2>/dev/null || echo "(no class)")
        geom=$(xdotool getwindowgeometry --shell "$win_id" 2>/dev/null)
        width=$(echo "$geom" | grep WIDTH | cut -d'=' -f2 2>/dev/null || echo "?")
        height=$(echo "$geom" | grep HEIGHT | cut -d'=' -f2 2>/dev/null || echo "?")
        x=$(echo "$geom" | grep X | head -1 | cut -d'=' -f2 2>/dev/null || echo "?")
        y=$(echo "$geom" | grep Y | head -1 | cut -d'=' -f2 2>/dev/null || echo "?")
        
        # Show windows that might be interactive elements
        if [ "$width" != "?" ] && [ "$height" != "?" ] && [ "$width" -gt 5 ] && [ "$height" -gt 5 ]; then
            echo "ID: $win_id | ${width}x${height} @ ($x,$y) | Class: $class | Name: $name"
        fi
    done
}

# Function to get window properties that might indicate button/field types
inspect_window_properties() {
    local window_id=$1
    echo ""
    echo "=== Window properties for $window_id ==="
    xprop -id "$window_id" 2>/dev/null | grep -E "WM_NAME|WM_CLASS|WM_WINDOW_ROLE|_NET_WM_WINDOW_TYPE" || echo "Limited property support (no window manager)"
}

# Function to click the IB API button
click_ib_api_button() {
    local content_window=$1
    echo ""
    echo "=== Clicking IB API button ==="
    
    # The IB API button is in the API Type section, upper-middle area
    # Based on 790x610 window, approximate coordinates:
    # - API Type section is roughly around y=150-200
    # - IB API button is to the right of FIX CTCI, roughly around x=450-550
    
    # Try clicking at approximate location (adjust these coordinates as needed)
    local button_x=500
    local button_y=175
    
    echo "Attempting to click IB API button at coordinates ($button_x, $button_y) relative to content window"
    
    # Move mouse to the button location and click
    xdotool mousemove --window "$content_window" "$button_x" "$button_y"
    sleep 0.5
    xdotool click --window "$content_window" 1
    
    echo "Click sent to IB API button"
}

# Function to help find button coordinates interactively
find_button_coordinates() {
    local content_window=$1
    echo ""
    echo "=== Interactive coordinate finder ==="
    echo "Content window ID: $content_window"
    echo "Window size: 790x610"
    echo ""
    echo "To find the exact coordinates of the IB API button:"
    echo "1. Move your mouse over the IB API button in the noVNC viewer"
    echo "2. Run this command in another terminal:"
    echo "   xdotool getmouselocation"
    echo ""
    echo "Or use this to click at different coordinates:"
    echo "   xdotool mousemove --window $content_window <X> <Y>"
    echo "   xdotool click --window $content_window 1"
    echo ""
    echo "Suggested coordinates to try (relative to content window):"
    echo "  - X: 450-550 (horizontal position)"
    echo "  - Y: 150-200 (vertical position, API Type section)"
}

# Wait for IB Gateway window to appear
echo "Waiting for IB Gateway window..."
timeout=60
elapsed=0
WINDOW_ID=""

while [ $elapsed -lt $timeout ]; do
    # Try multiple search methods to find IB Gateway window
    WINDOW_ID=$(xdotool search --class "install4j-ibgateway-GWClient" 2>/dev/null | head -1)
    if [ -z "$WINDOW_ID" ]; then
        WINDOW_ID=$(xdotool search --name "IBKR Gateway" 2>/dev/null | head -1)
    fi
    if [ -z "$WINDOW_ID" ]; then
        WINDOW_ID=$(xdotool search --all --name "IB" 2>/dev/null | head -1)
    fi
    
    if [ -n "$WINDOW_ID" ]; then
        echo "IB Gateway window found! Window ID: $WINDOW_ID"
        break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

if [ -z "$WINDOW_ID" ]; then
    echo "ERROR: IB Gateway window not found after ${timeout}s"
    exit 1
fi

# Find the content window (the actual 790x610 window)
CONTENT_WINDOW=$(xdotool search --name "IBKR Gateway" 2>/dev/null | head -1)
if [ -z "$CONTENT_WINDOW" ]; then
    echo "ERROR: Could not find content window"
    exit 1
fi

echo "Content window ID: $CONTENT_WINDOW"

# Click the IB API button
click_ib_api_button "$CONTENT_WINDOW"

# Also show helper function for finding coordinates
find_button_coordinates "$CONTENT_WINDOW"

echo ""
echo "=== Done ==="

# xdotool mousemove --window 16777225 793 284
# xdotool click --window 16777225 1  

