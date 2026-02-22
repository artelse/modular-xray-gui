"""
Build the main application UI: frame size, pipeline, texture, file dialogs, main window, control panel, settings window.
Single entry point: build_ui(gui). Called from gui._build_ui().
"""

import dearpygui.dearpygui as dpg

from ui.constants import DEFAULT_FRAME_W, DEFAULT_FRAME_H, INTEGRATION_CHOICES
from lib.image_viewport import ImageViewport


def build_ui(gui):
    """Build full UI: frame size, alteration pipeline, texture, dialogs, main window with control panel, settings window."""
    # Frame size from selected detector module (highest camera_priority among enabled)
    detector_modules = [m for m in gui._discovered_modules if m.get("type") == "detector" and gui._module_enabled.get(m["name"], False)]
    detector_modules.sort(key=lambda m: m.get("camera_priority", 0), reverse=True)
    if detector_modules:
        try:
            cam_mod = __import__(detector_modules[0]["import_path"], fromlist=["get_frame_size"])
            gui.frame_width, gui.frame_height = cam_mod.get_frame_size()
        except Exception:
            gui.frame_width, gui.frame_height = DEFAULT_FRAME_W, DEFAULT_FRAME_H
    else:
        gui.frame_width, gui.frame_height = DEFAULT_FRAME_W, DEFAULT_FRAME_H
    gui._disp_w = gui.frame_width // gui.disp_scale
    gui._disp_h = gui.frame_height // gui.disp_scale
    gui._aspect = gui.frame_width / gui.frame_height
    gui.bad_pixel_map_mask = None

    # Build image alteration pipeline (slot, process_frame) and distortion-only sublist for live preview
    image_processing_modules = [m for m in gui._discovered_modules if m.get("type") == "image_processing" and gui._module_enabled.get(m["name"], False)]
    image_processing_modules.sort(key=lambda m: m.get("pipeline_slot", 0))
    gui._alteration_pipeline = []
    gui._pipeline_module_slots = {}
    for m in image_processing_modules:
        try:
            mod = __import__(m["import_path"], fromlist=["process_frame"])
            pf = getattr(mod, "process_frame", None)
            if callable(pf):
                slot = m.get("pipeline_slot", 0)
                name = m["name"]
                gui._alteration_pipeline.append((slot, name, pf))
                gui._pipeline_module_slots[name] = slot
        except Exception:
            pass
    gui._distortion_crop_pipeline = [(s, n, pf) for s, n, pf in gui._alteration_pipeline if s >= gui.DISTORTION_PREVIEW_SLOT]

    gui.api.warn_about_unloaded_options_with_saved_values()

    blank = [0.0] * (gui._disp_w * gui._disp_h * 4)
    with dpg.texture_registry():
        gui._texture_id = dpg.add_dynamic_texture(
            width=gui._disp_w, height=gui._disp_h, default_value=blank
        )

    with dpg.file_dialog(
        directory_selector=False, show=False, tag="file_dialog",
        callback=gui._cb_file_selected, width=600, height=400,
        default_filename="xray_frame.png",
        default_path=gui._get_file_dialog_default_path(),
    ):
        dpg.add_file_extension(".png")

    with dpg.file_dialog(
        directory_selector=False, show=False, tag="tiff_file_dialog",
        callback=gui._cb_tiff_file_selected, width=600, height=400,
        default_filename=gui._get_default_tiff_filename(),
        default_path=gui._get_file_dialog_default_path(),
    ):
        dpg.add_file_extension(".tif")
        dpg.add_file_extension(".tiff")

    with dpg.file_dialog(
        directory_selector=False, show=False, tag="open_image_file_dialog",
        callback=gui._cb_open_image_file_selected, width=600, height=400,
        default_path=gui._get_file_dialog_default_path(),
    ):
        dpg.add_file_extension(".tif")
        dpg.add_file_extension(".tiff")
        dpg.add_file_extension(".png")

    with dpg.handler_registry(tag="wheel_handler_registry"):
        dpg.add_mouse_wheel_handler(callback=gui._cb_mouse_wheel)
        dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left, callback=gui._cb_mouse_click)
        dpg.add_mouse_drag_handler(button=dpg.mvMouseButton_Left, callback=gui._cb_mouse_drag)
        dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, callback=gui._cb_mouse_release)

    with dpg.window(tag="primary"):
        with dpg.menu_bar():
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="Export PNG...", callback=gui._cb_export_png)
                dpg.add_menu_item(label="Save as TIFF...", callback=gui._cb_save_tiff)
                dpg.add_menu_item(label="Quit", callback=lambda: dpg.stop_dearpygui())
            with dpg.menu(label="Settings"):
                dpg.add_menu_item(label="Settings...", callback=gui._cb_show_settings)

        with dpg.group(horizontal=True):
            with dpg.child_window(width=-370, tag="image_panel", no_scrollbar=True):
                with dpg.child_window(width=-1, height=-115, tag="image_area", no_scrollbar=True):
                    dpg.add_image(gui._texture_id, tag="main_image")
                gui.image_viewport = ImageViewport("main_image", hover_area_tag="image_area")
                gui.image_viewport.aspect_ratio = gui._aspect
                with dpg.group(tag="status_bar_group"):
                    dpg.add_separator()
                    dpg.add_text("Idle", tag="status_text")
                    dpg.add_progress_bar(default_value=0.0, tag="progress_bar", width=-1)
                    dpg.add_text("Frames: 0 | FPS: 0.0", tag="stats_text")
                    dpg.add_text("--", tag="diag_text")

            # 350 + 15 so content width matches menu (border/padding subtracted from total in DPG)
            with dpg.child_window(width=365, tag="control_column", no_scrollbar=True):
                with dpg.child_window(width=-1, tag="control_panel", height=-220):
                    with dpg.collapsing_header(label="File", default_open=False):
                        with dpg.group(indent=10):
                            dpg.add_button(label="Open image", tag="file_open_image_btn", width=-1, callback=gui._cb_file_open_image)
                            dpg.add_button(label="Run through processing", tag="file_run_processing_btn", width=-1, callback=gui._cb_file_run_through_processing)
                            dpg.add_button(label="Save TIF", tag="file_save_tiff_btn", width=-1, callback=gui._cb_file_save_tiff, enabled=False)

                    if detector_modules:
                        try:
                            cam_mod = __import__(detector_modules[0]["import_path"], fromlist=["build_ui"])
                            cam_mod.build_ui(gui, "control_panel")
                            gui.camera_module_name = detector_modules[0]["name"]
                            gui._load_dark_field()
                            gui._load_flat_field()
                        except Exception:
                            gui.camera_module_name = None
                            with dpg.collapsing_header(label="Connection", default_open=True):
                                with dpg.group(indent=10):
                                    dpg.add_text("No detector module loaded.", color=[150, 150, 150])
                                    dpg.add_text("Enable a detector module in Settings (applies on next startup).", color=[120, 120, 120])
                    else:
                        gui.camera_module_name = None
                        with dpg.collapsing_header(label="Connection", default_open=True):
                            with dpg.group(indent=10):
                                dpg.add_text("No detector module loaded.", color=[150, 150, 150])
                                dpg.add_text("Enable a detector module in Settings (applies on next startup).", color=[120, 120, 120])

                    with dpg.collapsing_header(label="Acquisition", default_open=True):
                        with dpg.group(indent=10):
                            if gui.camera_module is not None:
                                modes = gui.camera_module.get_acquisition_modes()
                                acq_items = [label for label, _ in modes]
                                gui._acquisition_mode_map = {label: mode_id for label, mode_id in modes}
                            else:
                                acq_items = ["Single Shot", "Dual Shot", "Continuous", "Capture N"]
                                gui._acquisition_mode_map = {
                                    "Single Shot": "single", "Dual Shot": "dual",
                                    "Continuous": "continuous", "Capture N": "capture_n",
                                }
                            saved_acq = gui._loaded_settings.get("acq_mode", "Dual Shot")
                            default_acq = saved_acq if saved_acq in acq_items else (acq_items[0] if acq_items else "Dual Shot")
                            dpg.add_combo(
                                items=acq_items,
                                default_value=default_acq, tag="acq_mode_combo", width=-1,
                                callback=lambda s, a: gui._save_settings()
                            )
                            integ_choices = getattr(gui.camera_module, "get_integration_choices", lambda: None)()
                            if integ_choices is None:
                                integ_choices = INTEGRATION_CHOICES
                            saved_integ = gui._loaded_settings.get("integ_time", "1 s")
                            default_integ = saved_integ if saved_integ in integ_choices else (integ_choices[0] if integ_choices else "1 s")
                            dpg.add_combo(
                                items=integ_choices,
                                default_value=default_integ, tag="integ_time_combo", width=-1,
                                callback=gui._cb_integ_time_changed
                            )
                            dpg.add_text("(trigger interval = integration time)", color=[120, 120, 120, 255])
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="Start", callback=gui._cb_start, width=115)
                                dpg.add_button(label="Stop", callback=gui._cb_stop, width=115)

                    with dpg.collapsing_header(label="Integration", default_open=True):
                        with dpg.group(indent=10):
                            dpg.add_slider_int(
                                label="N frames", default_value=gui._loaded_settings.get("integ_n", 1),
                                min_value=1, max_value=32, tag="integ_n_slider", width=-60,
                                callback=lambda s, a: gui._save_settings()
                            )
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="Clear Buffer", callback=gui._cb_clear_buffer, width=115)
                                dpg.add_button(label="Capture N", callback=gui._cb_capture_n, width=115)

                    for m in gui._discovered_modules:
                        if m.get("type") != "machine" or not gui._module_enabled.get(m["name"], False):
                            continue
                        try:
                            mod = __import__(m["import_path"], fromlist=["build_ui"])
                            mod.build_ui(gui, "control_panel")
                        except Exception:
                            pass

                    if gui._module_enabled.get("dark_correction", False):
                        with dpg.collapsing_header(label="Dark Field", default_open=False):
                            with dpg.group(indent=10):
                                dpg.add_slider_int(
                                    label="Stack", default_value=gui._dark_stack_n,
                                    min_value=1, max_value=50, tag="dark_stack_slider", width=-120,
                                    callback=lambda s, a: gui._save_settings()
                                )
                                with dpg.group(horizontal=True):
                                    dpg.add_button(label="Capture Dark", callback=gui._cb_capture_dark, width=115)
                                    dpg.add_button(label="Clear Dark", callback=gui._cb_clear_dark, width=115)
                                dpg.add_text(gui._dark_status_text(), tag="dark_status")

                    if gui._module_enabled.get("flat_correction", False):
                        with dpg.collapsing_header(label="Flat Field", default_open=False):
                            with dpg.group(indent=10):
                                dpg.add_slider_int(
                                    label="Stack", default_value=gui._flat_stack_n,
                                    min_value=1, max_value=50, tag="flat_stack_slider", width=-120,
                                    callback=lambda s, a: gui._save_settings()
                                )
                                with dpg.group(horizontal=True):
                                    dpg.add_button(label="Capture Flat", callback=gui._cb_capture_flat, width=115)
                                    dpg.add_button(label="Clear Flat", callback=gui._cb_clear_flat, width=115)
                                dpg.add_text(gui._flat_status_text(), tag="flat_status")

                    image_processing_for_ui = [m for m in gui._discovered_modules if m.get("type") == "image_processing" and gui._module_enabled.get(m["name"], False)]
                    image_processing_for_ui.sort(key=lambda m: m.get("pipeline_slot", 0))
                    for m in image_processing_for_ui:
                        try:
                            mod = __import__(m["import_path"], fromlist=["build_ui"])
                            mod.build_ui(gui, "control_panel")
                        except Exception:
                            pass

                    for m in gui._discovered_modules:
                        if m.get("type") != "manual_alteration" or not gui._module_enabled.get(m["name"], False):
                            continue
                        try:
                            mod = __import__(m["import_path"], fromlist=["build_ui"])
                            mod.build_ui(gui, "control_panel")
                        except Exception:
                            pass

                    for m in gui._discovered_modules:
                        if m.get("type") != "workflow_automation" or not gui._module_enabled.get(m["name"], False):
                            continue
                        try:
                            mod = __import__(m["import_path"], fromlist=["build_ui"])
                            mod.build_ui(gui, "control_panel")
                        except Exception:
                            pass

                # Right bottom: histogram + image controls (non-scrollable, no wheel conflict)
                with dpg.group(tag="control_bottom_group"):
                    with dpg.theme(tag="hist_plot_theme"):
                        with dpg.theme_component(dpg.mvPlot):
                            dpg.add_theme_style(dpg.mvPlotStyleVar_PlotPadding, 2, 2, category=dpg.mvThemeCat_Plots)
                            dpg.add_theme_style(dpg.mvPlotStyleVar_PlotBorderSize, 1, category=dpg.mvThemeCat_Plots)
                    with dpg.plot(
                        height=135, width=-1, tag="hist_plot",
                        no_title=True, no_mouse_pos=True,
                        no_box_select=True,
                        no_frame=True,
                    ):
                        dpg.add_plot_axis(
                            dpg.mvXAxis, label="", tag="hist_x",
                            no_tick_labels=True,
                        )
                        with dpg.plot_axis(
                            dpg.mvYAxis, label="", tag="hist_y",
                            no_tick_labels=True, lock_min=True, lock_max=True,
                        ):
                            dpg.add_shade_series(
                                [0], [0], y2=[0], tag="hist_series"
                            )
                        dpg.add_drag_line(
                            label="Min", color=[255, 100, 100, 255],
                            default_value=gui.win_min, tag="hist_min_line",
                            callback=gui._cb_hist_min_dragged
                        )
                        dpg.add_drag_line(
                            label="Max", color=[100, 100, 255, 255],
                            default_value=gui.win_max, tag="hist_max_line",
                            callback=gui._cb_hist_max_dragged
                        )
                    dpg.bind_item_theme("hist_plot", "hist_plot_theme")
                    gui.win_min, gui.win_max = gui._clamp_window_bounds(gui.win_min, gui.win_max)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Auto Window", callback=gui._cb_auto_window, width=115)
                        dpg.add_checkbox(label="Hist EQ", default_value=gui.hist_eq, callback=gui._cb_hist_eq_toggle, tag="hist_eq_cb")
                    dpg.add_input_float(
                        label="Min", default_value=gui.win_min,
                        callback=gui._cb_win_min_changed, tag="win_min_drag", width=-40,
                        on_enter=True, min_value=0.0, min_clamped=True,
                        max_value=gui._get_display_max_value(), max_clamped=True
                    )
                    dpg.add_input_float(
                        label="Max", default_value=gui.win_max,
                        callback=gui._cb_win_max_changed, tag="win_max_drag", width=-40,
                        on_enter=True, min_value=0.0, min_clamped=True,
                        max_value=gui._get_display_max_value(), max_clamped=True
                    )

    _disp_scale_labels = {"1": "1 - Full", "2": "2 - Half", "4": "4 - Quarter"}
    with dpg.window(label="Settings", tag="settings_window", show=False, on_close=lambda: gui._flush_pending_settings_save(force=True)):
        dpg.add_combo(
            label="Display scale",
            items=["1 - Full", "2 - Half", "4 - Quarter"],
            default_value=_disp_scale_labels.get(str(gui.disp_scale), "1 - Full"),
            tag="disp_scale_combo",
            width=-1,
            callback=gui._cb_disp_scale
        )
        dpg.add_text("Reduces display resolution (block average).", color=[150, 150, 150])
        dpg.add_spacer()
        _type_order = {"detector": 0, "image_processing": 1, "manual_alteration": 2, "machine": 3, "workflow_automation": 4}
        _type_headers = {"detector": "Detector modules", "image_processing": "Image processing modules", "manual_alteration": "Manual alteration modules", "machine": "Machine modules", "workflow_automation": "Workflow modules"}

        def _settings_module_sort_key(m):
            t = m.get("type", "machine")
            order = _type_order.get(t, 3)
            if t == "detector":
                return (order, -m.get("camera_priority", 0))
            if t == "image_processing" or t == "manual_alteration":
                return (order, m.get("pipeline_slot", 0))
            return (order, 0)

        _settings_modules = sorted(gui._discovered_modules, key=_settings_module_sort_key)
        _last_type = None
        for m in _settings_modules:
            t = m.get("type", "machine")
            if t != _last_type:
                _last_type = t
                header = _type_headers.get(t, "Modules")
                dpg.add_text(header, color=[200, 200, 200])
                if t == "detector":
                    detector_mods = [x for x in _settings_modules if x.get("type") == "detector"]
                    _det_items = ["None"] + [gui._detector_combo_label(x) for x in detector_mods]
                    _det_enabled = next((gui._detector_combo_label(x) for x in detector_mods if gui._module_enabled.get(x["name"], False)), None)
                    dpg.add_combo(
                        label="Detector module",
                        items=_det_items,
                        default_value=_det_enabled or "None",
                        tag="settings_detector_combo",
                        width=-1,
                        callback=gui._cb_detector_module_combo
                    )
                    continue
            if t == "detector":
                continue
            tag = f"load_module_cb_{m['name']}"
            label = f"Load {m['display_name']} module"
            if t == "image_processing" or (t == "manual_alteration" and m.get("pipeline_slot", 0) != 0):
                slot = m.get("pipeline_slot", 0)
                label += f" (slot {slot})" if t == "image_processing" else " (post-capture)"
            dpg.add_checkbox(
                label=label,
                default_value=gui._module_enabled.get(m["name"], m.get("default_enabled", False)),
                tag=tag,
                callback=lambda s, a, name=m["name"]: gui._cb_load_module(name)
            )
        dpg.add_spacer()
        dpg.add_text("Module load state and display scale apply on next startup.", color=[150, 150, 150])
        dpg.add_spacer()
        dpg.add_separator()
        dpg.add_text("Capture profiles", color=[200, 200, 200])
        dpg.add_text("Save current settings as a named profile, or load a profile (restart required).", color=[150, 150, 150])
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="profile_name_input", default_value="", hint="Profile name", width=-120)
            dpg.add_button(label="Save as profile", tag="profile_save_btn", callback=gui._cb_save_profile, width=115)
        dpg.add_spacer()
        dpg.add_spacer()
        with dpg.group(horizontal=True):
            dpg.add_combo(tag="profile_load_combo", items=[], width=-120, callback=lambda s, a: None)
            dpg.add_button(label="Load and restart", tag="profile_load_btn", callback=gui._cb_load_profile_restart, width=115)
        dpg.add_text("(Default: current settings.json; no profile file until you save one.)", color=[120, 120, 120])
