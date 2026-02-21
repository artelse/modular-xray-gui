"""
Flat correction image alteration module.
Divides frame by the loaded flat field (with dark removed if available) to correct vignetting/sensitivity.
Runs at pipeline slot 200 (after dark). Flat data and load/save remain in the main app.
"""

import numpy as np

MODULE_INFO = {
    "display_name": "Flat correction",
    "description": "Divide by flat field for vignetting correction. Applies on next startup.",
    "type": "alteration",
    "default_enabled": True,
    "pipeline_slot": 200,
}
MODULE_NAME = "flat_correction"


def get_setting_keys():
    return []


def get_default_settings():
    """Return default settings for this module."""
    return {
        "flat_stack_n": 20,
    }


def get_settings_for_save(gui=None):
    """Return flat_stack_n from our UI or from gui state when module is disabled."""
    import dearpygui.dearpygui as dpg
    if dpg.does_item_exist("flat_stack_slider"):
        return {"flat_stack_n": int(dpg.get_value("flat_stack_slider"))}
    if gui is not None:
        return {"flat_stack_n": gui.api.get_flat_capture_stack_count()}
    return {}


def process_frame(frame: np.ndarray, gui) -> np.ndarray:
    """
    Divide frame by flat field (normalized). The stored flat is always captured with dark
    correction applied (pipeline slot < 200), so it is already in dark-subtracted space.
    The incoming frame is also already dark-subtracted. Use flat as-is for normalization.
    Avoids divide-by-zero and clips to a display-safe range.
    """
    api = gui.api
    frame = api.incoming_frame(MODULE_NAME, frame)
    flat = api.get_flat_field()
    if flat is None or flat.shape != frame.shape:
        return api.outgoing_frame(MODULE_NAME, frame)
    frame = np.asarray(frame, dtype=np.float32)
    flat = np.asarray(flat, dtype=np.float32)
    mean_flat = float(np.mean(flat))
    if not np.isfinite(mean_flat) or mean_flat <= 0:
        mean_flat = 1e-10
    divisor = flat / mean_flat
    divisor = np.where(divisor > 1e-10, divisor, 1e-10)
    out = frame / divisor
    # Clip to a sensible range for display (e.g. 0–2× mean object intensity; 1e4 covers 12–16 bit)
    out = np.clip(np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0), 0.0, 1e4).astype(np.float32)
    return api.outgoing_frame(MODULE_NAME, out)


def capture_flat(gui) -> bool:
    """
    Capture a flat reference: request N frames with pipeline run only up to this module's slot (exclusive),
    so dark (and any earlier steps) are applied; then average, set flat field, save.
    Called by the app when the user clicks Capture Flat. Returns True if capture succeeded.
    """
    api = gui.api
    if not api.is_camera_connected():
        api.set_status_message("Not connected")
        return False
    n = api.get_flat_capture_stack_count()
    t_int = api.get_integration_time_seconds()
    # Timeout: nr_frames * frametime + nr_frames * 5 seconds
    timeout_s = n * t_int + n * 5.0
    api.set_progress(0.0, f"Capturing flat ({n} frames)... Click Stop to cancel.")
    avg = api.request_n_frames_processed_up_to_slot(
        n, max_slot=MODULE_INFO["pipeline_slot"], timeout_seconds=timeout_s, dark_capture=False
    )
    if avg is None:
        api.set_status_message("Flat capture failed (timeout or stopped). Try fewer frames or shorter integration.")
        return False
    api.set_flat_field(avg)
    api.save_flat_field()
    api.set_progress(1.0)
    api.set_status_message(f"Master flat saved ({n} frames avg, {api.get_integration_time_seconds()}s)")
    return True


def build_ui(gui, parent_tag: str = "control_panel") -> None:
    """Optional: show flat correction status. Capture/Clear are triggered by main app."""
    import dearpygui.dearpygui as dpg
    api = gui.api
    with dpg.collapsing_header(parent=parent_tag, label="Flat correction", default_open=False):
        with dpg.group(indent=10):
            def _status():
                flat = api.get_flat_field()
                if flat is not None:
                    return f"Active ({flat.shape[1]}×{flat.shape[0]})"
                return "No flat loaded"
            dpg.add_text("Divides by flat field when loaded.", color=[150, 150, 150])
            dpg.add_text(_status(), tag="flat_correction_status")
