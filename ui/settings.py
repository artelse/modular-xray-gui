"""
Settings persistence: debounced save, flush, and current-settings dict. All functions take the GUI instance.
Used by gui.py. Does not include apply_loaded_settings (stays in gui; touches many gui attrs + banding defaults).
"""

import time
import dearpygui.dearpygui as dpg

from lib.settings import save_settings


def request_save(gui, scope: str = "full", debounce_s: float = None):
    """Schedule debounced settings save; full scope overrides window-only scope."""
    if not getattr(gui, "_extra_settings_keys", None):
        return
    if scope not in ("window", "full"):
        scope = "full"
    if debounce_s is None:
        debounce_s = gui._settings_save_debounce_s
    gui._settings_save_pending = True
    if scope == "full" or gui._settings_save_scope != "full":
        gui._settings_save_scope = scope
    gui._settings_save_deadline = time.monotonic() + max(0.0, float(debounce_s))


def flush_pending_save(gui, force: bool = False):
    """Run pending debounced save on main thread when due (or immediately when force=True)."""
    if not gui._settings_save_pending:
        return
    if not force and time.monotonic() < gui._settings_save_deadline:
        return
    scope = gui._settings_save_scope
    gui._settings_save_pending = False
    gui._settings_save_scope = "window"
    if scope == "window":
        save_windowing_now(gui)
    else:
        save_settings_now(gui)


def save_settings_now(gui):
    """Read current values from UI and persist to disk immediately. No-op if UI not built yet."""
    if not getattr(gui, "_extra_settings_keys", None):
        return
    for m in gui._discovered_modules:
        tag = f"load_module_cb_{m['name']}"
        if dpg.does_item_exist(tag):
            gui._module_enabled[m["name"]] = bool(dpg.get_value(tag))
    s = {}
    for m in gui._discovered_modules:
        s[f"load_{m['name']}_module"] = gui._module_enabled.get(m["name"], False)
    try:
        if not dpg.does_item_exist("acq_mode_combo"):
            save_settings(s, extra_keys=gui._extra_settings_keys)
            return
        s["acq_mode"] = dpg.get_value("acq_mode_combo")
        s["integ_time"] = dpg.get_value("integ_time_combo")
        s["integ_n"] = int(dpg.get_value("integ_n_slider"))
        s["win_min"] = float(dpg.get_value("win_min_drag"))
        s["win_max"] = float(dpg.get_value("win_max_drag"))
        s["hist_eq"] = dpg.get_value("hist_eq_cb")
        s["disp_scale"] = gui.disp_scale
        s["last_file_dialog_dir"] = getattr(gui, "_last_file_dialog_dir", "") or ""
        for m in gui._discovered_modules:
            try:
                mod = __import__(m["import_path"], fromlist=["get_settings_for_save"])
                get_save = getattr(mod, "get_settings_for_save", None)
                if callable(get_save):
                    for k, v in get_save(gui).items():
                        s[k] = v
            except Exception:
                pass
    except Exception:
        pass
    save_settings(s, extra_keys=gui._extra_settings_keys)


def save_windowing_now(gui):
    """Persist only lightweight windowing settings immediately."""
    if not getattr(gui, "_extra_settings_keys", None):
        return
    s = {
        "win_min": float(gui.win_min),
        "win_max": float(gui.win_max),
        "hist_eq": bool(gui.hist_eq),
    }
    save_settings(s, extra_keys=gui._extra_settings_keys)


def get_current_settings_dict(gui):
    """Build the same dict as save_settings would persist (for saving as profile). Returns dict."""
    if not getattr(gui, "_extra_settings_keys", None):
        return {}
    s = {}
    for m in gui._discovered_modules:
        tag = f"load_module_cb_{m['name']}"
        if dpg.does_item_exist(tag):
            gui._module_enabled[m["name"]] = bool(dpg.get_value(tag))
    for m in gui._discovered_modules:
        s[f"load_{m['name']}_module"] = gui._module_enabled.get(m["name"], False)
    try:
        if not dpg.does_item_exist("acq_mode_combo"):
            return s
        s["acq_mode"] = dpg.get_value("acq_mode_combo")
        s["integ_time"] = dpg.get_value("integ_time_combo")
        s["integ_n"] = int(dpg.get_value("integ_n_slider"))
        s["win_min"] = float(dpg.get_value("win_min_drag"))
        s["win_max"] = float(dpg.get_value("win_max_drag"))
        s["hist_eq"] = dpg.get_value("hist_eq_cb")
        s["disp_scale"] = gui.disp_scale
        for m in gui._discovered_modules:
            try:
                mod = __import__(m["import_path"], fromlist=["get_settings_for_save"])
                get_save = getattr(mod, "get_settings_for_save", None)
                if callable(get_save):
                    for k, v in get_save(gui).items():
                        s[k] = v
            except Exception:
                pass
    except Exception:
        pass
    return s
