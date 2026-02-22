"""
GUI constants and path/nearest-match helpers for dark/flat fields.
Pure helpers: no GUI reference. Used by gui.py and ui.dark_flat.
"""

import re
import math
import pathlib

# App directory (parent of ui/)
_APP_DIR = pathlib.Path(__file__).resolve().parent.parent

# Default frame size when no detector module loaded
DEFAULT_FRAME_W = 2400
DEFAULT_FRAME_H = 2400

# Master darks, flats, pixel maps, default open/save folder
DARK_DIR = _APP_DIR / "darks"
FLAT_DIR = _APP_DIR / "flats"
PIXELMAPS_DIR = _APP_DIR / "pixelmaps"
CAPTURES_DIR = _APP_DIR / "captures"

LAST_CAPTURED_DARK_NAME = "last_captured_dark.npy"
LAST_CAPTURED_FLAT_NAME = "last_captured_flat.npy"
INTEGRATION_CHOICES = ["0.5 s", "1 s", "2 s", "5 s", "10 s", "15 s", "20 s"]
DARK_STACK_DEFAULT = 20  # default frames for dark/flat stacking (slider 1-50)
DARK_FLAT_MATCH_THRESHOLD = 1.0  # max distance to auto-apply dark/flat
HIST_MIN_12BIT = 0.0
HIST_MAX_12BIT = 4095.0
# Full-scale values for effective bit-depth detection (opened images)
FULL_SCALE_12BIT = 4095.0
FULL_SCALE_14BIT = 16383.0
FULL_SCALE_16BIT = 65535.0


def dark_dir(camera_name):
    """Base directory for darks for this camera (subfolder under DARK_DIR)."""
    return DARK_DIR / (camera_name or "default")


def flat_dir(camera_name):
    """Base directory for flats for this camera."""
    return FLAT_DIR / (camera_name or "default")


def pixelmaps_dir(camera_name):
    """Base directory for pixel maps (TIFF review images) for this camera."""
    return PIXELMAPS_DIR / (camera_name or "default")


def dark_path(integration_time_seconds: float, gain: int, width: int, height: int, camera_name) -> pathlib.Path:
    """Path for a specific dark file: darks/<camera>/dark_{time}_{gain}_{width}x{height}.npy"""
    return dark_dir(camera_name) / f"dark_{integration_time_seconds}_{gain}_{width}x{height}.npy"


def flat_path(integration_time_seconds: float, gain: int, width: int, height: int, camera_name) -> pathlib.Path:
    """Path for a specific flat file: flats/<camera>/flat_{time}_{gain}_{width}x{height}.npy"""
    return flat_dir(camera_name) / f"flat_{integration_time_seconds}_{gain}_{width}x{height}.npy"


# Filename patterns: with resolution dark_1.5_100_1920x1080.npy; legacy dark_1.5_100.npy, dark_1.5.npy
_DARK_FNAME_RE = re.compile(r"^dark_([\d.]+)_(\d+)_(\d+)x(\d+)\.npy$")
_DARK_LEGACY_RE = re.compile(r"^dark_([\d.]+)_(\d+)\.npy$")
_DARK_LEGACY_T_RE = re.compile(r"^dark_([\d.]+)\.npy$")
_FLAT_FNAME_RE = re.compile(r"^flat_([\d.]+)_(\d+)_(\d+)x(\d+)\.npy$")
_FLAT_LEGACY_RE = re.compile(r"^flat_([\d.]+)_(\d+)\.npy$")
_FLAT_LEGACY_T_RE = re.compile(r"^flat_([\d.]+)\.npy$")


def distance_time_gain(t1: float, g1: int, t2: float, g2: int) -> float:
    """Distance for nearest-match: time diff (s) + gain diff/100."""
    return abs(t1 - t2) + abs(g1 - g2) / 100.0


def find_nearest_dark(camera_name, time_seconds: float, gain: int, width: int, height: int):
    """Return (path, distance, (t, g)) for nearest dark matching resolution, or (None, inf, None)."""
    def scan_dir(base_path):
        candidates = []
        if not base_path.exists():
            return candidates
        for p in base_path.glob("dark_*.npy"):
            m = _DARK_FNAME_RE.match(p.name)
            if m:
                tw, gw, w, h = float(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                if width > 0 and height > 0 and (w != width or h != height):
                    continue
                candidates.append((p, (tw, gw)))
            else:
                m = _DARK_LEGACY_RE.match(p.name)
                if m:
                    t, g = float(m.group(1)), int(m.group(2))
                    candidates.append((p, (t, g)))
                else:
                    m = _DARK_LEGACY_T_RE.match(p.name)
                    if m:
                        candidates.append((p, (float(m.group(1)), 0)))
        return candidates
    all_c = scan_dir(dark_dir(camera_name)) + scan_dir(DARK_DIR)
    best_path, best_dist, best_tg = None, math.inf, None
    for p, (t, g) in all_c:
        d = distance_time_gain(time_seconds, gain, t, g)
        if d < best_dist:
            best_dist, best_path, best_tg = d, p, (t, g)
    return best_path, best_dist, best_tg


def find_nearest_flat(camera_name, time_seconds: float, gain: int, width: int, height: int):
    """Return (path, distance, (t, g)) for nearest flat matching resolution, or (None, inf, None)."""
    def scan_dir(base_path):
        candidates = []
        if not base_path.exists():
            return candidates
        for p in base_path.glob("flat_*.npy"):
            m = _FLAT_FNAME_RE.match(p.name)
            if m:
                tw, gw, w, h = float(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                if width > 0 and height > 0 and (w != width or h != height):
                    continue
                candidates.append((p, (tw, gw)))
            else:
                m = _FLAT_LEGACY_RE.match(p.name)
                if m:
                    t, g = float(m.group(1)), int(m.group(2))
                    candidates.append((p, (t, g)))
                else:
                    m = _FLAT_LEGACY_T_RE.match(p.name)
                    if m:
                        candidates.append((p, (float(m.group(1)), 0)))
        return candidates
    all_c = scan_dir(flat_dir(camera_name)) + scan_dir(FLAT_DIR)
    best_path, best_dist, best_tg = None, math.inf, None
    for p, (t, g) in all_c:
        d = distance_time_gain(time_seconds, gain, t, g)
        if d < best_dist:
            best_dist, best_path, best_tg = d, p, (t, g)
    return best_path, best_dist, best_tg
