#!/usr/bin/env python3
"""
Correct horizontal banding using dark/reference pixels on the right side of the frame.

Separates slow background (scatter/drift) from fast banding component and subtracts only the banding.
"""

import numpy as np
import tifffile as tiff
import argparse

# Configuration: reference pixel stripe position
BLACK_W = 80        # Width of reference stripe in pixels (use last BLACK_W columns from right edge)
BLACK_OFFSET = 0    # Offset from right edge (always 0 = use rightmost columns)


def moving_average_1d(x: np.ndarray, win: int) -> np.ndarray:
    """Moving average with edge padding."""
    win = int(win)
    if win < 3:
        return x.astype(np.float32)
    
    x = x.astype(np.float32)
    k = np.ones(win, dtype=np.float32) / win
    
    pad_left = win // 2
    pad_right = win - 1 - pad_left  # makes output length exactly len(x)
    
    xp = np.pad(x, (pad_left, pad_right), mode="edge")
    y = np.convolve(xp, k, mode="valid")
    return y


def optimize_smooth_window(img_u16: np.ndarray, black_w: int = 10, black_offset: int = 20, candidates: list[int] = None) -> tuple[int, float]:
    """
    Find optimal smooth window size by testing different values.
    
    Args:
        img_u16: Input image (H, W) uint16
        black_w: Width of reference stripe in pixels
        black_offset: Offset from right edge (0 = last columns, 20 = columns -20 to -20-black_w)
        candidates: List of smooth window sizes to test (default: more intermediate values)
    
    Returns:
        (best_window, best_score) - Best smooth window size and its quality score (lower is better)
    """
    if candidates is None:
        h = img_u16.shape[0]
        # Test from 10 to 512 in steps of 5 for thorough optimization
        max_win = min(512, h // 4)
        # Generate candidates: 10, 15, 20, 25, ... up to max_win
        candidates = list(range(10, max_win + 1, 5))
        # Ensure we have at least a few candidates
        if len(candidates) == 0:
            candidates = [10, 32, 64, 128, 256]
    
    img = img_u16.astype(np.float32)
    w = img.shape[1]
    # Extract stripe with offset: columns [w - black_offset - black_w : w - black_offset]
    stripe = img[:, w - black_offset - black_w : w - black_offset]
    ref = np.median(stripe, axis=1)
    
    best_window = candidates[0]
    best_score = float('inf')
    
    print(f"Testing smooth window sizes: {candidates}")
    
    for smooth_win in candidates:
        # Calculate banding correction
        ref_slow = moving_average_1d(ref, smooth_win)
        band = ref - ref_slow
        
        # Apply correction to reference stripe
        corrected_stripe = stripe - band[:, np.newaxis]
        corrected_ref = np.median(corrected_stripe, axis=1)
        
        # Quality metric: std of corrected reference stripe (lower = more uniform = better)
        score = np.std(corrected_ref)
        
        print(f"  Window {smooth_win:3d}: corrected stripe std = {score:.2f}")
        
        if score < best_score:
            best_score = score
            best_window = smooth_win
    
    print(f"Best smooth window: {best_window} (score: {best_score:.2f})")
    return best_window, best_score


def detect_banding(img_u16: np.ndarray, black_w: int = 10, black_offset: int = 20, smooth_win: int = 128, threshold: float = 5.0) -> tuple[bool, float]:
    """
    Detect if horizontal banding is present in the image.
    
    Args:
        img_u16: Input image (H, W) uint16
        black_w: Width of reference stripe in pixels
        black_offset: Offset from right edge (0 = last columns, 20 = columns -20 to -20-black_w)
        smooth_win: Window size for slow background smoothing
        threshold: Minimum std of banding component to consider it significant (default: 5.0)
    
    Returns:
        (has_banding, banding_std) - True if banding detected, and std of banding component
    """
    img = img_u16.astype(np.float32)
    w = img.shape[1]
    
    # Extract reference stripe with offset: columns [w - black_offset - black_w : w - black_offset]
    stripe = img[:, w - black_offset - black_w : w - black_offset]
    ref = np.median(stripe, axis=1)
    
    # Calculate banding component
    ref_slow = moving_average_1d(ref, smooth_win)
    band = ref - ref_slow
    
    # Check if banding is significant
    band_std = np.std(band)
    has_banding = band_std > threshold
    
    return has_banding, band_std


def correct_banding(img_u16: np.ndarray, black_w: int = 10, black_offset: int = 20, smooth_win: int = 128, auto_detect: bool = False, threshold: float = 5.0, auto_optimize: bool = False) -> tuple[np.ndarray, bool]:
    """
    Correct horizontal banding by separating slow background from fast banding.
    
    Args:
        img_u16: Input image (H, W) uint16
        black_w: Width of reference stripe in pixels (default: 10)
        black_offset: Offset from right edge (0 = last columns, 20 = columns -20 to -20-black_w) (default: 20)
        smooth_win: Window size for slow background smoothing in rows (default: 128)
        auto_detect: If True, only apply correction if banding is detected (default: False)
        threshold: Minimum std of banding component to consider it significant (default: 5.0)
        auto_optimize: If True, automatically find best smooth window size (default: False)
    
    Returns:
        (corrected_image, correction_applied) - Corrected image and flag if correction was applied
    """
    # Auto-optimize smooth window if requested
    if auto_optimize:
        print("Auto-optimizing smooth window size...")
        smooth_win, _ = optimize_smooth_window(img_u16, black_w, black_offset)
        print(f"Using optimized smooth window: {smooth_win}")
    
    # Auto-detect banding if requested
    if auto_detect:
        has_banding, band_std = detect_banding(img_u16, black_w, black_offset, smooth_win, threshold)
        if not has_banding:
            print(f"Banding detection: std={band_std:.2f} (threshold={threshold:.2f})")
            print("No significant banding detected - skipping correction")
            return img_u16.copy(), False
        print(f"Banding detected: std={band_std:.2f} (threshold={threshold:.2f}) - applying correction")
    
    img = img_u16.astype(np.float32)
    w = img.shape[1]
    
    # Extract reference stripe with offset: columns [w - black_offset - black_w : w - black_offset]
    col_start = w - black_offset - black_w
    col_end = w - black_offset
    print(f"Using reference pixels: columns {col_start} to {col_end} (width={black_w}, offset={black_offset} from right)")
    stripe = img[:, col_start : col_end]  # (H, black_w)
    ref = np.median(stripe, axis=1)  # (H,) - robust per-row measurement
    
    # Separate slow background from fast banding
    ref_slow = moving_average_1d(ref, smooth_win)
    band = ref - ref_slow  # (H,) - fast-varying banding component only
    
    # Subtract only banding from entire image
    corrected = img - band[:, np.newaxis]
    
    # Diagnostic: check reference stripe after correction (should be uniform)
    corrected_stripe = corrected[:, w - black_offset - black_w : w - black_offset]
    corrected_ref = np.median(corrected_stripe, axis=1)
    corrected_ref_std = np.std(corrected_ref)
    corrected_ref_range = np.max(corrected_ref) - np.min(corrected_ref)
    
    print(f"\nBefore correction - Reference stripe:")
    print(f"  Row-to-row std: {np.std(ref):.2f}, range: {np.max(ref) - np.min(ref):.2f}")
    print(f"After correction - Reference stripe:")
    print(f"  Row-to-row std: {corrected_ref_std:.2f}, range: {corrected_ref_range:.2f}")
    print(f"  (Should be much smaller - stripe should be uniform)")
    
    if corrected_ref_std > np.std(ref) * 0.3:
        print(f"  WARNING: Reference stripe still has gradients! Try larger --smooth-win")
    
    # Keep in 16-bit range (no limit on floating point adjustment before this)
    corrected = np.clip(corrected, 0, 65535).astype(np.uint16)
    return corrected, True


def main():
    parser = argparse.ArgumentParser(
        description="Correct horizontal banding using dark reference pixels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: always applies correction with smooth window 128
  python correct_banding_dark_pixels.py input.tiff
  
  # Auto-optimize: find best smooth window size automatically
  python correct_banding_dark_pixels.py input.tiff --auto-optimize
  
  # Auto-detect: only correct if banding is detected
  python correct_banding_dark_pixels.py input.tiff --auto-detect
  
  # Combine auto-optimize and auto-detect
  python correct_banding_dark_pixels.py input.tiff --auto-optimize --auto-detect
  
  # Custom stripe width and smooth window
  python correct_banding_dark_pixels.py input.tiff --black-w 20 --smooth-win 64
        """
    )
    parser.add_argument("input", help="Input TIFF file path")
    parser.add_argument("-o", "--output", help="Output TIFF file path (default: input_corrected.tiff)")
    parser.add_argument("--black-w", type=int, default=BLACK_W,
                        help=f"Width of reference stripe in pixels (default: {BLACK_W})")
    parser.add_argument("--black-offset", type=int, default=BLACK_OFFSET,
                        help=f"Offset from right edge in pixels (0 = last columns, {BLACK_OFFSET} = columns -{BLACK_OFFSET} to -{BLACK_OFFSET}-width) (default: {BLACK_OFFSET})")
    parser.add_argument("--smooth-win", type=int, default=128,
                        help="Window size for slow background smoothing in rows (default: 128)")
    parser.add_argument("--auto-detect", action="store_true",
                        help="Only apply correction if banding is detected (default: always correct)")
    parser.add_argument("--auto-optimize", action="store_true",
                        help="Automatically find best smooth window size by testing different values")
    parser.add_argument("--threshold", type=float, default=5.0,
                        help="Minimum std of banding component to consider it significant (default: 5.0)")
    
    args = parser.parse_args()
    
    # Load image
    print(f"Loading: {args.input}")
    img = tiff.imread(args.input)
    
    # Handle multi-page/stacks: use first page
    if img.ndim > 2:
        if img.ndim == 3 and img.shape[0] == 1:
            img = img[0]
        elif img.ndim == 3:
            print(f"Warning: Image has {img.shape[0]} pages, using first page")
            img = img[0]
        else:
            print(f"Warning: Unexpected shape {img.shape}, using first slice")
            img = img[0]
    
    print(f"Image shape: {img.shape}, dtype: {img.dtype}")
    
    # Correct banding (or detect first if auto-detect enabled)
    corrected, correction_applied = correct_banding(
        img, 
        black_w=args.black_w,
        black_offset=args.black_offset,
        smooth_win=args.smooth_win,
        auto_detect=args.auto_detect,
        threshold=args.threshold,
        auto_optimize=args.auto_optimize
    )
    
    if not correction_applied:
        print("\nNo correction applied - image unchanged")
    
    # Save corrected image
    if args.output:
        out_path = args.output
    else:
        base = args.input.rsplit(".", 1)[0]
        ext = args.input.rsplit(".", 1)[1] if "." in args.input else "tiff"
        out_path = f"{base}_corrected.{ext}"
    
    print(f"\nSaving corrected image: {out_path}")
    tiff.imwrite(out_path, corrected, photometric="minisblack", compression=None)
    print("Done!")


if __name__ == "__main__":
    main()
