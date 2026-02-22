"""
Display: texture conversion, histogram, painting, preview, windowing. All functions take the GUI instance.
Used by gui.py. Uses dpg for texture/histogram updates.
"""

import numpy as np
import dearpygui.dearpygui as dpg


def histogram_equalize(img):
    """Histogram equalization; static helper (no gui)."""
    flat = img.flatten()
    lo, hi = float(flat.min()), float(flat.max())
    if hi <= lo:
        return np.zeros_like(img)
    nbins = 4096
    hist, _ = np.histogram(flat, bins=nbins, range=(lo, hi))
    cdf = hist.cumsum().astype(np.float64)
    cdf_max = cdf[-1]
    if cdf_max == 0:
        return np.zeros_like(img)
    cdf_norm = cdf / cdf_max
    indices = np.clip(((img - lo) / (hi - lo) * (nbins - 1)), 0, nbins - 1).astype(np.int32)
    return cdf_norm[indices].astype(np.float32)


def frame_to_texture(gui, frame):
    """Apply windowing and convert to RGBA float32 for DPG texture. Returns (data, disp_w, disp_h)."""
    if gui.hist_eq:
        norm = histogram_equalize(frame)
    else:
        lo, hi = gui.win_min, gui.win_max
        if hi <= lo:
            hi = lo + 1
        norm = (frame - lo) / (hi - lo)
    norm = np.clip(norm, 0.0, 1.0).astype(np.float32)
    disp_h = frame.shape[0] // gui.disp_scale
    disp_w = frame.shape[1] // gui.disp_scale
    if gui.disp_scale > 1:
        norm = norm.reshape(disp_h, gui.disp_scale, disp_w, gui.disp_scale).mean(axis=(1, 3))
    rgba = np.empty((disp_h, disp_w, 4), dtype=np.float32)
    rgba[:, :, 0] = norm
    rgba[:, :, 1] = norm
    rgba[:, :, 2] = norm
    rgba[:, :, 3] = 1.0
    return rgba.ravel(), disp_w, disp_h


def scale_frame_to_fit(gui, frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Scale frame to fit inside target_w x target_h (preserve aspect, letterbox). Return float32 (target_h, target_w) in 0–1."""
    if target_w <= 0 or target_h <= 0:
        return np.zeros((target_h, target_w), dtype=np.float32)
    arr = np.asarray(frame, dtype=np.float32)
    h, w = arr.shape[0], arr.shape[1]
    if h <= 0 or w <= 0:
        return np.zeros((target_h, target_w), dtype=np.float32)
    scale = min(target_w / w, target_h / h)
    out_w = max(1, int(round(w * scale)))
    out_h = max(1, int(round(h * scale)))
    yi = np.linspace(0, h - 1, out_h).astype(np.int32)
    xi = np.linspace(0, w - 1, out_w).astype(np.int32)
    small = arr[np.ix_(yi, xi)]
    canvas = np.zeros((target_h, target_w), dtype=np.float32)
    y0 = (target_h - out_h) // 2
    x0 = (target_w - out_w) // 2
    canvas[y0:y0 + out_h, x0:x0 + out_w] = small
    lo, hi = float(np.min(canvas)), float(np.max(canvas))
    if hi > lo:
        canvas = (canvas - lo) / (hi - lo)
    else:
        canvas[:] = 0.5
    return np.clip(canvas, 0.0, 1.0).astype(np.float32)


def get_display_max_value(gui) -> float:
    """
    Max display/windowing value: camera bit depth (12/14/16) or opened-image effective
    bits, whichever is larger. Ensures 14-bit (and 16-bit) opened images get full
    range in Min/Max and histogram even when the selected detector is 12-bit.
    """
    camera_max = gui.api.get_display_max_value()
    bits = getattr(gui, "_last_opened_image_effective_bits", None)
    if bits in (12, 14, 16):
        image_max = float((1 << bits) - 1)  # 4095, 16383, 65535
        return max(camera_max, image_max)
    return camera_max


def clamp_window_bounds(gui, lo: float, hi: float):
    dmin, dmax = 0.0, get_display_max_value(gui)
    lo = float(max(dmin, min(lo, dmax)))
    hi = float(max(dmin, min(hi, dmax)))
    if hi <= lo:
        hi = min(dmax, lo + 1.0)
        if hi <= lo:
            lo = max(dmin, hi - 1.0)
    return lo, hi


def get_histogram_analysis_pixels(gui, frame: np.ndarray) -> np.ndarray:
    """Pixels used for histogram/auto-window stats."""
    flat = np.asarray(frame, dtype=np.float32).reshape(-1)
    flat = flat[np.isfinite(flat)]
    if flat.size == 0:
        return flat
    use_bgsep_mask = bool(getattr(gui, "_bgsep_hist_ignore", True)) and bool(
        getattr(gui, "_bgsep_hist_active", False)
    )
    cutoff = getattr(gui, "_bgsep_hist_cutoff", None)
    if use_bgsep_mask and cutoff is not None and np.isfinite(float(cutoff)):
        masked = flat[flat < float(cutoff)]
        if masked.size >= max(128, int(0.01 * flat.size)):
            return masked
    return flat


def paint_preview_raw(gui) -> None:
    """Paint _preview_frame to main view with scale-to-fit and frame's own min/max (no histogram/windowing)."""
    if gui._preview_frame is None or gui._preview_frame.size == 0 or gui._texture_id is None:
        return
    disp_w = getattr(gui, "_disp_w", 0)
    disp_h = getattr(gui, "_disp_h", 0)
    if disp_w <= 0 or disp_h <= 0:
        return
    scaled = scale_frame_to_fit(gui, gui._preview_frame, disp_w, disp_h)
    rgba = np.empty((disp_h, disp_w, 4), dtype=np.float32)
    rgba[:, :, 0] = scaled
    rgba[:, :, 1] = scaled
    rgba[:, :, 2] = scaled
    rgba[:, :, 3] = 1.0
    dpg.set_value(gui._texture_id, rgba.ravel().tolist())
    gui._force_image_refresh()


def paint_preview_to_main_view(gui, frame: np.ndarray, use_histogram: bool = True) -> None:
    """Paint a frame to the main view. use_histogram=True: windowing/hist eq; False: raw. Sets preview mode until clear."""
    if frame is None or frame.size == 0 or gui._texture_id is None:
        return
    gui._main_view_preview_active = True
    gui._preview_frame = np.asarray(frame, dtype=np.float32).copy()
    gui._preview_use_histogram = use_histogram
    if use_histogram:
        paint_texture_from_frame(gui, gui._preview_frame)
    else:
        paint_preview_raw(gui)
    gui._force_image_refresh()


def clear_main_view_preview(gui) -> None:
    """Leave preview mode and repaint the normal display (live/raw/deconvolved)."""
    gui._main_view_preview_active = False
    gui._preview_frame = None
    gui._preview_use_histogram = True
    refresh_texture_from_settings(gui)
    gui._force_image_refresh()


def paint_texture_from_frame(gui, frame: np.ndarray):
    """Update texture and histogram from a given frame. Recreates texture when frame size changes (e.g. after crop)."""
    texture_data, disp_w, disp_h = frame_to_texture(gui, frame)
    if (disp_w, disp_h) != (gui._disp_w, gui._disp_h):
        with dpg.texture_registry():
            new_id = dpg.add_dynamic_texture(width=disp_w, height=disp_h, default_value=texture_data)
        dpg.configure_item("main_image", texture_tag=new_id)
        dpg.delete_item(gui._texture_id)
        gui._texture_id = new_id
        gui._disp_w, gui._disp_h = disp_w, disp_h
        if gui.image_viewport is not None:
            gui.image_viewport.aspect_ratio = disp_w / disp_h if disp_h else 1.0
    else:
        dpg.set_value(gui._texture_id, texture_data)
    flat = get_histogram_analysis_pixels(gui, frame)
    frame_lo, frame_hi = float(flat.min()), float(flat.max())
    if not (np.isfinite(frame_lo) and np.isfinite(frame_hi)) or frame_hi <= frame_lo:
        frame_lo, frame_hi = 0.0, get_display_max_value(gui)
    frame_lo, frame_hi = clamp_window_bounds(gui, frame_lo, frame_hi)
    axis_lo = min(frame_lo, float(gui.win_min))
    axis_hi = max(frame_hi, float(gui.win_max))
    axis_lo, axis_hi = clamp_window_bounds(gui, axis_lo, axis_hi)
    hist_vals, hist_edges = np.histogram(flat, bins=256, range=(axis_lo, axis_hi))
    peak = hist_vals.max()
    if peak > 0:
        hist_norm = (hist_vals / peak).tolist()
    else:
        hist_norm = [0.0] * len(hist_vals)
    hist_centers = (hist_edges[:-1] + hist_edges[1:]) / 2
    zeros = [0] * len(hist_centers)
    dpg.set_value("hist_series", [hist_centers.tolist(), hist_norm, zeros])
    dpg.set_axis_limits_constraints("hist_x", axis_lo, axis_hi)
    dpg.set_axis_limits("hist_x", axis_lo, axis_hi)
    if getattr(gui, "_hist_zoom_lo", None) is not None and getattr(gui, "_hist_zoom_hi", None) is not None:
        zoom_lo = max(axis_lo, gui._hist_zoom_lo)
        zoom_hi = min(axis_hi, gui._hist_zoom_hi)
        if zoom_hi - zoom_lo >= 50 and zoom_lo < zoom_hi:
            dpg.set_axis_limits("hist_x", zoom_lo, zoom_hi)
        else:
            gui._hist_zoom_lo = None
            gui._hist_zoom_hi = None
            dpg.set_axis_limits("hist_x", axis_lo, axis_hi)
    else:
        dpg.set_axis_limits("hist_x", axis_lo, axis_hi)
    dpg.set_axis_limits("hist_y", 0.0, 1.05)


def update_display(gui):
    """Called from main thread when new_frame_ready is set. Only updates texture when showing live."""
    if gui._main_view_preview_active:
        return
    if gui._display_mode != "live":
        return
    with gui.frame_lock:
        if gui.display_frame is None:
            return
        frame = gui.display_frame.copy()
    paint_texture_from_frame(gui, frame)


def refresh_distortion_preview(gui):
    """Re-run distortion+crop steps on the last pre-distortion frame and repaint (live preview when adjusting sliders)."""
    if gui._display_mode != "live":
        return
    with gui.frame_lock:
        if gui._frame_before_distortion is None:
            return
        frame = gui._frame_before_distortion.copy()
    token = int(getattr(gui, "_pipeline_frame_token", 0))
    for _slot, _name, step in getattr(gui, "_distortion_crop_pipeline", []):
        frame_in = frame
        try:
            frame = step(frame, gui)
        except Exception as e:
            print(
                f"[Pipeline][preview] token={token} slot={_slot} module={_name} "
                f"step-error={e}",
                flush=True,
            )
            raise
        gui._log_pipeline_step("preview", token, _slot, _name, frame_in, frame)
    paint_texture_from_frame(gui, frame)


def refresh_texture_from_settings(gui):
    """Re-render current view with new windowing settings (live, raw, deconvolved, or preview)."""
    if gui._main_view_preview_active and gui._preview_frame is not None:
        if getattr(gui, "_preview_use_histogram", True):
            paint_texture_from_frame(gui, gui._preview_frame.copy())
        else:
            paint_preview_raw(gui)
        return
    if gui._display_mode == "live":
        with gui.frame_lock:
            if gui.display_frame is None:
                return
            frame = gui.display_frame.copy()
    elif gui._display_mode == "raw" and gui._deconv_raw_frame is not None:
        frame = gui._deconv_raw_frame.copy()
    elif gui._display_mode == "deconvolved" and gui._deconv_result is not None:
        frame = gui._deconv_result.copy()
    else:
        return
    paint_texture_from_frame(gui, frame)
