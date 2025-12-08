#!/usr/bin/env python3
"""
Compare current screenshots with baseline screenshots.
Exits with code 0 if screenshots are similar, 1 if they differ significantly.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import ibgateway
sys.path.insert(0, str(Path(__file__).parent.parent))

from ibgateway.cli import IBGatewayCLI


def compare_screenshot(current_path: str, baseline_path: str, threshold: float = 0.05) -> bool:
    """
    Compare a current screenshot with a baseline.
    
    Args:
        current_path: Path to current screenshot
        baseline_path: Path to baseline screenshot
        threshold: Similarity threshold (default: 0.05 = 5% mean pixel difference)
    
    Returns:
        True if screenshots are similar, False otherwise
    """
    if not os.path.exists(current_path):
        print(f"ERROR: Current screenshot not found: {current_path}")
        return False
    
    if not os.path.exists(baseline_path):
        print(f"WARNING: Baseline screenshot not found: {baseline_path}")
        print(f"  This is expected on first run. Current screenshot will be used as baseline.")
        return True  # Allow first run to pass
    
    print(f"\n=== Comparing screenshots ===")
    print(f"Current:  {current_path}")
    print(f"Baseline: {baseline_path}")
    
    cli = IBGatewayCLI()
    result = cli._compare_images_pil(current_path, baseline_path, threshold)
    
    if result is None:
        print("ERROR: Could not compare images (different sizes or error)")
        return False
    
    print(f"\nComparison results:")
    print(f"  Mean pixel difference: {result['mean_diff']:.2f}")
    print(f"  Max pixel difference: {result['max_diff']}")
    print(f"  Different pixels: {result['diff_percentage']:.2f}%")
    print(f"  Threshold: {threshold * 100}%")
    
    # Check if images are similar enough
    is_similar = result['is_similar']
    diff_percentage = result['diff_percentage']
    
    # Consider similar if:
    # 1. Mean difference is below threshold, AND
    # 2. Different pixels are less than 5%
    if is_similar and diff_percentage < 5.0:
        print(f"\n✓ Screenshots are similar (within acceptable range)")
        return True
    else:
        print(f"\n✗ Screenshots differ significantly")
        print(f"  Mean diff threshold: {255 * threshold:.2f}, actual: {result['mean_diff']:.2f}")
        print(f"  Different pixels: {diff_percentage:.2f}% (threshold: 5%)")
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: compare_screenshots.py <current_screenshot> <baseline_screenshot> [threshold]")
        sys.exit(1)
    
    current_path = sys.argv[1]
    baseline_path = sys.argv[2]
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    
    is_similar = compare_screenshot(current_path, baseline_path, threshold)
    sys.exit(0 if is_similar else 1)


if __name__ == "__main__":
    main()
