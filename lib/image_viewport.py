#!/usr/bin/env python3
"""
Image viewport handling for zoom and pan functionality.
Manages zoom level, pan offset, and mouse interactions (wheel zoom, click-drag pan).
"""

import dearpygui.dearpygui as dpg


class ImageViewport:
    """Handles zoom and pan for an image widget."""
    
    def __init__(self, image_tag: str):
        """
        Initialize image viewport.
        
        Args:
            image_tag: DearPyGui tag of the image widget to control
        """
        self.image_tag = image_tag
        
        # Zoom/pan state in UV space:
        # - zoom=1.0 shows full texture (uv 0..1)
        # - pan_x/pan_y represent uv_min when zoom>1
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._base_image_size = None  # Base size when zoom=1.0 (fit to window)
        
        # Drag/pan state
        self._is_dragging = False
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0
        self._drag_start_pan_x = 0.0
        self._drag_start_pan_y = 0.0
        
        # Aspect ratio (will be set by resize method)
        self.aspect_ratio = 1.0

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def _get_image_rect(self):
        try:
            img_min = dpg.get_item_rect_min(self.image_tag)
            img_max = dpg.get_item_rect_max(self.image_tag)
            if img_min is None or img_max is None:
                return None
            x0, y0 = img_min
            x1, y1 = img_max
            if x1 <= x0 or y1 <= y0:
                return None
            return x0, y0, x1, y1
        except Exception:
            return None

    def _mouse_over_image(self):
        rect = self._get_image_rect()
        if rect is None:
            return False
        mx, my = dpg.get_mouse_pos()
        x0, y0, x1, y1 = rect
        return x0 <= mx <= x1 and y0 <= my <= y1
    
    def handle_wheel(self, app_data: float) -> bool:
        """
        Handle mouse wheel scroll for zooming.
        
        Args:
            app_data: Wheel delta (positive = zoom in, negative = zoom out)
            
        Returns:
            True if zoom was applied, False otherwise
        """
        rect = self._get_image_rect()
        if rect is None:
            return False
        if not self._mouse_over_image():
            return False

        x0, y0, x1, y1 = rect
        mx, my = dpg.get_mouse_pos()
        widget_w = x1 - x0
        widget_h = y1 - y0
        rel_x = self._clamp((mx - x0) / widget_w if widget_w > 0 else 0.5, 0.0, 1.0)
        rel_y = self._clamp((my - y0) / widget_h if widget_h > 0 else 0.5, 0.0, 1.0)

        old_zoom = self.zoom
        old_uv_w = 1.0 / old_zoom
        old_uv_h = 1.0 / old_zoom
        target_uv_x = self.pan_x + rel_x * old_uv_w
        target_uv_y = self.pan_y + rel_y * old_uv_h

        zoom_factor = 1.15 if app_data > 0 else (1.0 / 1.15)
        new_zoom = self._clamp(old_zoom * zoom_factor, 1.0, 12.0)
        if abs(new_zoom - old_zoom) < 1e-6:
            return False

        self.zoom = new_zoom
        if self.zoom <= 1.0:
            self.pan_x = 0.0
            self.pan_y = 0.0
            return True

        new_uv_w = 1.0 / self.zoom
        new_uv_h = 1.0 / self.zoom
        max_pan_x = max(0.0, 1.0 - new_uv_w)
        max_pan_y = max(0.0, 1.0 - new_uv_h)

        self.pan_x = self._clamp(target_uv_x - rel_x * new_uv_w, 0.0, max_pan_x)
        self.pan_y = self._clamp(target_uv_y - rel_y * new_uv_h, 0.0, max_pan_y)
        return True
    
    def handle_click(self) -> bool:
        """
        Handle mouse click to start drag/pan.
        
        Returns:
            True if drag started, False otherwise
        """
        if self.zoom <= 1.0:
            return False
        if not self._mouse_over_image():
            # Clicking outside the image should always clear any stale pan capture.
            self._is_dragging = False
            return False

        mouse_x, mouse_y = dpg.get_mouse_pos()
        self._is_dragging = True
        self._drag_start_x = mouse_x
        self._drag_start_y = mouse_y
        self._drag_start_pan_x = self.pan_x
        self._drag_start_pan_y = self.pan_y
        return True
    
    def handle_drag(self) -> bool:
        """
        Handle mouse drag to pan the image.
        
        Returns:
            True if pan was applied, False otherwise
        """
        if not self._is_dragging or self.zoom <= 1.0:
            return False

        # Safety: if release was missed, stop dragging once button is up.
        try:
            if not dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
                self._is_dragging = False
                return False
        except Exception:
            pass

        # Do not pan while interacting outside the image area (e.g. histogram controls).
        if not self._mouse_over_image():
            self._is_dragging = False
            return False

        rect = self._get_image_rect()
        if rect is None:
            return False
        x0, y0, x1, y1 = rect
        widget_w = x1 - x0
        widget_h = y1 - y0
        if widget_w <= 0 or widget_h <= 0:
            return False

        mouse_x, mouse_y = dpg.get_mouse_pos()
        delta_x = mouse_x - self._drag_start_x
        delta_y = mouse_y - self._drag_start_y

        uv_w = 1.0 / self.zoom
        uv_h = 1.0 / self.zoom
        uv_delta_x = -(delta_x / widget_w) * uv_w
        uv_delta_y = -(delta_y / widget_h) * uv_h

        max_pan_x = max(0.0, 1.0 - uv_w)
        max_pan_y = max(0.0, 1.0 - uv_h)
        new_pan_x = self._clamp(self._drag_start_pan_x + uv_delta_x, 0.0, max_pan_x)
        new_pan_y = self._clamp(self._drag_start_pan_y + uv_delta_y, 0.0, max_pan_y)

        changed = (abs(new_pan_x - self.pan_x) > 1e-6) or (abs(new_pan_y - self.pan_y) > 1e-6)
        self.pan_x = new_pan_x
        self.pan_y = new_pan_y
        return changed
    
    def handle_release(self):
        """Handle mouse release to stop drag/pan."""
        self._is_dragging = False
    
    def resize(self, panel_width: int, panel_height: int, status_bar_height: int = 115) -> tuple[int, int, tuple, tuple]:
        """
        Calculate image size and UV coordinates for current zoom/pan state.
        
        Args:
            panel_width: Available panel width
            panel_height: Available panel height
            status_bar_height: Height reserved for status bar
            
        Returns:
            Tuple of (image_width, image_height, uv_min, uv_max)
        """
        # Reserve space for status bar area and margin so zoomed-out image stays inside the panel
        # (image_area + status bar + DPG padding use ~20px more than status_bar_height alone)
        fit_margin = 32  # extra pixels so image fits without scrolling
        avail_w = max(panel_width - 16 - fit_margin, 10)   # padding + margin
        avail_h = max(panel_height - status_bar_height - fit_margin, 10)

        # Fit to available space maintaining aspect ratio (base size at zoom=1.0)
        if avail_w / avail_h > self.aspect_ratio:
            # Height-limited
            base_h = int(avail_h)
            base_w = int(base_h * self.aspect_ratio)
        else:
            # Width-limited
            base_w = int(avail_w)
            base_h = int(base_w / self.aspect_ratio)
        
        self._base_image_size = (base_w, base_h)
        
        # Keep widget fit size constant; zoom is handled by UV window.
        img_w = int(base_w)
        img_h = int(base_h)

        # Clamp zoom to reasonable limits (minimum is 1.0 = fit to window)
        self.zoom = self._clamp(self.zoom, 1.0, 12.0)
        
        # Calculate UV coordinates for zoom/pan (texture coordinates 0-1)
        # Pan is normalized (0-1), where 0 = top-left, 1 = bottom-right
        # When zoomed, we show a portion of the texture
        if self.zoom > 1.0:
            # Zoomed in: show portion of texture
            uv_w = 1.0 / self.zoom
            uv_h = 1.0 / self.zoom
            # Clamp pan to keep image visible
            max_pan_x = max(0.0, 1.0 - uv_w)
            max_pan_y = max(0.0, 1.0 - uv_h)
            pan_x = self._clamp(self.pan_x, 0.0, max_pan_x)
            pan_y = self._clamp(self.pan_y, 0.0, max_pan_y)
            self.pan_x = pan_x
            self.pan_y = pan_y
            uv_min = (pan_x, pan_y)
            uv_max = (pan_x + uv_w, pan_y + uv_h)
        else:
            # Zoomed out or fit: show full texture
            uv_min = (0.0, 0.0)
            uv_max = (1.0, 1.0)
            # Reset pan when zoomed out
            self.pan_x = 0.0
            self.pan_y = 0.0
        
        return img_w, img_h, uv_min, uv_max
