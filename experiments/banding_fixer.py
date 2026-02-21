import numpy as np
import tifffile as tiff

BLACK_W = 10        # width of the right stripe in pixels (adjust)
SMOOTH_WIN = 128     # rows; bigger = preserve more "real" gradient

import numpy as np

def moving_average_1d(x, win):
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


def correct_banding(img_u16):
    img = img_u16.astype(np.float32)

    stripe = img[:, -BLACK_W:]                  # (H, BLACK_W)
    ref = np.median(stripe, axis=1)             # (H,)
    ref_slow = moving_average_1d(ref, SMOOTH_WIN)
    band = ref - ref_slow                       # (H,)

    corrected = img - band[:, None]

    # keep in 16-bit range
    corrected = np.clip(corrected, 0, 65535).astype(np.uint16)
    return corrected

img = tiff.imread("dark_5.0.tif")
out = correct_banding(img)
tiff.imwrite("input_banding_fixed.tiff", out)
print("Wrote input_banding_fixed.tiff")
