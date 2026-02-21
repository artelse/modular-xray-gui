"""
Autocrop alteration module.
Crops the image to a rectangle (x_start, x_end, y_start, y_end). Applied at the end of the
alteration pipeline (slot 500) so it only affects the final view. Uses 0,0,0,0 as "no crop".
"""

MODULE_INFO = {
    "display_name": "Autocrop",
    "description": "Crop image to a rectangle (x/y start and end). Applies on next startup.",
    "type": "alteration",
    "default_enabled": True,
    "pipeline_slot": 500,
}
MODULE_NAME = "autocrop"


def get_setting_keys():
    return ["crop_x_start", "crop_x_end", "crop_y_start", "crop_y_end"]


# Spec for api.get_module_settings_for_save: (key, tag, converter, default)
_AUTOCROP_SAVE_SPEC = [
    ("crop_x_start", "crop_x_start", int, 0),
    ("crop_x_end", "crop_x_end", int, 0),
    ("crop_y_start", "crop_y_start", int, 0),
    ("crop_y_end", "crop_y_end", int, 0),
]


def get_default_settings():
    """Return default settings for this module (extracted from save spec)."""
    return {key: default for key, _tag, _conv, default in _AUTOCROP_SAVE_SPEC}


def get_settings_for_save(gui=None):
    """Return crop coordinates from UI or loaded settings (auto fallback when UI not built)."""
    if gui is None or not getattr(gui, "api", None):
        return {}
    return gui.api.get_module_settings_for_save(_AUTOCROP_SAVE_SPEC)


def process_frame(frame, gui):
    """
    Pure per-frame pipeline step.
    Input/output manual helpers are not needed here because this module has no manual apply/revert actions.
    """
    import numpy as np
    api = gui.api
    frame = api.incoming_frame(MODULE_NAME, frame)
    h, w = frame.shape[0], frame.shape[1]
    x_start, y_start, x_end, y_end = api.get_crop_region()
    if x_end <= x_start or y_end <= y_start:
        return api.outgoing_frame(MODULE_NAME, frame)
    x_start = max(0, min(x_start, w - 1))
    x_end = max(x_start + 1, min(x_end, w))
    y_start = max(0, min(y_start, h - 1))
    y_end = max(y_start + 1, min(y_end, h))
    out = np.ascontiguousarray(frame[y_start:y_end, x_start:x_end])
    return api.outgoing_frame(MODULE_NAME, out)


def build_ui(gui, parent_tag: str = "control_panel") -> None:
    """Build Autocrop collapsing header; callbacks live in this module (no gui.py changes)."""
    import dearpygui.dearpygui as dpg

    api = gui.api

    def _apply_crop(sender=None, app_data=None):
        gui.crop_x_start = int(dpg.get_value("crop_x_start"))
        gui.crop_x_end = int(dpg.get_value("crop_x_end"))
        gui.crop_y_start = int(dpg.get_value("crop_y_start"))
        gui.crop_y_end = int(dpg.get_value("crop_y_end"))
        api.save_settings()
        getattr(gui, "_refresh_distortion_preview", lambda: None)()

    loaded = api.get_loaded_settings()
    x_start = int(loaded.get("crop_x_start", 0))
    x_end = int(loaded.get("crop_x_end", 0))
    y_start = int(loaded.get("crop_y_start", 0))
    y_end = int(loaded.get("crop_y_end", 0))
    # Persist on gui so process_frame can read them
    gui.crop_x_start = x_start
    gui.crop_x_end = x_end
    gui.crop_y_start = y_start
    gui.crop_y_end = y_end

    with dpg.collapsing_header(parent=parent_tag, label="Autocrop", default_open=False):
        with dpg.group(indent=10):
            dpg.add_input_int(
                label="X start", default_value=x_start, tag="crop_x_start",
                min_value=0, min_clamped=True, width=80, callback=_apply_crop
            )
            dpg.add_input_int(
                label="X end", default_value=x_end, tag="crop_x_end",
                min_value=0, min_clamped=True, width=80, callback=_apply_crop
            )
            dpg.add_input_int(
                label="Y start", default_value=y_start, tag="crop_y_start",
                min_value=0, min_clamped=True, width=80, callback=_apply_crop
            )
            dpg.add_input_int(
                label="Y end", default_value=y_end, tag="crop_y_end",
                min_value=0, min_clamped=True, width=80, callback=_apply_crop
            )
            dpg.add_text("0,0,0,0 = no crop. Applied at end of pipeline (view only).", color=[150, 150, 150])
