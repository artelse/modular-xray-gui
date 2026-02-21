"""
Pincushion distortion correction alteration module.
Applies radial distortion correction (pincushion). Center X/Y are saved settings; if not set (< 0) uses frame center. Runs at slot 450.
"""

import numpy as np

MODULE_INFO = {
    "display_name": "Pincushion correction",
    "description": "Correct pincushion distortion. Set center X/Y or leave default for frame center. Applies on next startup.",
    "type": "alteration",
    "default_enabled": False,
    "pipeline_slot": 450,
}
MODULE_NAME = "pincushion"


def get_setting_keys():
    return ["pincushion_strength", "pincushion_center_x", "pincushion_center_y"]


# Spec for api.get_module_settings_for_save: (key, tag, converter, default)
_PINCUSHION_SAVE_SPEC = [
    ("pincushion_strength", "pincushion_strength", float, 0.0),
    ("pincushion_center_x", "pincushion_center_x", float, -1.0),
    ("pincushion_center_y", "pincushion_center_y", float, -1.0),
]


def get_default_settings():
    """Return default settings for this module (extracted from save spec)."""
    return {key: default for key, _tag, _conv, default in _PINCUSHION_SAVE_SPEC}


def get_settings_for_save(gui=None):
    """Return pincushion strength and center from UI or loaded settings (auto fallback when UI not built)."""
    if gui is None or not getattr(gui, "api", None):
        return {}
    return gui.api.get_module_settings_for_save(_PINCUSHION_SAVE_SPEC)


def process_frame(frame, gui):
    """Apply pincushion correction: sample from r_src = r / (1 + k*r_norm^2). Center from saved X/Y or frame center."""
    from scipy.ndimage import map_coordinates

    api = gui.api
    frame = api.incoming_frame(MODULE_NAME, frame)
    h, w = frame.shape[0], frame.shape[1]
    k, cx, cy = api.get_pincushion_params()
    k = float(k)
    if abs(k) < 1e-9:
        return api.outgoing_frame(MODULE_NAME, frame)

    cx, cy = float(cx), float(cy)
    if cx < 0 or cy < 0:
        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0
    # Max radius from center to corner (normalize so strength is scale-invariant)
    r_max = np.sqrt(max(cx, w - 1 - cx) ** 2 + max(cy, h - 1 - cy) ** 2)
    if r_max < 1e-6:
        return api.outgoing_frame(MODULE_NAME, frame)

    rows = np.arange(h, dtype=np.float64)
    cols = np.arange(w, dtype=np.float64)
    col_grid, row_grid = np.meshgrid(cols, rows)
    dx = col_grid - cx
    dy = row_grid - cy
    r = np.sqrt(dx * dx + dy * dy)
    # Where r is tiny, no remap
    r_safe = np.where(r < 1e-6, 1.0, r)
    r_norm = r_safe / r_max
    # r_src = r / (1 + k * r_norm^2) -> sample from closer to center (pincushion correction)
    r_src = r_safe / (1.0 + k * (r_norm * r_norm))
    scale = np.where(r < 1e-6, 1.0, r_src / r_safe)
    src_col = cx + scale * dx
    src_row = cy + scale * dy
    coords = np.stack([src_row, src_col], axis=0)
    out = map_coordinates(frame, coords, order=1, mode="reflect", cval=0.0)
    out = np.ascontiguousarray(out.astype(frame.dtype))
    return api.outgoing_frame(MODULE_NAME, out)


def build_ui(gui, parent_tag: str = "control_panel") -> None:
    """Build Pincushion collapsing header; callbacks in module. Center X/Y saved; -1 = use frame center."""
    import dearpygui.dearpygui as dpg

    api = gui.api

    def _apply(sender=None, app_data=None):
        gui.pincushion_strength = float(dpg.get_value("pincushion_strength"))
        gui.pincushion_center_x = float(dpg.get_value("pincushion_center_x"))
        gui.pincushion_center_y = float(dpg.get_value("pincushion_center_y"))
        api.save_settings()
        getattr(gui, "_refresh_distortion_preview", lambda: None)()

    loaded = api.get_loaded_settings()
    strength = float(loaded.get("pincushion_strength", 0.0))
    center_x = float(loaded.get("pincushion_center_x", -1.0))
    center_y = float(loaded.get("pincushion_center_y", -1.0))
    gui.pincushion_strength = strength
    gui.pincushion_center_x = center_x
    gui.pincushion_center_y = center_y

    with dpg.collapsing_header(parent=parent_tag, label="Pincushion correction", default_open=False):
        with dpg.group(indent=10):
            dpg.add_slider_float(
                label="Strength",
                default_value=strength,
                min_value=-0.5,
                max_value=0.5,
                format="%.4f",
                tag="pincushion_strength",
                width=250,
                callback=_apply,
            )
            dpg.add_input_float(
                label="Center X",
                default_value=center_x,
                tag="pincushion_center_x",
                width=250,
                callback=_apply,
            )
            dpg.add_input_float(
                label="Center Y",
                default_value=center_y,
                tag="pincushion_center_y",
                width=250,
                callback=_apply,
            )
            dpg.add_text(
                "Center X/Y in pixels. Use -1 for frame center. Positive strength = pincushion correction.",
                color=[150, 150, 150],
            )
