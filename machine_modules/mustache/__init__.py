"""
Mustache (moustache) distortion correction alteration module.
Applies radial distortion with k1*r^2 + k2*r^4 so barrel and pincushion can combine (S-shape).
Center X/Y are saved; if < 0 uses frame center. Runs at slot 455 (after pincushion, before crop).
"""

import numpy as np

MODULE_INFO = {
    "display_name": "Mustache correction",
    "description": "Correct mustache (barrel+pincushion) distortion. k1/k2 and center X/Y. Applies on next startup.",
    "type": "alteration",
    "default_enabled": False,
    "pipeline_slot": 455,
}
MODULE_NAME = "mustache"


def get_setting_keys():
    return ["mustache_k1", "mustache_k2", "mustache_center_x", "mustache_center_y"]


# Spec for api.get_module_settings_for_save: (key, tag, converter, default)
_MUSTACHE_SAVE_SPEC = [
    ("mustache_k1", "mustache_k1", float, 0.0),
    ("mustache_k2", "mustache_k2", float, 0.0),
    ("mustache_center_x", "mustache_center_x", float, -1.0),
    ("mustache_center_y", "mustache_center_y", float, -1.0),
]


def get_default_settings():
    """Return default settings for this module (extracted from save spec)."""
    return {key: default for key, _tag, _conv, default in _MUSTACHE_SAVE_SPEC}


def get_settings_for_save(gui=None):
    """Return mustache k1, k2 and center from UI or loaded settings (auto fallback when UI not built)."""
    if gui is None or not getattr(gui, "api", None):
        return {}
    return gui.api.get_module_settings_for_save(_MUSTACHE_SAVE_SPEC)


def process_frame(frame, gui):
    """Apply mustache correction: r_src = r / (1 + k1*r_norm^2 + k2*r_norm^4). Center from saved X/Y or frame center."""
    from scipy.ndimage import map_coordinates

    api = gui.api
    frame = api.incoming_frame(MODULE_NAME, frame)
    h, w = frame.shape[0], frame.shape[1]
    k1, k2, cx, cy = api.get_mustache_params()
    k1, k2 = float(k1), float(k2)
    if abs(k1) < 1e-9 and abs(k2) < 1e-9:
        return api.outgoing_frame(MODULE_NAME, frame)

    cx, cy = float(cx), float(cy)
    if cx < 0 or cy < 0:
        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0
    r_max = np.sqrt(max(cx, w - 1 - cx) ** 2 + max(cy, h - 1 - cy) ** 2)
    if r_max < 1e-6:
        return api.outgoing_frame(MODULE_NAME, frame)

    rows = np.arange(h, dtype=np.float64)
    cols = np.arange(w, dtype=np.float64)
    col_grid, row_grid = np.meshgrid(cols, rows)
    dx = col_grid - cx
    dy = row_grid - cy
    r = np.sqrt(dx * dx + dy * dy)
    r_safe = np.where(r < 1e-6, 1.0, r)
    r_norm = r_safe / r_max
    r2 = r_norm * r_norm
    r4 = r2 * r2
    # r_src = r / (1 + k1*r_norm^2 + k2*r_norm^4); opposite signs for k1/k2 give mustache
    denom = 1.0 + k1 * r2 + k2 * r4
    r_src = np.where(r < 1e-6, 0.0, r_safe / np.maximum(denom, 0.1))
    scale = np.where(r < 1e-6, 1.0, r_src / r_safe)
    src_col = cx + scale * dx
    src_row = cy + scale * dy
    coords = np.stack([src_row, src_col], axis=0)
    out = map_coordinates(frame, coords, order=1, mode="reflect", cval=0.0)
    out = np.ascontiguousarray(out.astype(frame.dtype))
    return api.outgoing_frame(MODULE_NAME, out)


def build_ui(gui, parent_tag: str = "control_panel") -> None:
    """Build Mustache correction collapsing header. Center X/Y: -1 = frame center."""
    import dearpygui.dearpygui as dpg

    api = gui.api

    def _apply(sender=None, app_data=None):
        gui.mustache_k1 = float(dpg.get_value("mustache_k1"))
        gui.mustache_k2 = float(dpg.get_value("mustache_k2"))
        gui.mustache_center_x = float(dpg.get_value("mustache_center_x"))
        gui.mustache_center_y = float(dpg.get_value("mustache_center_y"))
        api.save_settings()
        getattr(gui, "_refresh_distortion_preview", lambda: None)()

    loaded = api.get_loaded_settings()
    k1 = float(loaded.get("mustache_k1", 0.0))
    k2 = float(loaded.get("mustache_k2", 0.0))
    center_x = float(loaded.get("mustache_center_x", -1.0))
    center_y = float(loaded.get("mustache_center_y", -1.0))
    gui.mustache_k1 = k1
    gui.mustache_k2 = k2
    gui.mustache_center_x = center_x
    gui.mustache_center_y = center_y

    with dpg.collapsing_header(parent=parent_tag, label="Mustache correction", default_open=False):
        with dpg.group(indent=10):
            dpg.add_slider_float(
                label="k1",
                default_value=k1,
                min_value=-0.5,
                max_value=0.5,
                format="%.4f",
                tag="mustache_k1",
                width=250,
                callback=_apply,
            )
            dpg.add_slider_float(
                label="k2",
                default_value=k2,
                min_value=-0.5,
                max_value=0.5,
                format="%.4f",
                tag="mustache_k2",
                width=250,
                callback=_apply,
            )
            dpg.add_input_float(
                label="Center X",
                default_value=center_x,
                tag="mustache_center_x",
                width=250,
                callback=_apply,
            )
            dpg.add_input_float(
                label="Center Y",
                default_value=center_y,
                tag="mustache_center_y",
                width=250,
                callback=_apply,
            )
            dpg.add_text(
                "k1*r^2 + k2*r^4. Opposite signs = mustache (S-shape). Center -1 = frame center.",
                color=[150, 150, 150],
            )
