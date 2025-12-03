#!/usr/bin/env python3
"""
Helper script to compare screenshots and verify automation changes.
Can detect differences between before/after screenshots.
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: PIL/Pillow not available. Install with: pip install Pillow")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def compare_images_pil(img1_path, img2_path, threshold=0.01):
    """Compare two images using PIL and return similarity metrics."""
    if not HAS_PIL:
        return None
    
    try:
        img1 = Image.open(img1_path)
        img2 = Image.open(img2_path)
        
        # Ensure same size
        if img1.size != img2.size:
            print(f"WARNING: Images have different sizes: {img1.size} vs {img2.size}")
            return None
        
        # Convert to RGB if needed
        if img1.mode != 'RGB':
            img1 = img1.convert('RGB')
        if img2.mode != 'RGB':
            img2 = img2.convert('RGB')
        
        # Calculate difference
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        
        # Calculate mean difference per channel
        mean_diff = sum(stat.mean) / len(stat.mean)
        max_diff = max(stat.extrema[0][1], stat.extrema[1][1], stat.extrema[2][1])
        
        # Calculate percentage of different pixels
        diff_array = np.array(diff)
        different_pixels = np.sum(np.any(diff_array > 0, axis=2))
        total_pixels = diff_array.shape[0] * diff_array.shape[1]
        diff_percentage = (different_pixels / total_pixels) * 100
        
        return {
            'mean_diff': mean_diff,
            'max_diff': max_diff,
            'diff_percentage': diff_percentage,
            'is_similar': mean_diff < (255 * threshold),
            'has_changes': diff_percentage > 1.0  # More than 1% of pixels changed
        }
    except Exception as e:
        print(f"ERROR comparing images: {e}")
        return None


def compare_images_simple(img1_path, img2_path):
    """Simple file-based comparison."""
    if not os.path.exists(img1_path) or not os.path.exists(img2_path):
        return None
    
    size1 = os.path.getsize(img1_path)
    size2 = os.path.getsize(img2_path)
    
    return {
        'size1': size1,
        'size2': size2,
        'size_diff': abs(size1 - size2),
        'size_diff_percent': abs(size1 - size2) / max(size1, size2) * 100 if max(size1, size2) > 0 else 0
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: compare-screenshots.py <image1> <image2> [threshold]")
        print("  Compares two screenshots and reports differences")
        sys.exit(1)
    
    img1_path = sys.argv[1]
    img2_path = sys.argv[2]
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01
    
    if not os.path.exists(img1_path):
        print(f"ERROR: Image not found: {img1_path}")
        sys.exit(1)
    
    if not os.path.exists(img2_path):
        print(f"ERROR: Image not found: {img2_path}")
        sys.exit(1)
    
    print(f"Comparing images:")
    print(f"  Image 1: {img1_path}")
    print(f"  Image 2: {img2_path}")
    print()
    
    # Simple comparison
    simple_result = compare_images_simple(img1_path, img2_path)
    if simple_result:
        print("File size comparison:")
        print(f"  Image 1 size: {simple_result['size1']} bytes")
        print(f"  Image 2 size: {simple_result['size2']} bytes")
        print(f"  Size difference: {simple_result['size_diff']} bytes ({simple_result['size_diff_percent']:.2f}%)")
        print()
    
    # PIL comparison if available
    if HAS_PIL:
        pil_result = compare_images_pil(img1_path, img2_path, threshold)
        if pil_result:
            print("Image content comparison:")
            print(f"  Mean pixel difference: {pil_result['mean_diff']:.2f}")
            print(f"  Max pixel difference: {pil_result['max_diff']}")
            print(f"  Different pixels: {pil_result['diff_percentage']:.2f}%")
            print()
            
            if pil_result['has_changes']:
                print("✓ Images are different (changes detected)")
                if pil_result['is_similar']:
                    print("  Note: Changes are relatively small")
                else:
                    print("  Note: Significant changes detected")
            else:
                print("⚠ Images are very similar (minimal changes)")
            
            return 0 if pil_result['has_changes'] else 1
    else:
        print("WARNING: PIL/Pillow not available. Install for detailed comparison:")
        print("  pip install Pillow")
        print()
        print("Using file size comparison only.")
        if simple_result and simple_result['size_diff_percent'] > 5:
            print("✓ Files are different (size difference > 5%)")
            return 0
        else:
            print("⚠ Files are similar (size difference < 5%)")
            return 1


if __name__ == "__main__":
    sys.exit(main())
