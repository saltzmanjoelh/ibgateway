#!/bin/bash
# Test script to verify the draw-square functionality
# This can be run inside the Docker container to test the square drawing

set -e
export DISPLAY=:99

echo "=== Testing Square Drawing Functionality ==="
echo ""

# Test 1: Draw a square at a specific location
echo "Test 1: Drawing square at (100, 100)"
python3 /draw-square-on-screen.py 100 100 30 red 5.0 :99 &
SQUARE1_PID=$!
echo "Square 1 process: $SQUARE1_PID"
sleep 1

# Test 2: Draw another square at a different location
echo "Test 2: Drawing square at (200, 200)"
python3 /draw-square-on-screen.py 200 200 30 red 5.0 :99 &
SQUARE2_PID=$!
echo "Square 2 process: $SQUARE2_PID"
sleep 1

# Test 3: Draw a square at (350, 175) - FIX button location
echo "Test 3: Drawing square at FIX button location (350, 175)"
python3 /draw-square-on-screen.py 350 175 25 red 5.0 :99 &
SQUARE3_PID=$!
echo "Square 3 process: $SQUARE3_PID"
sleep 1

# Test 4: Draw a square at (500, 275) - Paper Trading button location
echo "Test 4: Drawing square at Paper Trading button location (500, 275)"
python3 /draw-square-on-screen.py 500 275 25 red 5.0 :99 &
SQUARE4_PID=$!
echo "Square 4 process: $SQUARE4_PID"

echo ""
echo "All squares should now be visible on the screen."
echo "Take a screenshot to see them:"
echo "  curl http://localhost:8080/screenshot"
echo ""
echo "Squares will disappear after 5 seconds."
echo "Waiting for squares to finish..."
sleep 6

echo ""
echo "=== Test Complete ==="
