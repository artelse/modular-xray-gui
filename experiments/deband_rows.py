"""
Remove horizontal banding by estimating a smooth row-wise band profile
(low-pass of row statistic) and subtracting it. High-contrast content
doesn't drive the correction because we smooth the profile first.
"""
import sys
import numpy as np
import tifffile as tiff


def _smooth1d(y: np.ndarray, radius: int) -> np.ndarray:
    """Uniform-window moving average; reflect at edges."""
    if radius <= 0:
        return y
    n = len(y)
    kernel = np.ones(2 * radius + 1, dtype=np.float64) / (2 * radius + 1)
    # Pad so we get same length and smooth edges
    pad = np.pad(y.astype(np.float64), radius, mode="reflect")
    out = np.convolve(pad, kernel, mode="valid")
    return out


def deband_rows_band_profile(
    img: np.ndarray,
    row_stat: str = "median",
    smooth_radius: int = 80,
) -> np.ndarray:
    """
    Remove horizontal banding by subtracting a smooth row-wise band profile.

    - row_stat: "median" or "mean" per row (median is more robust to hot pixels).
    - smooth_radius: half-width of smoothing window in rows; larger = only
      removes very slow row-to-row drift (typical banding). Try 50–150 for
      2000-pixel height.
    """
    if img.dtype != np.uint16:
        img = img.astype(np.uint16)
    work = img.astype(np.float64)

    # Per-row statistic (1D profile)
    if row_stat == "median":
        row_profile = np.median(work, axis=1)
    else:
        row_profile = np.mean(work, axis=1)

    # Low-pass: this is the "band" we want to remove (smooth row-to-row variation)
    band_profile = _smooth1d(row_profile, smooth_radius)

    # Subtract band so rows are leveled; keep global level via reference
    ref = np.mean(band_profile)
    work = work - (band_profile[:, np.newaxis] - ref)

    # Clip and cast
    work = np.clip(work, 0, 65535).astype(np.uint16)
    return work


def deband_rows_median(img: np.ndarray) -> np.ndarray:
    """Legacy: subtract each row's median (sensitive to high-contrast content)."""
    if img.dtype != np.uint16:
        img = img.astype(np.uint16)
    work = img.astype(np.int32)
    row_med = np.median(work, axis=1).astype(np.int32)
    work -= row_med[:, None]
    global_med = int(np.median(img))
    work += global_med
    work = np.clip(work, 0, 65535).astype(np.uint16)
    return work

def main():
    if len(sys.argv) < 2:
        print("Usage: python deband_rows.py input.tiff [smooth_radius]")
        print("  smooth_radius = rows half-window for band profile (default 80); try 50–150.")
        sys.exit(1)

    in_path = sys.argv[1]
    smooth_radius = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    out_path = in_path.rsplit(".", 1)[0] + "_deband.tiff"

    img = tiff.imread(in_path)

    if img.ndim > 2:
        img2 = img[0]
    else:
        img2 = img

    out = deband_rows_band_profile(img2, smooth_radius=smooth_radius)
    tiff.imwrite(out_path, out)

    print("Wrote:", out_path)

if __name__ == "__main__":
    main()
