#!/bin/bash
# Script to set up baseline screenshots from GitHub Actions artifacts

set -e

BASELINE_DIR="tests/baseline_screenshots"
ARTIFACT_PATTERN="automation-test-screenshots-*"

echo "=== Setting up baseline screenshots ==="

# Check if we're in a GitHub Actions environment
if [ -n "$GITHUB_ACTIONS" ]; then
    echo "Running in GitHub Actions environment"
    ARTIFACT_DIRS=$(find . -type d -name "$ARTIFACT_PATTERN" 2>/dev/null || true)
else
    echo "Running locally"
    echo "Please download artifacts from GitHub Actions first:"
    echo "1. Go to your workflow run"
    echo "2. Download the 'automation-test-screenshots-*' artifacts"
    echo "3. Extract them in the current directory"
    echo "4. Run this script again"
    exit 1
fi

if [ -z "$ARTIFACT_DIRS" ]; then
    echo "ERROR: No artifact directories found matching $ARTIFACT_PATTERN"
    exit 1
fi

mkdir -p "$BASELINE_DIR"

# Copy screenshots from artifacts
for artifact_dir in $ARTIFACT_DIRS; do
    if [ -d "$artifact_dir" ]; then
        echo "Processing artifacts from: $artifact_dir"
        for screenshot in "$artifact_dir"/*.png; do
            if [ -f "$screenshot" ]; then
                filename=$(basename "$screenshot")
                echo "  Copying $filename to $BASELINE_DIR/"
                cp "$screenshot" "$BASELINE_DIR/$filename"
            fi
        done
    fi
done

echo ""
echo "Baseline screenshots set up:"
ls -lh "$BASELINE_DIR/" || echo "No screenshots found"

if [ -n "$GITHUB_ACTIONS" ]; then
    echo ""
    echo "To commit these baselines, run:"
    echo "  git add $BASELINE_DIR/*.png"
    echo "  git commit -m 'Add baseline screenshots'"
    echo "  git push"
fi
