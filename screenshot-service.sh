#!/bin/bash
# Screenshot service - takes screenshots of display :99
# Usage: screenshot-service.sh [output_path]

set -e

export DISPLAY=:99
SCREENSHOT_DIR="/tmp/screenshots"
mkdir -p "$SCREENSHOT_DIR"

# Default output filename with timestamp
if [ -z "$1" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_PATH="$SCREENSHOT_DIR/screenshot_${TIMESTAMP}.png"
else
    OUTPUT_PATH="$1"
    # Security: Validate output path to prevent directory traversal
    # Reject paths with directory traversal attempts
    if [[ "$OUTPUT_PATH" == *".."* ]]; then
        echo "ERROR: Directory traversal not allowed in output path"
        exit 1
    fi
    # Resolve to absolute path for additional security check
    if command -v realpath &> /dev/null; then
        RESOLVED_PATH=$(realpath "$OUTPUT_PATH" 2>/dev/null || echo "$OUTPUT_PATH")
        # Allow paths within SCREENSHOT_DIR or /tmp/ (for testing)
        if [[ "$RESOLVED_PATH" != "$SCREENSHOT_DIR"/* ]] && [[ "$RESOLVED_PATH" != "/tmp/"* ]]; then
            echo "ERROR: Output path must be within $SCREENSHOT_DIR or /tmp/"
            exit 1
        fi
    else
        # Fallback validation without realpath
        if [[ "$OUTPUT_PATH" != "$SCREENSHOT_DIR"/* ]] && [[ "$OUTPUT_PATH" != "/tmp/"* ]]; then
            echo "ERROR: Output path must be within $SCREENSHOT_DIR or /tmp/"
            exit 1
        fi
    fi
fi

# Take screenshot using scrot (preferred) or import (imagemagick fallback)
if command -v scrot &> /dev/null; then
    echo "Taking screenshot with scrot..."
    scrot -z "$OUTPUT_PATH"
elif command -v import &> /dev/null; then
    echo "Taking screenshot with imagemagick..."
    import -window root "$OUTPUT_PATH"
else
    echo "ERROR: No screenshot tool available (scrot or imagemagick)"
    exit 1
fi

if [ -f "$OUTPUT_PATH" ]; then
    echo "Screenshot saved to: $OUTPUT_PATH"
    echo "$OUTPUT_PATH"
    exit 0
else
    echo "ERROR: Screenshot file was not created"
    exit 1
fi
