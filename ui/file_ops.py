"""
File operations: open/save dialogs, default path and TIFF filename, load image, export PNG/TIFF.
All functions take the GUI instance. Used by gui.py; callbacks stay registered on gui.
"""
from __future__ import annotations

import os
import pathlib
import numpy as np
import dearpygui.dearpygui as dpg

from ui.constants import (
    CAPTURES_DIR,
    DEFAULT_FRAME_W,
    DEFAULT_FRAME_H,
    FULL_SCALE_12BIT,
    FULL_SCALE_14BIT,
    FULL_SCALE_16BIT,
)


def _detect_effective_bit_depth_and_restretch(arr: np.ndarray, gui) -> tuple[np.ndarray, int]:
    """
    Detect effective bit depth from the data range and put the image in that standard
    range (12/14/16-bit) so darks and flats match. Uses the same logic as a live sensor:
    - If the data already fits in the chosen range (e.g. values in [0, 4095]), pass
      through with only clipping — no contrast stretch, same numeric scale as sensor.
    - If the data is in a different scale (e.g. 16-bit file 0–65535 with only 12-bit
      content), scale linearly into the chosen range so pipeline and darks/flats align.
    Uses high percentile for max to ignore hot pixels when choosing bit depth.
    Returns (float32_array_in_standard_range, effective_bits).
    """
    finite = np.isfinite(arr)
    if not np.any(finite):
        return arr, 16
    data_min = float(np.min(arr[finite]))
    data_max = float(np.max(arr[finite]))
    hi_robust = float(np.percentile(arr[finite], 99.5))  # ignore hot pixels for bit-depth choice
    if hi_robust <= FULL_SCALE_12BIT:
        full_scale = FULL_SCALE_12BIT
        effective_bits = 12
    elif hi_robust <= FULL_SCALE_14BIT:
        full_scale = FULL_SCALE_14BIT
        effective_bits = 14
    else:
        full_scale = FULL_SCALE_16BIT
        effective_bits = 16
    # Same logic as sensor: if data already fits in [0, full_scale], no stretch — just clip
    if data_min >= 0.0 and data_max <= full_scale:
        out = np.clip(arr, 0.0, full_scale).astype(np.float32)
        return out, effective_bits
    # Data in different scale (e.g. normalized 0–65535): map [min, max] -> [0, full_scale]
    lo = float(np.percentile(arr[finite], 0.5))
    hi = float(np.percentile(arr[finite], 99.5))
    if hi <= lo:
        hi = lo + 1.0
    out = (arr - lo) / (hi - lo) * full_scale
    out = np.clip(out, 0.0, full_scale).astype(np.float32)
    return out, effective_bits


def get_file_dialog_default_path(gui) -> str:
    """Directory to open file dialogs in; defaults to app/captures if none saved or invalid."""
    p = pathlib.Path(getattr(gui, "_last_file_dialog_dir", "") or str(CAPTURES_DIR))
    if not p.is_dir():
        p = CAPTURES_DIR
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def get_default_tiff_filename(gui) -> str:
    """Default TIFF save name: dd-mm-YYYY-{exposuretime}-{gain}-{integration count}.tif"""
    from datetime import datetime
    date_str = datetime.now().strftime("%d-%m-%Y")
    integ_time = gui._parse_integration_time(dpg.get_value("integ_time_combo")) if dpg.does_item_exist("integ_time_combo") else gui.integration_time
    gain = gui._get_camera_gain()
    n = int(dpg.get_value("integ_n_slider")) if dpg.does_item_exist("integ_n_slider") else gui.integration_n
    return f"{date_str}-{integ_time}-{gain}-{n}.tif"


def load_image_file_as_float32(gui, path: str) -> np.ndarray:
    """
    Load TIFF or PNG as 2D float32, resized to current frame size.
    Detects effective bit depth from the data range and restretches to the closest
    standard range (12/14/16-bit) so darks and flats match after save/reload.
    Sets gui._last_opened_image_effective_bits. Raises on error.
    """
    try:
        import tifffile
        arr = tifffile.imread(path)
    except Exception:
        from PIL import Image
        arr = np.array(Image.open(path))
    if arr is None or arr.size == 0:
        raise ValueError("Empty or invalid image")
    if arr.ndim == 3:
        arr = arr[:, :, 0] if arr.shape[2] >= 1 else arr.squeeze()
    if arr.ndim != 2:
        arr = arr.squeeze()
    arr = np.asarray(arr, dtype=np.float32)
    h = getattr(gui, "frame_height", DEFAULT_FRAME_H)
    w = getattr(gui, "frame_width", DEFAULT_FRAME_W)
    if arr.shape[0] != h or arr.shape[1] != w:
        try:
            from skimage.transform import resize
            arr = resize(arr, (h, w), order=1, preserve_range=True).astype(np.float32)
        except Exception:
            from scipy.ndimage import zoom
            zoom_h = h / arr.shape[0]
            zoom_w = w / arr.shape[1]
            arr = zoom(arr, (zoom_h, zoom_w), order=1)[:h, :w].astype(np.float32)
    arr, effective_bits = _detect_effective_bit_depth_and_restretch(arr, gui)
    gui._last_opened_image_effective_bits = effective_bits
    return arr


def cb_export_png(gui):
    """Show PNG export file dialog (menu or File section)."""
    if gui._get_export_frame() is None:
        gui._status_msg = "No frame to export"
        return
    dpg.configure_item("file_dialog", default_path=get_file_dialog_default_path(gui))
    dpg.show_item("file_dialog")


def cb_save_tiff(gui):
    """Show TIFF save file dialog (menu)."""
    if gui._get_export_frame() is None:
        gui._status_msg = "No frame to save"
        return
    dpg.configure_item("tiff_file_dialog", default_path=get_file_dialog_default_path(gui), default_filename=get_default_tiff_filename(gui))
    dpg.show_item("tiff_file_dialog")


def cb_file_open_image(gui):
    """Show Open image file dialog."""
    dpg.configure_item("open_image_file_dialog", default_path=get_file_dialog_default_path(gui))
    dpg.show_item("open_image_file_dialog")


def cb_open_image_file_selected(gui, sender, app_data):
    """Handle file selected from Open image dialog: load, set preview, update last dir."""
    if not app_data:
        return
    path = app_data.get("file_path_name", "")
    if isinstance(path, (list, tuple)):
        path = path[0] if path else ""
    if not path:
        return
    try:
        frame = load_image_file_as_float32(gui, path)
        gui._file_preview_frame = frame
        gui._paint_preview_to_main_view(frame, use_histogram=True)
        bits = getattr(gui, "_last_opened_image_effective_bits", None)
        gui._status_msg = f"Opened: {os.path.basename(path)} ({bits}-bit range)" if bits else f"Opened: {os.path.basename(path)}"
        # So 14/16-bit opened images get full range: allow Min/Max controls up to display max
        if bits and dpg.does_item_exist("win_max_drag"):
            disp_max = gui._get_display_max_value()
            dpg.configure_item("win_min_drag", max_value=disp_max)
            dpg.configure_item("win_max_drag", max_value=disp_max)
        dir_path = os.path.dirname(path)
        if dir_path and pathlib.Path(dir_path).is_dir():
            gui._last_file_dialog_dir = dir_path
            gui._save_settings()
    except Exception as e:
        gui._status_msg = f"Open failed: {e}"
        gui._file_preview_frame = None


def cb_file_run_through_processing(gui):
    """Run the current file preview frame through the pipeline and repaint."""
    if gui._file_preview_frame is None:
        gui._status_msg = "Open an image first"
        return
    frame = gui._file_preview_frame
    gui._clear_main_view_preview()
    gui.clear_frame_buffer()
    gui._push_frame(frame)
    gui._file_preview_frame = None
    with gui.frame_lock:
        if gui.display_frame is not None:
            gui._paint_texture_from_frame(gui.display_frame.copy())
    gui._status_msg = "Processed; you can Save TIF"


def cb_file_save_tiff(gui):
    """Show TIFF save file dialog (File section)."""
    if gui._get_export_frame() is None:
        gui._status_msg = "No frame to save (run an image through processing first)"
        return
    dpg.configure_item("tiff_file_dialog", default_path=get_file_dialog_default_path(gui), default_filename=get_default_tiff_filename(gui))
    dpg.show_item("tiff_file_dialog")


def cb_tiff_file_selected(gui, sender, app_data):
    """Handle file selected from TIFF save dialog: save 16-bit TIFF, update last dir."""
    filepath = app_data.get("file_path_name", "")
    if not filepath:
        return
    if not filepath.lower().endswith((".tif", ".tiff")):
        filepath += ".tif"
    dir_path = os.path.dirname(filepath)
    if dir_path and pathlib.Path(dir_path).is_dir():
        gui._last_file_dialog_dir = dir_path
        gui._save_settings()
    frame = gui._get_export_frame()
    if frame is None:
        gui._status_msg = "No frame to save"
        return
    frame = frame.copy().astype(np.float32)
    finite = np.isfinite(frame)
    if not np.any(finite):
        gui._status_msg = "TIFF save failed: frame has no finite values"
        return
    lo = float(np.min(frame[finite]))
    hi = float(np.max(frame[finite]))
    if hi <= lo:
        arr16 = np.zeros(frame.shape, dtype=np.uint16)
    else:
        safe = np.nan_to_num(frame, nan=lo, posinf=hi, neginf=lo)
        scaled = (safe - lo) / (hi - lo)
        arr16 = np.clip(np.rint(scaled * 65535.0), 0.0, 65535.0).astype(np.uint16)
    try:
        try:
            import tifffile
            tifffile.imwrite(filepath, arr16, photometric="minisblack", compression=None)
        except ImportError:
            from PIL import Image
            img = Image.fromarray(arr16, mode="I;16")
            img.save(filepath, compression=None)
            gui._status_msg = f"Saved TIFF (16-bit normalized, min={lo:.3f}, max={hi:.3f}): {filepath}"
            return
        gui._status_msg = f"Saved TIFF (16-bit normalized, min={lo:.3f}, max={hi:.3f}): {filepath}"
    except Exception as e:
        gui._status_msg = f"TIFF save failed: {e}"


def cb_file_selected(gui, sender, app_data):
    """Handle file selected from PNG export dialog: save 8-bit PNG with current windowing, update last dir."""
    filepath = app_data.get("file_path_name", "")
    if not filepath:
        return
    if not filepath.lower().endswith(".png"):
        filepath += ".png"
    dir_path = os.path.dirname(filepath)
    if dir_path and pathlib.Path(dir_path).is_dir():
        gui._last_file_dialog_dir = dir_path
        gui._save_settings()
    frame = gui._get_export_frame()
    if frame is None:
        gui._status_msg = "No frame to export"
        return
    frame = frame.copy()
    lo, hi = gui.win_min, gui.win_max
    if hi <= lo:
        hi = lo + 1
    normed = np.clip((frame - lo) / (hi - lo), 0, 1)
    img8 = (normed * 255).astype(np.uint8)
    try:
        from PIL import Image
        Image.fromarray(img8, mode='L').save(filepath)
        gui._status_msg = f"Exported: {filepath}"
    except Exception as e:
        gui._status_msg = f"Export failed: {e}"
