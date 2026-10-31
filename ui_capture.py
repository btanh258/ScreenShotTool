# -*- coding: utf-8 -*-
"""ui_capture.py - full-screen snipping overlay + capture result toast.

This module owns everything the user sees *around* the editor:

``SnippingTool``
    Grabs the desktop with ``mss``, freezes it behind a dim scrim, then lets the
    user either click a window / detected UI block (smart snap, ``win32gui`` +
    DWM extended frame bounds + optional OpenCV contours) or drag a freehand
    region.  A magnifier with pixel grid and colour readout follows the cursor,
    ``Esc`` cancels both through the Tk binding and a global keyboard hook.

``ResultToast``
    The "captured" card: thumbnail, dimensions, primary *open editor* action and
    a progress bar that auto-dismisses the card after ``duration`` ms, pausing
    while the pointer rests on it.

The behaviour is a straight port of the original ``SnippingTool`` /
``show_toast`` code that lived in ``ScreenShotTool.pyw`` - every capture path
(mss grab, DWM rects, OpenCV rects, click-to-snap, drag-to-select, 10x10
minimum, clipboard publish, toast -> editor, 6 s auto-dismiss, work-area aware
placement, error dialogs) is preserved.  Only the rendering is new: everything
is drawn from :mod:`ui_theme` tokens and :mod:`ui_widgets` controls.

IMPORT / DEPENDENCY POLICY
--------------------------
``import ui_capture`` must never fail because an *optional* dependency is
missing.  ``mss``, ``cv2`` and ``numpy`` (and ``win32gui``) are imported lazily
on first use and cached in module globals that stay patchable:

===================  =====================================================
``ui_capture.mss``   inject a fake before ``start_snipping()``
``ui_capture.cv2``   ``None`` disables the OpenCV smart rects
``ui_capture.np``    paired with ``cv2``
===================  =====================================================

To simulate "not installed" in a test, set the global to ``None`` **and**
``ui_capture._optional_imported = True`` (or call
:func:`reset_optional_dependencies` to force a fresh import attempt).
"""

from __future__ import annotations

import ctypes
import io
import logging
import os
import sys
import time
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageEnhance, ImageTk

import ui_theme as T
import ui_widgets as W

__all__ = ["SnippingTool", "ResultToast"]

log = logging.getLogger(__name__)

try:  # Pillow >= 9.1
    _RESAMPLE = Image.Resampling.LANCZOS
    _NEAREST = Image.Resampling.NEAREST
except AttributeError:  # pragma: no cover - old Pillow
    _RESAMPLE = Image.LANCZOS
    _NEAREST = Image.NEAREST


# --------------------------------------------------------------------------
# Lazy optional dependencies
# --------------------------------------------------------------------------
mss = None
cv2 = None
np = None
_optional_imported = False
_win32gui = None
_win32gui_present = None


def reset_optional_dependencies():
    """Forget the lazily imported optional modules (test helper)."""
    global mss, cv2, np, _optional_imported, _win32gui, _win32gui_present
    mss = cv2 = np = None
    _optional_imported = False
    _win32gui = None
    _win32gui_present = None


def _import_optional_dependencies():
    """Import mss / cv2 / numpy once, tolerating their absence."""
    global mss, cv2, np, _optional_imported
    if _optional_imported:
        return
    _optional_imported = True
    if mss is None:
        try:
            import mss as _mss_module
        except Exception:  # ImportError, but also broken installs
            _mss_module = None
        mss = _mss_module
    if cv2 is None:
        try:
            import cv2 as _cv2_module
        except Exception:
            _cv2_module = None
        cv2 = _cv2_module
    if np is None:
        try:
            import numpy as _np_module
        except Exception:
            _np_module = None
        np = _np_module


def _get_win32gui():
    """Return ``win32gui`` or ``None`` (smart window snapping is optional)."""
    global _win32gui, _win32gui_present
    if _win32gui is not None:
        return _win32gui
    if _win32gui_present:
        return None
    try:
        import win32gui as _module
    except Exception:
        _win32gui_present = False
        return None
    _win32gui = _module
    _win32gui_present = True
    return _win32gui


def _resolve_keyboard(keyboard_module):
    """``None`` -> auto-detect; a module -> use it; ``False`` -> disable."""
    if keyboard_module is None:
        try:
            import keyboard as _kb
        except Exception:
            return None
        return _kb
    return keyboard_module or None


# --------------------------------------------------------------------------
# Default collaborator implementations (used when the app injects nothing)
# --------------------------------------------------------------------------
def _default_resource_path(relative_path):
    """Absolute path that works both from source and from a PyInstaller exe."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def _default_send_to_clipboard(image):
    """Publish PNG *and* CF_DIB, retrying transient clipboard locks.

    Mirrors ``ScreenShotTool.send_to_clipboard`` so the module stays usable on
    its own; the application normally injects its own writer.
    """
    try:
        import win32clipboard
    except Exception:
        log.warning("Clipboard unavailable: pywin32 not installed")
        return False
    rgba = image.convert("RGBA")
    output_png = io.BytesIO()
    rgba.save(output_png, "PNG")
    output_bmp = io.BytesIO()
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.getchannel("A"))
    bg.save(output_bmp, "BMP")
    png_data = output_png.getvalue()
    bmp_data = output_bmp.getvalue()[14:]
    last_error = None
    for _ in range(4):
        opened = False
        try:
            win32clipboard.OpenClipboard()
            opened = True
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(
                win32clipboard.RegisterClipboardFormat("PNG"), png_data)
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
            return True
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
        finally:
            if opened:
                win32clipboard.CloseClipboard()
    log.warning("Clipboard unavailable: %s", last_error)
    return False


def _work_area():
    """``(left, top, right, bottom)`` of the Windows work area."""
    try:
        rect = ctypes.wintypes.RECT()
        user32 = ctypes.windll.user32
        user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        if rect.right > rect.left and rect.bottom > rect.top:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, None, None


def _extended_frame_bounds(win32gui_mod, hwnd):
    """DWM extended-frame rect (no invisible border / drop shadow)."""
    rect = ctypes.wintypes.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    try:
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            ctypes.wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
    except Exception:
        result = -1
    if result == 0:
        return rect.left, rect.top, rect.right, rect.bottom
    return win32gui_mod.GetWindowRect(hwnd)


def _screenshot_to_image(shot):
    """Convert an mss screenshot to a PIL image (BGRX for mss, RGB for fakes)."""
    if hasattr(shot, "bgra"):
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return Image.frombytes("RGB", shot.size, shot.rgb, "raw", "RGB")


# ==========================================================================
# SnippingTool
# ==========================================================================
class SnippingTool:
    """Full-screen snipping overlay (behaviour-identical to the legacy class)."""

    MIN_SIZE = 10            # minimum accepted selection edge, in pixels
    DRAG_THRESHOLD = 5       # click vs drag, in pixels
    DIM_FACTOR = 0.4         # scrim brightness applied to the desktop grab
    OUTSIDE_FACTOR = 0.18    # extra dim applied outside an active selection
    MAG_RADIUS = 10          # magnifier samples a (2r)x(2r) pixel window
    MAG_ZOOM = 6             # ... blown up by this factor
    WINDOW_MIN_SIZE = 40     # smallest window DWM rect worth snapping to

    def __init__(self, root, *, resource_path=None, send_to_clipboard=None,
                 open_editor=None, keyboard_module=None):
        self.root = root
        self._resource_path = resource_path or _default_resource_path
        self._send_to_clipboard = send_to_clipboard or _default_send_to_clipboard
        self._open_editor = open_editor
        self._keyboard = _resolve_keyboard(keyboard_module)

        # -- public state (contract section 4) ------------------------------
        self.is_active = False
        self.monitor_origin = (0, 0)
        self.full_img = None

        # -- capture / overlay state ---------------------------------------
        self.tk_dark = None
        self.esc_hook = None
        self.current_toast = None
        self.start_x = 0
        self.start_y = 0
        self.is_dragging = False
        self.snip_state = 0          # 0 = idle/window-picking, 1 = dragging
        self.smart_rects = []
        self.window_rects = []
        self.cv_rects = []
        self.current_auto_rect = None
        self.clicked_auto_rect = None
        self._selection_rect = None
        self._mag_key = None
        self.tk_sel = None
        self.tk_auto_sel = None
        self.tk_mag = None
        self._dim_photo = None

        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            pass
        try:
            self.root.config(cursor="cross")
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.root, cursor="cross",
                                bg=T.COLORS.canvas_bg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        # Declared to keep the legacy binding surface; double-click is a no-op.
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Escape>", self.cancel_snip)

    # ------------------------------------------------------------------
    # Smart rect detection
    # ------------------------------------------------------------------
    def _prepare_smart_rects(self):
        """Collect snap candidates: top-most windows first, then CV blocks."""
        self.window_rects = []
        self.cv_rects = []
        _import_optional_dependencies()
        if self.full_img is None:
            return

        self._prepare_window_rects()
        self._prepare_cv_rects()

    def _prepare_window_rects(self):
        win32gui_mod = _get_win32gui()
        if win32gui_mod is None:
            return
        origin_x, origin_y = getattr(self, "monitor_origin", (0, 0))
        full_w, full_h = self.full_img.width, self.full_img.height

        def enum_win_cb(hwnd, _ctx):
            try:
                if not (win32gui_mod.IsWindowVisible(hwnd)
                        and not win32gui_mod.IsIconic(hwnd)):
                    return True
                title = win32gui_mod.GetWindowText(hwnd)
                class_name = win32gui_mod.GetClassName(hwnd)
                # Skip the desktop wallpaper shells.
                if not title or class_name in ("Progman", "WorkerW"):
                    return True
                left, top, right, bottom = _extended_frame_bounds(win32gui_mod, hwnd)
                width, height = right - left, bottom - top
                if self.WINDOW_MIN_SIZE < width <= full_w and self.WINDOW_MIN_SIZE < height <= full_h:
                    self.window_rects.append((
                        max(0, left - origin_x),
                        max(0, top - origin_y),
                        min(full_w, right - origin_x),
                        min(full_h, bottom - origin_y),
                    ))
            except Exception:
                # A single hostile window must not kill snapping for the rest.
                return True
            return True

        try:
            win32gui_mod.EnumWindows(enum_win_cb, None)
        except Exception:
            pass

    def _prepare_cv_rects(self):
        """OpenCV Canny contour blocks.  Skipped cleanly without cv2/numpy."""
        if cv2 is None or np is None:
            return
        scale_factor = 0.5
        small_width = int(self.full_img.width * scale_factor)
        small_height = int(self.full_img.height * scale_factor)
        img_np = np.array(self.full_img.resize((small_width, small_height), _NEAREST))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(cv2.medianBlur(gray, 3), 40, 120)
        closed = cv2.morphologyEx(
            edges, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        full_w, full_h = self.full_img.width, self.full_img.height
        for contour in contours:
            approx = cv2.approxPolyDP(
                contour, 0.04 * cv2.arcLength(contour, True), True)
            if 4 <= len(approx) <= 6:
                x_sm, y_sm, w_sm, h_sm = cv2.boundingRect(approx)
                x = int(x_sm / scale_factor)
                y = int(y_sm / scale_factor)
                w = int(w_sm / scale_factor)
                h = int(h_sm / scale_factor)
                if 40 < w < full_w - 20 and 40 < h < full_h - 20:
                    self.cv_rects.append((x, y, x + w, y + h))

    # ------------------------------------------------------------------
    # Capture lifecycle
    # ------------------------------------------------------------------
    def start_snipping(self, delay=0):
        """Enter capture mode.  Re-entrant calls are ignored (held hotkey).

        ``delay`` postpones only the actual screen grab, not the window setup:
        it exists so a user can open a menu, hover a tooltip or wait out an
        animation before the screenshot freezes. The tray menu already closes
        itself, but the app underneath often needs a moment to show the state
        worth capturing.
        """
        if getattr(self, "is_active", False):
            return
        self.is_active = True

        if delay and delay > 0:
            # Sleep before anything is captured. Doing it on the Tk thread would
            # freeze the tray-owned window for the whole delay, so the wait runs
            # on a worker and the grab is handed back to the main loop.
            self.root.after(100, lambda: self._deferred_snipping(float(delay)))
            return
        self._capture_now()

    def _deferred_snipping(self, delay):
        """Run the grab after ``delay`` seconds without blocking the UI thread."""
        self._pending_delay_job = getattr(self, "_pending_delay_job", None)
        try:
            import threading as _threading
            worker = _threading.Timer(delay, lambda: self.root.after(0, self._capture_now))
            worker.daemon = True
            worker.start()
            self._pending_delay_job = worker
        except Exception:
            log.exception("Could not schedule delayed capture")
            self._capture_now()

    def _capture_now(self):
        """Take the screenshot and enter capture mode immediately."""
        _import_optional_dependencies()
        if mss is None:
            self.is_active = False
            messagebox.showerror(
                "Thiếu thư viện",
                "Chưa cài mss. Hãy chạy: pip install -r requirements.txt",
                parent=self.root,
            )
            return

        sct = None
        try:
            sct = mss.mss()
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            self.full_img = _screenshot_to_image(shot)
            self.monitor_origin = (monitor.get("left", 0), monitor.get("top", 0))
            self.root.geometry(
                f"{monitor['width']}x{monitor['height']}"
                f"{monitor.get('left', 0):+d}{monitor.get('top', 0):+d}"
            )
        except Exception as exc:
            self.is_active = False
            log.exception("Screen capture failed")
            messagebox.showerror("Không thể chụp màn hình", str(exc), parent=self.root)
            return
        finally:
            close = getattr(sct, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        self.tk_dark = ImageTk.PhotoImage(
            ImageEnhance.Brightness(self.full_img).enhance(self.DIM_FACTOR))
        # Pre-render the deeper "outside" scrim once per capture so dragging
        # does not pay for a darken + full-screen PhotoImage on every motion.
        self._dim_photo = ImageTk.PhotoImage(
            ImageEnhance.Brightness(self.full_img).enhance(self.OUTSIDE_FACTOR))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_dark, tags="bg")

        self._prepare_smart_rects()

        self.snip_state = 0
        self.is_dragging = False
        self.current_auto_rect = None
        self.clicked_auto_rect = None
        self._selection_rect = None
        self._mag_key = None
        self._draw_hint()

        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.update()
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass

        try:
            self.root.focus_force()
            self.canvas.focus_set()
        except tk.TclError:
            pass

        self._install_escape_hook()

    def _install_escape_hook(self):
        if self.esc_hook or self._keyboard is None:
            return
        try:
            self.esc_hook = self._keyboard.on_press_key(
                "esc", self._global_cancel_snip, suppress=True)
        except Exception:
            # No admin rights / no hook support: the Tk <Escape> binding remains.
            log.warning("Global Esc hook unavailable; using the in-window binding only")
            self.esc_hook = None

    def _release_escape_hook(self):
        if not self.esc_hook:
            return
        try:
            if self._keyboard is not None:
                self._keyboard.unhook(self.esc_hook)
        except Exception:
            pass
        self.esc_hook = None

    def _global_cancel_snip(self, event=None):
        """Global-hook callback: hop onto the Tk thread."""
        try:
            self.root.after(0, self.cancel_snip)
        except tk.TclError:
            pass

    def cancel_snip(self, event=None):
        self.is_active = False
        self.snip_state = 0
        self.is_dragging = False
        self.current_auto_rect = None
        self.clicked_auto_rect = None
        self._selection_rect = None
        self._release_escape_hook()
        self.canvas.delete("all")
        self.tk_dark = None
        self._dim_photo = None
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    _LAYER_ORDER = ("outside", "auto_selection", "selection",
                    "selection_badge", "hint", "guidelines", "magnifier")

    def _raise_layers(self):
        for tag in self._LAYER_ORDER:
            try:
                self.canvas.tag_raise(tag)
            except tk.TclError:
                pass

    def _screen_size(self):
        if self.full_img is None:
            return self.canvas.winfo_width(), self.canvas.winfo_height()
        return self.full_img.width, self.full_img.height

    def _draw_pill(self, x, y, width, height, text, *, fnt, fill, fg, outline,
                   pad=0, tags=()):
        """Rounded label pill; returns ``(x1, y1, x2, y2)`` of the pill."""
        T.round_rect(self.canvas, x, y, x + width, y + height, height / 2.0,
                     fill=fill, outline=outline, tags=tags)
        self.canvas.create_text(x + width / 2.0, y + height / 2.0, text=text,
                                fill=fg, font=fnt, anchor="center", tags=tags)
        return x, y, x + width, y + height

    def _draw_hint(self):
        """Centered bottom hint pill shown while idle."""
        self.canvas.delete("hint")
        if self.full_img is None:
            return
        screen_w, screen_h = self.full_img.width, self.full_img.height
        text = "Kéo chuột để chọn vùng · Click để chụp cửa sổ · Esc để hủy"
        fnt = T.FONTS.small
        text_w = W.measure_text(fnt, text)
        pad_x, height = 18, 34
        width = text_w + pad_x * 2
        x = (screen_w - width) / 2.0
        y = screen_h - height - 44
        T.round_rect(self.canvas, x, y, x + width, y + height, height / 2.0,
                     fill=T.COLORS.hint_bg, outline=T.COLORS.border_strong,
                     tags="hint")
        # Accent dot as a quiet "you are in capture mode" marker.
        dot_x = x + pad_x - 4
        self.canvas.create_oval(dot_x - 3, y + height / 2.0 - 3,
                                dot_x + 3, y + height / 2.0 + 3,
                                fill=T.COLORS.accent, outline="", tags="hint")
        self.canvas.create_text(x + pad_x + 8, y + height / 2.0, text=text,
                                fill=T.COLORS.hint_text, font=fnt,
                                anchor="w", tags="hint")
        self._raise_layers()

    def _hide_hint(self):
        self.canvas.delete("hint")

    def _draw_handles(self, x1, y1, x2, y2):
        """Eight accent handles: four corners + four edge midpoints."""
        if (x2 - x1) < 24 or (y2 - y1) < 24:
            return
        size = 7.0
        half = size / 2.0
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        for cx, cy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2),
                       (mid_x, y1), (mid_x, y2), (x1, mid_y), (x2, mid_y)):
            self.canvas.create_rectangle(
                cx - half, cy - half, cx + half, cy + half,
                fill=T.COLORS.selection, outline=T.COLORS.text_on_accent,
                width=1, tags="selection")

    def _draw_size_badge(self, x1, y1, x2, y2, *, rect=None, tag="selection_badge",
                         suffix="", fill=None, outline=None, fg=None):
        """Dark mono pill showing ``W × H`` next to a rect; flips near edges."""
        screen_w, screen_h = self._screen_size()
        text = f"{int(x2 - x1)} × {int(y2 - y1)}{suffix}"
        fnt = T.FONTS.mono_small
        text_w = W.measure_text(fnt, text)
        pad_x, height, gap = 9, 22, 8
        width = text_w + pad_x * 2

        bx = x1
        if bx + width > screen_w - 4:
            bx = max(4, x2 - width)
        by = y1 - height - gap
        if by < 4:
            by = y1 + gap if y1 + gap + height <= screen_h - 4 else y1 + 4
        self._draw_pill(
            bx, by, width, height, text,
            fnt=fnt,
            fill=fill or T.COLORS.hint_bg,
            fg=fg or T.COLORS.hint_text,
            outline=outline or T.COLORS.selection,
            tags=(tag,),
        )

    def draw_selection(self, x1, y1, x2, y2):
        """Bright crop + accent frame + handles + size badge + outside dim."""
        self.canvas.delete("auto_selection")
        self.canvas.delete("selection")
        self.canvas.delete("selection_badge")
        self.canvas.delete("outside")
        if self.full_img is None:
            return

        full_w, full_h = self.full_img.width, self.full_img.height
        rx1 = int(max(0, min(x1, x2)))
        rx2 = int(min(full_w, max(x1, x2)))
        ry1 = int(max(0, min(y1, y2)))
        ry2 = int(min(full_h, max(y1, y2)))
        if rx2 <= rx1 or ry2 <= ry1:
            self._raise_layers()
            return

        # -- dim everything outside the selection so the crop really pops ----
        self._draw_outside()

        # -- the selection itself -------------------------------------------
        self.tk_sel = ImageTk.PhotoImage(self.full_img.crop((rx1, ry1, rx2, ry2)))
        self.canvas.image_sel = self.tk_sel  # pin the PhotoImage
        self.canvas.create_image(rx1, ry1, anchor="nw", image=self.tk_sel,
                                 tags="selection")
        self.canvas.create_rectangle(rx1, ry1, rx2, ry2,
                                    outline=T.COLORS.selection, width=1,
                                    tags="selection")
        self._draw_handles(rx1, ry1, rx2, ry2)
        self._draw_size_badge(rx1, ry1, rx2, ry2)
        self._selection_rect = (rx1, ry1, rx2, ry2)
        self._raise_layers()

    def _draw_outside(self):
        """Recess the desktop behind an active selection.

        A Tk ``stipple`` cannot be used here: stippled fills show the *canvas
        background* through the holes, not the image underneath, which would
        punch the desktop out instead of dimming it.  Instead one pre-darkened
        copy of the grab is laid down full-screen and the bright selection crop
        is drawn on top - the same "outside darker than inside" read that
        Snipping Tool / CleanShot give.
        """
        self.canvas.delete("outside")
        if self._dim_photo is None:
            return
        self.canvas.create_image(0, 0, anchor="nw", image=self._dim_photo,
                                 tags="outside")

    def _draw_snap_preview(self, rect):
        """Amber dashed preview + hint badge for the snap target."""
        self.canvas.delete("auto_selection")
        if not rect:
            return
        hx1, hy1, hx2, hy2 = rect
        if hx2 <= hx1 or hy2 <= hy1:
            return
        self.tk_auto_sel = ImageTk.PhotoImage(
            self.full_img.crop((hx1, hy1, hx2, hy2)))
        self.canvas.image_auto_sel = self.tk_auto_sel  # pin the PhotoImage
        self.canvas.create_image(hx1, hy1, anchor="nw", image=self.tk_auto_sel,
                                 tags="auto_selection")
        self.canvas.create_rectangle(hx1, hy1, hx2, hy2,
                                    outline=T.COLORS.selection_alt,
                                    dash=(4, 4), width=2, tags="auto_selection")
        self._draw_size_badge(
            hx1, hy1, hx2, hy2,
            tag="auto_selection", suffix="  ·  Nhấp để chụp",
            outline=T.COLORS.selection_alt)
        self._raise_layers()

    # ------------------------------------------------------------------
    # Magnifier
    # ------------------------------------------------------------------
    def update_magnifier(self, x, y):
        """Crosshair guides + rounded magnifier card with a colour readout."""
        if self.full_img is None:
            return
        full_w, full_h = self.full_img.width, self.full_img.height
        x = max(0, min(full_w - 1, int(x)))
        y = max(0, min(full_h - 1, int(y)))

        # Re-render only when the pixel under the cursor actually changed;
        # otherwise a stationary pointer would rebuild the card on every event.
        if self._mag_key == (x, y):
            return
        self._mag_key = (x, y)

        self.canvas.delete("guidelines")
        self.canvas.delete("magnifier")
        guide = T.mix(T.COLORS.selection, T.COLORS.panel, 0.45)
        self.canvas.create_line(0, y, full_w, y, fill=guide, dash=(4, 4),
                                tags="guidelines")
        self.canvas.create_line(x, 0, x, full_h, fill=guide, dash=(4, 4),
                                tags="guidelines")

        mx1, my1 = max(0, x - self.MAG_RADIUS), max(0, y - self.MAG_RADIUS)
        mx2, my2 = min(full_w, x + self.MAG_RADIUS), min(full_h, y + self.MAG_RADIUS)
        if mx2 <= mx1 or my2 <= my1:
            self._raise_layers()
            return

        mag_crop = self.full_img.crop((mx1, my1, mx2, my2))
        mag_img = mag_crop.resize((mag_crop.width * self.MAG_ZOOM,
                                   mag_crop.height * self.MAG_ZOOM), _NEAREST)
        draw = ImageDraw.Draw(mag_img)
        grid = T.mix(T.COLORS.panel, T.COLORS.text_muted, 0.55)
        step = self.MAG_ZOOM
        for i in range(0, mag_img.width, step):
            draw.line([(i, 0), (i, mag_img.height)], fill=grid, width=1)
        for i in range(0, mag_img.height, step):
            draw.line([(0, i), (mag_img.width, i)], fill=grid, width=1)
        cx_line, cy_line = mag_img.width // 2, mag_img.height // 2
        draw.line((0, cy_line, mag_img.width, cy_line), fill=T.COLORS.danger)
        draw.line((cx_line, 0, cx_line, mag_img.height), fill=T.COLORS.danger)
        draw.rectangle((0, 0, mag_img.width - 1, mag_img.height - 1),
                       outline=T.COLORS.border_strong, width=1)

        self.tk_mag = ImageTk.PhotoImage(mag_img)
        self.canvas.image_mag = self.tk_mag  # pin the PhotoImage

        pad = 6
        footer_h = 20
        card_w = mag_img.width + pad * 2
        card_h = mag_img.height + pad * 2 + footer_h
        card_x = x + 26 if x + 26 + card_w <= full_w - 8 else x - 26 - card_w
        card_y = y + 26 if y + 26 + card_h <= full_h - 8 else y - 26 - card_h
        card_x = max(8, min(full_w - card_w - 8, card_x))
        card_y = max(8, min(full_h - card_h - 8, card_y))

        T.round_rect(self.canvas, card_x, card_y, card_x + card_w,
                     card_y + card_h, T.RADIUS.sm,
                     fill=T.COLORS.panel, outline=T.COLORS.selection,
                     tags="magnifier")
        img_x = card_x + pad
        img_y = card_y + pad
        self.canvas.create_image(img_x, img_y, anchor="nw", image=self.tk_mag,
                                 tags="magnifier")

        # -- footer: coordinates (left) + pixel colour (right) --------------
        foot_y = img_y + mag_img.height + footer_h / 2.0
        self.canvas.create_text(img_x, foot_y, text=f"{x}, {y}",
                                anchor="w", fill=T.COLORS.text_secondary,
                                font=T.FONTS.mono_small, tags="magnifier")
        try:
            px = self.full_img.getpixel((x, y))[:3]
        except Exception:
            px = (0, 0, 0)
        hex_colour = "#%02X%02X%02X" % px
        right = card_x + card_w - pad
        swatch = 10
        self.canvas.create_text(right, foot_y, text=hex_colour, anchor="e",
                                fill=T.COLORS.text_primary,
                                font=T.FONTS.mono_small, tags="magnifier")
        self.canvas.create_rectangle(
            right - W.measure_text(T.FONTS.mono_small, hex_colour) - swatch - 6,
            foot_y - swatch / 2.0,
            right - W.measure_text(T.FONTS.mono_small, hex_colour) - 6,
            foot_y + swatch / 2.0,
            fill=hex_colour, outline=T.COLORS.border_strong, width=1,
            tags="magnifier")

        self._raise_layers()

    # ------------------------------------------------------------------
    # Pointer handling
    # ------------------------------------------------------------------
    def _hit_test_rect(self, x, y):
        """Smallest snap candidate under the cursor (window wins over CV)."""
        top_win = None
        for rect in getattr(self, "window_rects", []):
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                top_win = rect
                break  # topmost window only: never fall through to occluded ones

        possible_cv = [r for r in getattr(self, "cv_rects", [])
                       if r[0] <= x <= r[2] and r[1] <= y <= r[3]]
        if top_win:
            possible_cv.append(top_win)
        if not possible_cv:
            return None
        return min(possible_cv, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))

    def on_mouse_move(self, event):
        if getattr(self, "full_img", None) is None:
            return
        self.update_magnifier(event.x, event.y)

        if getattr(self, "snip_state", 0) == 1 and not self.is_dragging:
            self._hide_hint()
            self.draw_selection(self.start_x, self.start_y, event.x, event.y)
        elif getattr(self, "snip_state", 0) == 0:
            hovered = self._hit_test_rect(event.x, event.y)
            if hovered != getattr(self, "current_auto_rect", None):
                self.current_auto_rect = hovered
                if hovered:
                    self._draw_snap_preview(hovered)
                else:
                    self.canvas.delete("auto_selection")
                    self._raise_layers()

    def on_button_press(self, event):
        self.snip_state = 1          # dragging mode
        self.start_x, self.start_y = event.x, event.y
        self.is_dragging = False
        self.clicked_auto_rect = getattr(self, "current_auto_rect", None)
        self._hide_hint()

    def on_double_click(self, event):
        """Kept for API parity with the legacy binding; intentionally a no-op."""
        return None

    def on_move_press(self, event):
        if self.snip_state == 1:
            self.is_dragging = True
            self.update_magnifier(event.x, event.y)
            self.draw_selection(self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        if self.snip_state != 1:
            return
        dist = abs(event.x - self.start_x) + abs(event.y - self.start_y)
        if self.is_dragging and dist > self.DRAG_THRESHOLD:
            # Drag: finish with the freehand region.
            self.finish_snip(self.start_x, self.start_y, event.x, event.y)
        elif getattr(self, "clicked_auto_rect", None):
            # Bare click on a snap target: use the amber preview rect.
            x1, y1, x2, y2 = self.clicked_auto_rect
            self.finish_snip(x1, y1, x2, y2)
        else:
            self.is_dragging = False

    # ------------------------------------------------------------------
    # Finish / publish
    # ------------------------------------------------------------------
    def finish_snip(self, x1, y1, x2, y2):
        if self.snip_state == 0:
            return
        self.snip_state = 0
        self.is_active = False
        self._release_escape_hook()

        if self.full_img is None:
            self.cancel_snip()
            return

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        full_w, full_h = self.full_img.width, self.full_img.height
        x1, y1 = max(0, min(x1, full_w)), max(0, min(y1, full_h))
        x2, y2 = max(0, min(x2, full_w)), max(0, min(y2, full_h))

        self.canvas.delete("all")
        self.tk_dark = None
        self.current_auto_rect = None
        self._selection_rect = None
        self._mag_key = None
        try:
            self.root.withdraw()
            self.root.update()
        except tk.TclError:
            pass

        if x2 - x1 >= self.MIN_SIZE and y2 - y1 >= self.MIN_SIZE:
            cropped_img = self.full_img.crop(
                (int(x1), int(y1), int(x2), int(y2)))
            copied = self._send_to_clipboard(cropped_img)
            # The toast still offers editing if the clipboard was locked.
            self.show_toast(cropped_img, copied)
        else:
            # Below the 10x10 minimum: treat as a cancelled capture.
            self.cancel_snip()

    def show_toast(self, cropped_img, copied=True):
        """Show the result card, replacing any card still on screen."""
        if self.current_toast is not None:
            try:
                self.current_toast.destroy()
            except Exception:
                pass
        toast = ResultToast(
            self.root,
            cropped_img,
            copied=copied,
            on_open_editor=self._open_editor,
            resource_path=self._resource_path,
        )
        self.current_toast = toast
        toast.show()
        return toast


# ==========================================================================
# ResultToast
# ==========================================================================
class ResultToast:
    """Capture-result card, bottom-right of the work area.

    Layout: accent rail · thumbnail · title/subtitle · primary action ·
    ghost dismiss · close glyph · auto-dismiss progress bar.
    """

    WIDTH = T.METRICS.toast_w
    HEIGHT = 112
    MARGIN = T.SPACE.lg
    TICK_MS = 40
    _THUMB_W, _THUMB_H = 84, 64
    _TEXT_X = 130
    _CONTENT_X = 112

    def __init__(self, root, image, *, copied=True, on_open_editor=None,
                 resource_path=None, duration=6000):
        self.root = root
        self.image = image
        self.copied = bool(copied)
        self.on_open_editor = on_open_editor
        self.resource_path = resource_path
        self.duration = int(duration) if duration and duration > 0 else 6000

        self.window = None
        self.canvas = None
        self._after_ids = set()
        self._tick_id = None
        self._progress_fill = None
        self._elapsed = 0.0
        self._destroyed = False
        self._target_x = 0
        self._target_y = 0
        self._thumb_photo = None
        self._icon_photo = None
        self._buttons = []

    # -- public API -----------------------------------------------------
    def show(self):
        if self._destroyed:
            return self
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    return self
            except tk.TclError:
                pass

        window = tk.Toplevel(self.root)
        self.window = window
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass

        # Rounded corners on Windows need a chroma key; derived from the theme
        # so no raw colour literal leaks into this module.
        key = T.darken(T.COLORS.canvas_bg, 0.5)
        transparent = False
        try:
            window.attributes("-transparentcolor", key)
            transparent = True
        except tk.TclError:
            pass
        background = key if transparent else T.COLORS.border
        window.configure(bg=background)

        self._apply_window_icon()

        canvas = tk.Canvas(window, width=self.WIDTH, height=self.HEIGHT,
                           bg=background, highlightthickness=0, bd=0)
        canvas.pack()
        self.canvas = canvas

        self._paint()
        self._place()

        canvas.bind("<Button-1>", self._open_editor)
        window.bind("<Button-1>", self._open_editor)
        window.bind("<Escape>", lambda _e: self.destroy())

        self._animate_in()
        self._tick_id = self._schedule(self.TICK_MS, self._tick)
        return self

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        window = self.window
        for after_id in list(self._after_ids):
            try:
                if window is not None:
                    window.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()
        self._tick_id = None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass
        self.window = None
        self.canvas = None
        self._buttons = []

    def winfo_exists(self):
        if self._destroyed or self.window is None:
            return False
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    # -- construction helpers -------------------------------------------
    def _schedule(self, delay_ms, callback):
        window = self.window
        if window is None:
            return None
        try:
            after_id = window.after(delay_ms, callback)
        except tk.TclError:
            return None
        self._after_ids.add(after_id)
        return after_id

    def _apply_window_icon(self):
        if not callable(self.resource_path):
            return
        try:
            icon = self.resource_path("icon_ScreenShotTool.ico")
        except Exception:
            return
        try:
            if icon and os.path.exists(icon):
                self.window.iconbitmap(icon)
        except Exception:
            pass

    def _image_bytes_label(self):
        """Human-readable encoded size of the capture."""
        if self.image is None:
            return ""
        try:
            buffer = io.BytesIO()
            self.image.save(buffer, "PNG")
            size = buffer.tell()
        except Exception:
            return ""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{max(1, round(size / 1024))} KB"

    def _make_thumbnail(self):
        if self.image is None:
            return None
        try:
            source = self.image.convert("RGB")
            ratio = min(self._THUMB_W / source.width, self._THUMB_H / source.height)
            width = max(1, int(source.width * ratio))
            height = max(1, int(source.height * ratio))
            self._thumb_photo = ImageTk.PhotoImage(
                source.resize((width, height), _RESAMPLE))
        except Exception:
            self._thumb_photo = None
        return self._thumb_photo

    def _paint(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas.delete("all")
        screen_w, screen_h = self.WIDTH, self.HEIGHT

        # -- card ------------------------------------------------------------
        T.round_rect(canvas, 1, 1, screen_w - 1, screen_h - 1, T.RADIUS.md,
                     fill=T.COLORS.panel, outline=T.COLORS.border)
        rail_colour = T.COLORS.accent if self.copied else T.COLORS.warning
        T.round_rect(canvas, 2, 18, 6, screen_h - 18, 2,
                     fill=rail_colour, outline="")

        # -- thumbnail (rounded well + fitted preview) -----------------------
        box_x1, box_y1 = 16, 16
        box_x2, box_y2 = box_x1 + self._THUMB_W, box_y1 + self._THUMB_H
        T.round_rect(canvas, box_x1, box_y1, box_x2, box_y2, T.RADIUS.sm,
                     fill=T.COLORS.canvas_bg, outline=T.COLORS.border)
        photo = self._make_thumbnail()
        if photo is not None:
            cx = box_x1 + (self._THUMB_W - photo.width()) // 2
            cy = box_y1 + (self._THUMB_H - photo.height()) // 2
            canvas.create_image(cx, cy, anchor="nw", image=photo)

        # -- status glyph + title -------------------------------------------
        glyph = T.GLYPH.check if self.copied else T.GLYPH.warning
        canvas.create_text(self._CONTENT_X + 6, 26, text=glyph,
                           fill=rail_colour, font=(T.FONT_FAMILY, 11, "bold"),
                           anchor="center")
        title = ("Đã sao chép vào clipboard" if self.copied
                 else "Đã chụp màn hình")
        canvas.create_text(self._TEXT_X, 26, text=title, anchor="w",
                           fill=T.COLORS.text_primary, font=T.FONTS.body_strong)

        # -- subtitle: dimensions + encoded size -----------------------------
        dimensions = ""
        if self.image is not None:
            dimensions = f"{self.image.width} × {self.image.height} px"
        size_label = self._image_bytes_label()
        subtitle = " · ".join(part for part in (dimensions, size_label) if part)
        canvas.create_text(self._TEXT_X, 46, text=subtitle, anchor="w",
                           fill=T.COLORS.text_secondary, font=T.FONTS.small)

        # -- close glyph -----------------------------------------------------
        close_btn = W.IconButton(
            canvas, T.GLYPH.close, command=self.destroy,
            size=26, glyph_size=12, variant="ghost",
            surface=T.COLORS.panel, tooltip="Đóng")
        canvas.create_window(screen_w - 16 - 26, 10, anchor="nw", window=close_btn)
        self._buttons = [close_btn]

        # -- actions ----------------------------------------------------------
        action = W.PillButton(
            canvas, "Mở trình chỉnh sửa", command=self._open_editor,
            variant="primary", glyph=T.GLYPH.pen,
            fontspec=T.FONTS.small_strong, padx=14, height=28,
            surface=T.COLORS.panel)
        action_x = self._TEXT_X
        action_y = 58
        action_width = action.winfo_reqwidth()
        canvas.create_window(action_x, action_y, anchor="nw", window=action)

        dismiss = W.PillButton(
            canvas, "Đóng", command=self.destroy,
            variant="ghost", fontspec=T.FONTS.small_strong, padx=14,
            height=28, surface=T.COLORS.panel)
        canvas.create_window(action_x + action_width + 8, action_y, anchor="nw",
                             window=dismiss)
        self._buttons.extend([action, dismiss])

        # -- auto-dismiss progress track --------------------------------------
        track_y = screen_h - 12
        T.round_rect(canvas, 16, track_y, screen_w - 16, track_y + 4, 2,
                     fill=T.COLORS.elevated, outline="")
        self._progress_fill = None
        self._draw_progress(0.0)

    def _draw_progress(self, ratio):
        canvas = self.canvas
        if canvas is None:
            return
        if self._progress_fill is not None:
            try:
                canvas.delete(self._progress_fill)
            except tk.TclError:
                pass
            self._progress_fill = None
        ratio = max(0.0, min(1.0, float(ratio)))
        track_x1, track_x2 = 16, self.WIDTH - 16
        width = (track_x2 - track_x1) * ratio
        if width < 1:
            return
        track_y = self.HEIGHT - 12
        self._progress_fill = T.round_rect(
            canvas, track_x1, track_y, track_x1 + width, track_y + 4, 2,
            fill=T.COLORS.accent, outline="")

    # -- placement + animation -------------------------------------------
    def _place(self):
        window = self.window
        if window is None:
            return
        try:
            window.update_idletasks()
        except tk.TclError:
            return
        width, height = self.WIDTH, self.HEIGHT
        left, top, right, bottom = _work_area()
        if right is None or bottom is None:
            right = window.winfo_screenwidth()
            bottom = window.winfo_screenheight() - 40
        margin = self.MARGIN
        self._target_x = max(0, right - width - margin)
        self._target_y = max(0, bottom - height - margin)
        try:
            window.geometry(f"{width}x{height}+{self._target_x}+{self._target_y + 10}")
            window.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

    def _animate_in(self, step=0, steps=8):
        window = self.window
        if window is None or self._destroyed:
            return
        progress = min(1.0, (step + 1) / float(steps))
        try:
            window.attributes("-alpha", progress)
        except tk.TclError:
            progress = 1.0
        offset = int(round(10 * (1.0 - progress)))
        try:
            window.geometry(
                f"{self.WIDTH}x{self.HEIGHT}+{self._target_x}+{self._target_y + offset}")
        except tk.TclError:
            return
        if step + 1 < steps:
            self._schedule(16, lambda n=step + 1: self._animate_in(n, steps))

    # -- auto-dismiss ------------------------------------------------------
    def _pointer_inside(self):
        window = self.window
        if window is None:
            return False
        try:
            px, py = window.winfo_pointerxy()
            widget = window.winfo_containing(px, py)
        except Exception:
            return False
        while widget is not None:
            if widget is window:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _tick(self):
        self._tick_id = None
        if self._destroyed or self.window is None:
            return
        # Safety net: if the fade-in was starved of event-loop time the card
        # would stay semi-transparent for its whole life.  The first tick
        # guarantees full opacity and the final resting position.
        try:
            if float(self.window.attributes("-alpha")) < 1.0:
                self.window.attributes("-alpha", 1.0)
                self.window.geometry(
                    f"{self.WIDTH}x{self.HEIGHT}"
                    f"+{self._target_x}+{self._target_y}")
        except (tk.TclError, ValueError, TypeError):
            pass
        # Hovering pauses the countdown, then it resumes where it stopped.
        if not self._pointer_inside():
            self._elapsed += self.TICK_MS
        ratio = min(1.0, self._elapsed / float(self.duration))
        try:
            self._draw_progress(ratio)
        except tk.TclError:
            return
        if self._elapsed >= self.duration:
            self.destroy()
            return
        self._tick_id = self._schedule(self.TICK_MS, self._tick)

    # -- actions -----------------------------------------------------------
    def _open_editor(self, _event=None):
        callback = self.on_open_editor
        image = self.image
        self.destroy()
        if not callable(callback):
            log.info("No open_editor callback wired; capture captured only.")
            return
        try:
            callback(image)
        except Exception:
            log.exception("open_editor callback failed")
