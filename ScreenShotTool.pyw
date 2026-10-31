import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
from tkinter import Widget as _TkWidget
from PIL import ImageDraw, ImageTk, ImageEnhance, Image, ImageFilter, ImageFont
try:
    import keyboard
except ImportError:
    keyboard = None
import win32clipboard
import win32gui
import io
import ctypes
import ctypes.wintypes
import math
import random
import sys
import os
import json
import threading
import pystray
from pystray import MenuItem as item
import winreg
from pathlib import Path
from contextlib import contextmanager
from hotkey_settings import open_hotkey_settings
import time
import logging
import logging.handlers

import ui_theme as T
import ui_widgets as W
import ui_capture
import ui_dialogs
import ui_updates
from ui_editor_io import EditorExportMixin, _COPY_LABEL

def _setup_logging():
    """Log to stderr, and to a size-capped file beside the config.

    The tray app runs for days; an unbounded log file would grow without limit.
    The rotating handler caps it at ~1 MB across two files. File logging is
    best-effort: if the directory is unwritable the app still runs.
    """
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            os.path.join(CONFIG_DIR, "ScreenShotTool.log"),
            maxBytes=512 * 1024, backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)



# Optional dependencies are loaded lazily so the editor remains usable without OpenCV.
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None
try:
    import mss
except ImportError:
    mss = None

# Ẩn Console
if sys.platform == "win32":
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

APP_NAME = "ScreenShotTool"
APP_VERSION = "1.1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Where the config lives.
#
# APP_DIR was wrong for the way the exe is actually distributed: people copy it
# into Program Files, where a normal user cannot write, so every setting was
# silently lost on restart. %APPDATA% is per-user and always writable.
#
# A portable copy still wins if one is present: if a config file sits next to the
# exe, that one is used and kept next to the exe, so carrying the tool on a USB
# stick keeps its settings with it.
def _config_dir():
    portable = os.path.join(APP_DIR, "ScreenShotTool_config.json")
    if os.path.exists(portable):
        return APP_DIR
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, APP_NAME)
    return APP_DIR


CONFIG_DIR = _config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "ScreenShotTool_config.json")
# Pre-1.1 builds wrote next to the exe or into the working directory; both are
# read so an upgrade does not look like every setting was reset.
LEGACY_CONFIG_FILE = os.path.join(os.getcwd(), "ScreenShotTool_config.json")
LEGACY_CONFIG_FILE_APP_DIR = os.path.join(APP_DIR, "ScreenShotTool_config.json")
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Logging needs CONFIG_DIR, so it is configured here rather than at the top of
# the file where the handler was defined.
_setup_logging()

HOTKEY_MODIFIERS = {"ALT": 0x0001, "CTRL": 0x0002, "SHIFT": 0x0004, "WIN": 0x0008}

def validate_hotkey(value):
    """Normalize a user hotkey string; reject unsafe single modifier keys."""
    if not isinstance(value, str):
        return None
    aliases = {"CONTROL": "CTRL", "CONTROL_L": "CTRL", "CONTROL_R": "CTRL", "ESCAPE": "ESC", "RETURN": "ENTER"}
    parts = [part.strip().upper() for part in value.replace("-", "+").split("+") if part.strip()]
    parts = [aliases.get(part, part) for part in parts]
    if len(parts) < 2 or parts[-1] in HOTKEY_MODIFIERS:
        return None
    key = parts[-1]
    if len(key) != 1 and not key.startswith("F") and key not in {"DELETE", "ESC", "SPACE", "ENTER"}:
        return None
    modifiers = [part for part in parts[:-1] if part in HOTKEY_MODIFIERS]
    if not modifiers or len(set(modifiers)) != len(modifiers):
        return None
    return "+".join([*modifiers, key])

def parse_hotkey(value):
    normalized = validate_hotkey(value)
    if not normalized:
        return None
    parts = normalized.split("+")
    modifiers = 0
    for part in parts[:-1]:
        modifiers |= HOTKEY_MODIFIERS[part]
    key = parts[-1]
    if len(key) == 1:
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        vk = {"DELETE": 0x2E, "ESC": 0x1B, "SPACE": 0x20, "ENTER": 0x0D}.get(key)
    return (modifiers, vk) if vk is not None else None

def get_exe_path():
    if getattr(sys, 'frozen', False): return sys.executable
    return os.path.abspath(sys.argv[0])

def check_startup(item=None):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return value == f'"{get_exe_path()}"'
    except OSError:
        return False

def toggle_startup(icon, item):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
        if check_startup(): winreg.DeleteValue(key, APP_NAME)
        else: winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{get_exe_path()}"')
        winreg.CloseKey(key)
    except Exception:
        pass

def load_config():
    defaults = {
        "color": "#ff0000", "width": 4,
        # The *display* default keeps the human spelling "Alt+X"; the Win32
        # registrar upper-cases it itself via parse_hotkey. tests/test_transform.py
        # pins this exact string, so it is a contract, not an implementation
        # detail - do not "normalise" it here.
        "capture_hotkey": "Alt+X",
        "editor_hotkeys": {"undo": "Ctrl+Z", "redo": "Ctrl+Y", "delete": "Delete", "edit_text": "Double-click"},
    }
    try:
        candidates = [CONFIG_FILE, LEGACY_CONFIG_FILE, LEGACY_CONFIG_FILE_APP_DIR]
        seen = set()
        for path in candidates:
            if path in seen or not os.path.exists(path):
                continue
            seen.add(path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            color = data.get("color", defaults["color"])
            width = int(data.get("width", defaults["width"]))
            if not isinstance(color, str) or not color.startswith("#"):
                color = defaults["color"]
            editor_hotkeys = data.get("editor_hotkeys", defaults["editor_hotkeys"])
            if not isinstance(editor_hotkeys, dict):
                editor_hotkeys = defaults["editor_hotkeys"].copy()
            return {
                "color": color,
                "width": max(1, min(50, width)),
                "capture_hotkey": validate_hotkey(data.get("capture_hotkey", defaults["capture_hotkey"])) or defaults["capture_hotkey"],
                "editor_hotkeys": {**defaults["editor_hotkeys"], **editor_hotkeys},
            }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logging.warning("Could not load config: %s", exc)
    return defaults

def save_config(cfg):
    """Persist the config atomically, so a crash mid-write cannot eat it.

    Writing straight to CONFIG_FILE truncates it first: losing power or killing
    the process between the truncate and the final flush left a zero-byte or
    half-written JSON file behind, and the next launch silently reset every
    setting to defaults. Writing to a sibling temp file and then os.replace()
    (atomic on NTFS for same-volume renames) means the old file stays intact
    until the new one is complete.
    """
    tmp_path = CONFIG_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, CONFIG_FILE)
    except Exception:
        # Keep the app usable when the directory is read-only (e.g. the exe sits
        # in Program Files) but make the failure visible in the log instead of
        # swallowing it like the old bare `except: pass`.
        logging.warning("Could not save config to %s", CONFIG_FILE, exc_info=True)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def send_to_clipboard(image):
    """Publish PNG and CF_DIB, retrying transient clipboard locks."""
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
            win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat("PNG"), png_data)
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
            return True
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
        finally:
            if opened:
                win32clipboard.CloseClipboard()
    logging.warning("Clipboard unavailable: %s", last_error)
    return False

# ---------------------------------------------------------------------------
# Editor shell constants (design tokens come from ui_theme)
# ---------------------------------------------------------------------------
def _glyph(name):
    """Read a glyph from the theme without tripping over dict attributes.

    ``T.GLYPH`` is a ``dict`` subclass exposing keys through ``__getattr__``, so
    keys that shadow real dict methods (notably ``copy``) resolve to the method
    instead of the symbol.  Indexing always returns the symbol.
    """
    try:
        return T.GLYPH[name]
    except (KeyError, TypeError):
        return getattr(T.GLYPH, name, "")


# (tool value, caption, glyph, keyboard shortcut, status-bar hint)
_TOOL_SPEC = (
    ("select", "Chọn", _glyph("select"), "1",
     "kéo để quét chọn · Ctrl+click chọn nhiều · Ctrl+A chọn tất cả"),
    ("crop", "Cắt", _glyph("crop"), "2",
     "kéo vùng cần giữ · Enter để cắt · Esc để hủy"),
    ("erase", "Xóa", _glyph("erase"), "3", "kéo vùng để xóa pixel"),
    ("pen", "Bút", _glyph("pen"), "4", "vẽ tự do · Shift để khóa trục · cuộn chuột đổi nét"),
    ("highlight", "Dạ quang", _glyph("highlight"), "5", "kéo để tô sáng vùng"),
    ("rect", "Chữ nhật", _glyph("rect"), "6", "kéo để vẽ khung · Shift để khóa trục"),
    ("oval", "Oval", _glyph("oval"), "7", "kéo để vẽ oval · Shift để vẽ hình tròn"),
    ("arrow", "Mũi tên", _glyph("arrow"), "8", "kéo từ gốc tới đỉnh · Shift để khóa trục"),
    ("text", "Văn bản", _glyph("text"), "9", "click để nhập chữ · Enter xong · Esc hủy"),
    ("blur", "Làm mờ", _glyph("blur"), "0", "kéo vùng cần làm mờ"),
)

_TOOL_VALUES = [spec[0] for spec in _TOOL_SPEC]

# Rail width once the layout tightens below 900px.  Wide enough to keep the
# longest tool caption ("Dạ quang", 51px at the 8pt caption face) legible, so
# every tool keeps its label at every window size.
_RAIL_W_COMPACT = 64

# Narrowest width at which the inspector can be docked beside the canvas.  Below
# it the panel floats over the canvas instead of vanishing, so the controls it
# holds stay reachable down to the app minimum width (760 px).
_INSPECTOR_DOCK_MIN = 1180

# _COPY_LABEL is imported from ui_editor_io, where the Copy button logic lives.


class _CopyPill(W.PillButton):
    """Primary pill whose label can be swapped at runtime.

    ``save_clipboard`` rewrites the caption to "✔ Đã Copy!" / "✖ Clipboard lỗi"
    and restores it 2 s later.  ``PillButton`` only re-measures its width in
    ``set_text``, so the classic ``config(text=...)`` dialect is routed there to
    keep the longer confirmation text inside the rounded background.
    """

    def configure(self, cget=False, **kwargs):
        if "text" in kwargs:
            value = kwargs.pop("text")
            self.set_text("" if value is None else str(value))
        if kwargs:
            super().configure(cget=cget, **kwargs)
        return None

    config = configure



class _ToolRailButton(W.RailButton):
    """RailButton that keeps the glyph optically centred when running captionless.

    ``W.RailButton`` always reserves a caption line, which leaves the glyph 7px
    above centre once the caption is empty (compact rail on narrow windows).
    Only the captionless case is overridden; captioned rendering is the frozen
    widget's.
    """

    def _render(self):
        if self.caption:
            return super()._render()
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        selected = self._selected()
        enabled = self._is_enabled()
        if selected:
            bg, fg = T.COLORS.accent_soft, T.COLORS.accent_hover
        elif self._pressed:
            bg, fg = T.COLORS.border, T.COLORS.text_primary
        elif self._hovering and enabled:
            bg, fg = T.COLORS.hover, T.COLORS.text_primary
        else:
            bg, fg = T.COLORS.chrome, T.COLORS.text_secondary
        if not enabled:
            fg = T.COLORS.text_muted
        T.round_rect(self, 4, 3, w - 4, h - 3, self._radius, fill=bg, outline="")
        if selected:
            self.create_rectangle(4, 10, 6, h - 10, fill=T.COLORS.accent, outline="")
        self.create_text(w / 2, h / 2, text=self.glyph, fill=fg,
                         font=(T.FONT_FAMILY, 16))


class ImageEditor(EditorExportMixin):
    # Looked up on each call instead of captured at construction, so tests that
    # replace the module-level clipboard writer still take effect.
    send_to_clipboard = property(lambda self: globals()["send_to_clipboard"])

    def __init__(self, root, pil_image):
        self.top = tk.Toplevel(root)
        self.top.title(f"{APP_NAME} — Trình chỉnh sửa ảnh")
        try:
            self.top.iconbitmap(resource_path("icon_ScreenShotTool.ico"))
        except Exception:
            pass
        T.apply_theme(self.top)
        T.apply_dark_titlebar(self.top)

        self.pil_image = pil_image.copy().convert("RGBA")
        self.orig_w, self.orig_h = self.pil_image.width, self.pil_image.height
        self.scale = 1.0
        self.offset_x = 0; self.offset_y = 0
        
        self.shapes = []
        self.shape_counter = 0
        self.selected_tag = None
        self.selected_tags = []
        self.selection_marquee = False
        self.text_entry = None
        self.editing_tag = None
        self._syncing_text_style = False
        self.crop_pending = False
        self.history = []
        self.history_index = -1
        self.last_mouse_x = -100
        self.last_mouse_y = -100
        self._tk_images = []

        self.cfg = load_config()
        self.capture_hotkey_var = tk.StringVar(value=self.cfg.get("capture_hotkey", "Alt+X"))
        self.tool_var = tk.StringVar(value="select")
        self.color_var = tk.StringVar(value=self.cfg.get("color", "#ff0000"))
        self.width_var = tk.IntVar(value=self.cfg.get("width", 4))
        self.text_bg_var = tk.BooleanVar(value=False)
        self.palette = ["#ff0000", "#ffaa00", "#ffff00", "#00aa00", "#0088ff", "#aa00ff", "#000000", "#ffffff"]
        if self.color_var.get() not in self.palette: self.palette.append(self.color_var.get())
        
        self.color_var.trace_add("write", lambda *args: self._update_config())
        self.width_var.trace_add("write", lambda *args: self._update_config())
        self.tool_var.trace_add("write", lambda *args: self.update_custom_cursor())
        self.text_bg_var.trace_add("write", lambda *args: self._on_text_bg_change())

        # --- shell state ---------------------------------------------------
        self._metrics = {"zoom": self.scale,
                         "size": (self.orig_w, self.orig_h),
                         "cursor": None, "selection": None}
        self._cursor_after_id = None
        self._copy_reset_id = None
        self._inspector_visible = True
        self._inspector_overlay = False
        self._brand_subtitle_visible = True
        self._rail_compact = False
        self._last_layout_width = 0

        self.top.minsize(760, 520)

        # The bottom strip is packed before the expanding body, otherwise the
        # body would consume the whole cavity and squeeze the status bar out.
        self.statusbar = W.StatusBar(self.top)
        self.statusbar.pack(side="bottom", fill="x")

        self._build_toolbar()      # header + tool rail + right inspector
        self._build_canvas_area()  # centre stage; keeps self.canvas semantics

        self.tool_var.trace_add("write", lambda *args: self._on_tool_changed())
        self.color_var.trace_add("write", lambda *args: self._sync_color_widgets())
        self.width_var.trace_add("write", lambda *args: self._sync_width_widgets())
        self.top.bind("<Configure>", self._on_editor_resize)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<ButtonPress-2>", self.on_middle_press)
        self.canvas.bind("<B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_middle_release)
        self.canvas.bind("<Motion>", self.on_mouse_move_editor)
        self.canvas.bind("<Configure>", lambda e: self.redraw_all())
        
        hotkeys = self.cfg.get("editor_hotkeys", {})
        self.top.bind("<Delete>", self.delete_selected)
        self.top.bind("<MouseWheel>", self.on_mouse_wheel)
        self.top.bind("<Control-MouseWheel>", self.on_mouse_wheel)
        self.top.bind_all("<Control-z>", lambda e: (self.undo(), "break")[1])
        self.top.bind_all("<Control-y>", lambda e: (self.redo(), "break")[1])
        self.top.bind_all("<Control-c>", lambda e: (self.save_clipboard(), "break")[1])
        self.top.bind_all("<Control-s>", lambda e: (self.save_file(), "break")[1])
        self.top.bind_all("<Control-a>", lambda e: (self.handle_select_all_shortcut(), "break")[1])
        for sequence, delta in (("<Left>", (-1, 0)), ("<Right>", (1, 0)), ("<Up>", (0, -1)), ("<Down>", (0, 1))):
            self.top.bind_all(sequence, lambda e, dx=delta[0], dy=delta[1]: (self.move_selected_by(dx * (10 if e.state & 0x0001 else 1), dy * (10 if e.state & 0x0001 else 1)), "break")[1])
        self.top.bind_all("<Return>", lambda e: (self.confirm_crop(), "break")[1] if self.tool_var.get() == "crop" else None)
        # Escape is handled in one place, in priority order: cancel an in-progress
        # crop/text edit first, otherwise dismiss a floating inspector. Keeping a
        # second bind_all("<Escape>") further down looked correct but the one
        # below returned "break", which stops Tk from running any later handler
        # on the same tag - so the inspector dismissal was unreachable.
        self.top.bind_all("<Escape>", self._on_escape)
        for index, value in enumerate(_TOOL_VALUES):
            key = "0" if index == 9 else str(index + 1)
            self.top.bind_all(f"<KeyPress-{key}>", lambda e, v=value: self._on_tool_hotkey(e, v))
        self._refresh_editor_hotkeys()

        self.start_cx = None; self.start_cy = None
        self.prev_cx = None; self.prev_cy = None
        self.axis_locked = None; self.has_moved = False
        self.save_state()
        self._on_tool_changed()
        self._sync_history_buttons()

        # Maximise only where the layout actually fits; otherwise a sane window.
        screen_w = self.top.winfo_screenwidth()
        screen_h = self.top.winfo_screenheight()
        try:
            if screen_w >= 1600 and screen_h >= 900:
                self.top.state("zoomed")
            else:
                T.center_window(self.top, min(1280, screen_w - 80), min(860, screen_h - 120))
        except tk.TclError:
            T.center_window(self.top, 1280, 800)
        self.top.after(60, self.redraw_all)
        # Drop the pending Copy confirmation when the window goes away, so Tk
        # never fires an "after" script whose widget no longer exists.
        self.top.bind("<Destroy>", self._on_top_destroy, add="+")

        self.canvas.bind("<ButtonPress-1>", self._dismiss_inspector_overlay, add="+")

    def _on_escape(self, _event=None):
        """Single Escape handler: cancel an active edit, else close the drawer.

        ``cancel_crop_or_text`` returns nothing, so the state is snapshotted to
        tell whether it actually did something: only an open text editor, a
        pending crop, or a live selection count as "the key was consumed".
        Otherwise Escape falls through to dismissing a floating inspector.
        Returns None rather than "break" so other Escape bindings still run.
        """
        had_text = bool(self.text_entry)
        had_crop = bool(getattr(self, "crop_pending", False))
        had_selection = bool(self.selected_tag)
        try:
            self.cancel_crop_or_text()
        except Exception:
            logging.exception("cancel_crop_or_text failed")
        consumed = had_text or had_crop or had_selection
        if not consumed:
            self._dismiss_inspector_overlay()
        return None

    def _dismiss_inspector_overlay(self, _event=None):
        if not getattr(self, "_inspector_overlay", False):
            return None
        self._inspector_visible = False
        self._last_layout_width = 0
        self._apply_layout(self.top.winfo_width())
        return None

    def _on_top_destroy(self, event=None):
        if event is not None and event.widget is not self.top:
            return
        self._cancel_copy_reset()
        if self._cursor_after_id is not None:
            try:
                self.top.after_cancel(self._cursor_after_id)
            except tk.TclError:
                pass
            self._cursor_after_id = None

    # ------------------------------------------------------------------
    # Shell construction
    # ------------------------------------------------------------------
    def _build_canvas_area(self):
        """Centre stage: the screenshot on a dark surface, plus both scrollbars."""
        self.body = tk.Frame(self.top, bg=T.COLORS.app)
        self.body.pack(side="left", fill="both", expand=True)

        self.canvas_frame = tk.Frame(self.body, bg=T.COLORS.canvas_bg)
        self.canvas_frame.pack(fill="both", expand=True)

        # Tk packs later siblings into the remaining cavity, so the horizontal
        # scrollbar must be packed before the canvas grows.
        self.h_scroll = ttk.Scrollbar(self.canvas_frame, orient="horizontal",
                                      style=T.STYLE_HSCROLL)
        self.h_scroll.pack(side="bottom", fill="x")
        self.v_scroll = ttk.Scrollbar(self.canvas_frame, orient="vertical",
                                      style=T.STYLE_VSCROLL)
        self.v_scroll.pack(side="right", fill="y")

        stage = tk.Frame(self.canvas_frame, bg=T.COLORS.canvas_bg,
                         highlightthickness=0)
        stage.pack(side="left", fill="both", expand=True, padx=T.SPACE.sm, pady=T.SPACE.sm)

        self.canvas = tk.Canvas(stage, bg=T.COLORS.canvas_bg, cursor="cross",
                                highlightthickness=0, borderwidth=0,
                                xscrollcommand=self.h_scroll.set,
                                yscrollcommand=self.v_scroll.set)
        self.canvas.pack(fill="both", expand=True)
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

    def _build_toolbar(self):
        """Build the header bar, the left tool rail and the right inspector.

        Keeps its historical name: the contract requires ``_build_toolbar`` to
        create ``btn_undo``, ``btn_redo``, ``btn_copy``, ``color_btn`` and
        ``width_cb`` and to delegate to undo / redo / save_file /
        save_clipboard / pick_color.
        """
        # ---- header -------------------------------------------------------
        self.header = tk.Frame(self.top, bg=T.COLORS.chrome,
                               height=T.METRICS.toolbar_h)
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)
        tk.Frame(self.header, bg=T.COLORS.border, height=1).pack(side="bottom", fill="x")

        brand = tk.Frame(self.header, bg=T.COLORS.chrome)
        brand.pack(side="left", padx=(T.SPACE.lg, 0))

        self._logo = tk.Canvas(brand, width=30, height=30, bg=T.COLORS.chrome,
                               highlightthickness=0, borderwidth=0)
        self._logo.pack(side="left")
        T.round_rect(self._logo, 1, 1, 29, 29, T.RADIUS.sm,
                     fill=T.COLORS.accent_soft, outline=T.COLORS.border_strong)
        self._logo.create_text(15, 15, text=_glyph("image"), fill=T.COLORS.accent_hover,
                               font=(T.FONT_FAMILY, 12))

        brand_text = tk.Frame(brand, bg=T.COLORS.chrome)
        brand_text.pack(side="left", padx=(T.SPACE.sm, 0))
        tk.Label(brand_text, text=APP_NAME, bg=T.COLORS.chrome,
                 fg=T.COLORS.text_primary, font=T.FONTS.subheading,
                 anchor="w").pack(anchor="w")
        self._brand_subtitle = tk.Label(
            brand_text, text=f"Ảnh đã chụp · {self.orig_w}×{self.orig_h}",
            bg=T.COLORS.chrome, fg=T.COLORS.text_muted, font=T.FONTS.tiny,
            anchor="w")
        self._brand_subtitle.pack(anchor="w")

        actions = tk.Frame(self.header, bg=T.COLORS.chrome)
        actions.pack(side="right", padx=(0, T.SPACE.lg))

        self.btn_inspector_toggle = W.IconButton(
            self.header, _glyph("settings"), command=self.toggle_inspector,
            size=34, glyph_size=15, tooltip="Bảng thuộc tính")
        self.btn_inspector_toggle.pack(side="right", padx=(T.SPACE.sm, 0))

        self.btn_info = W.IconButton(
            self.header, _glyph("info"), command=self.show_function_info,
            size=34, glyph_size=15, tooltip="Thông tin & phím tắt")
        self.btn_info.pack(side="right", padx=(T.SPACE.sm, 0))

        W.Divider(self.header, orient="vertical").pack(side="right", fill="y",
                                                       pady=T.SPACE.md,
                                                       padx=(T.SPACE.md, T.SPACE.sm))

        self.btn_copy = _CopyPill(
            actions, _COPY_LABEL, command=self.save_clipboard, variant="primary",
            glyph=_glyph("copy"), fontspec=T.FONTS.body_strong, padx=14,
            tooltip="Copy ảnh vào clipboard  (Ctrl+C)", min_width=104)
        self.btn_copy.pack(side="right", padx=(T.SPACE.sm, 0))

        self.btn_save = W.PillButton(
            actions, "Lưu", command=self.save_file, variant="secondary",
            glyph=_glyph("save"), fontspec=T.FONTS.body_strong, padx=14,
            tooltip="Lưu ra tệp PNG / JPEG  (Ctrl+S)", min_width=92)
        self.btn_save.pack(side="right")

        # ---- left tool rail ----------------------------------------------
        self.rail = tk.Frame(self.top, bg=T.COLORS.chrome, width=T.METRICS.rail_w)
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)
        tk.Frame(self.rail, bg=T.COLORS.border, width=1).pack(side="right", fill="y")

        rail_inner = tk.Frame(self.rail, bg=T.COLORS.chrome)
        rail_inner.pack(fill="both", expand=True, pady=T.SPACE.sm)
        self._rail_button_parent = rail_inner
        self._build_rail_buttons()

        # ---- right inspector ---------------------------------------------
        self.inspector = tk.Frame(self.top, bg=T.COLORS.panel,
                                  width=T.METRICS.sidebar_w)
        self.inspector.pack(side="right", fill="y")
        self.inspector.pack_propagate(False)
        tk.Frame(self.inspector, bg=T.COLORS.border, width=1).pack(side="left", fill="y")

        inspector_body = tk.Frame(self.inspector, bg=T.COLORS.panel)
        inspector_body.pack(side="left", fill="both", expand=True)
        self._inspector_body = inspector_body
        self._build_inspector(inspector_body)

    def _sync_overlay_close(self, floating):
        """Show a close glyph on the inspector only while it floats.

        Docked, the header gear is enough.  Floating, the panel needs a visible
        way out so Escape is a shortcut rather than the only escape.
        """
        close = getattr(self, "_inspector_close", None)
        if floating:
            if close is None:
                close = W.IconButton(
                    self.inspector, T.GLYPH.close,
                    command=self._dismiss_inspector_overlay,
                    size=24, glyph_size=11, variant="ghost",
                    surface=T.COLORS.panel, tooltip="Đóng bảng thuộc tính  (Esc)")
                self._inspector_close = close
            close.place(relx=1.0, x=-8, y=8, anchor="ne")
            # W.IconButton paints on a Canvas, so its own ``lift`` is the canvas
            # tag-raise; raise the widget in the stacking order instead.
            _TkWidget.lift(close)
        elif close is not None:
            try:
                close.place_forget()
            except tk.TclError:
                pass

    def _build_rail_buttons(self):
        for child in self._rail_button_parent.winfo_children():
            child.destroy()
        self.rail_buttons = {}
        compact = self._rail_compact
        # Below 900px the rail gets tighter (shorter buttons, no footer), but the
        # captions stay: "Làm mờ" measured against the compact rail and fits, and
        # a bare glyph for one tool but a label for the other nine reads as a bug.
        rail_w = _RAIL_W_COMPACT if compact else T.METRICS.rail_w
        self.rail.config(width=rail_w)
        for value, caption, glyph, shortcut, hint in _TOOL_SPEC:
            button = _ToolRailButton(
                self._rail_button_parent, glyph, caption,
                value, self.tool_var,
                width=rail_w - 16,
                height=40 if compact else 52,
                command=self.clear_selection,
                tooltip=f"{caption}  ({shortcut})")
            button.pack(pady=1)
            self.rail_buttons[value] = button
        if not compact:
            self._build_rail_footer()

    def _build_rail_footer(self):
        footer = tk.Frame(self._rail_button_parent, bg=T.COLORS.chrome)
        footer.pack(side="bottom", pady=(T.SPACE.sm, 0))
        self._rail_shortcut_hint = tk.Label(
            footer, text=_glyph("keyboard"), bg=T.COLORS.chrome,
            fg=T.COLORS.text_muted, font=(T.FONT_FAMILY, 13))
        self._rail_shortcut_hint.pack()
        self.rail_buttons_tooltip = W.Tooltip(
            self._rail_shortcut_hint, "Phím 1–0 chuyển nhanh công cụ")

    def _build_inspector(self, master):
        # ---- history ------------------------------------------------------
        section = W.InspectorSection(master, "Lịch sử")
        section.pack(fill="x")
        row = tk.Frame(section.body, bg=T.COLORS.panel)
        row.pack(fill="x")
        self.btn_undo = W.IconButton(row, _glyph("undo"), command=self.undo,
                                     size=T.METRICS.control_h, glyph_size=16,
                                     surface=T.COLORS.panel,
                                     tooltip="Hoàn tác  (Ctrl+Z)")
        self.btn_undo.pack(side="left")
        self.btn_redo = W.IconButton(row, _glyph("redo"), command=self.redo,
                                     size=T.METRICS.control_h, glyph_size=16,
                                     surface=T.COLORS.panel,
                                     tooltip="Làm lại  (Ctrl+Y)")
        self.btn_redo.pack(side="left", padx=(T.SPACE.sm, 0))
        self.history_label = tk.Label(row, text="", bg=T.COLORS.panel,
                                      fg=T.COLORS.text_muted, font=T.FONTS.mono_small,
                                      anchor="e")
        self.history_label.pack(side="right")

        # ---- stroke width -------------------------------------------------
        section = W.InspectorSection(master, "Nét vẽ")
        section.pack(fill="x")
        self.width_slider = W.Slider(section.body, self.width_var, minimum=1,
                                     maximum=50, width=T.METRICS.sidebar_w - 32,
                                     command=lambda *_: self.update_custom_cursor())
        self.width_slider.pack(fill="x")
        width_row = tk.Frame(section.body, bg=T.COLORS.panel)
        width_row.pack(fill="x", pady=(T.SPACE.sm, 0))
        self.width_cb = W.NumberStepper(
            width_row, self.width_var, minimum=1, maximum=50,
            width=T.METRICS.sidebar_w - 32,
            command=lambda *_: self.update_custom_cursor(),
            tooltip="Độ dày nét (1–50) · cuộn chuột trên canvas cũng đổi")
        self.width_cb.pack(fill="x")

        # ---- colour -------------------------------------------------------
        section = W.InspectorSection(master, "Màu sắc")
        section.pack(fill="x")
        color_row = tk.Frame(section.body, bg=T.COLORS.panel)
        color_row.pack(fill="x")
        self.color_btn = W.ColorSwatch(
            color_row, self.color_var.get(), command=self._on_swatch_color,
            random_command=self.random_color, palette=list(self.palette),
            size=T.METRICS.control_h,
            tooltip="Chọn màu · chuột phải để pha màu · cuộn để đổi nhanh")
        self.color_btn.pack(side="left")
        self.color_value_label = tk.Label(
            color_row, text=self.color_var.get().upper(), bg=T.COLORS.panel,
            fg=T.COLORS.text_secondary, font=T.FONTS.mono, anchor="w")
        self.color_value_label.pack(side="left", padx=(T.SPACE.sm, 0))
        self.btn_random_color = W.IconButton(
            color_row, _glyph("random"), command=self.random_color, size=28,
            glyph_size=14, surface=T.COLORS.panel, tooltip="Màu ngẫu nhiên")
        self.btn_random_color.pack(side="right")
        self.btn_pick_color = W.IconButton(
            color_row, _glyph("magnifier"), command=self.pick_color, size=28,
            glyph_size=14, surface=T.COLORS.panel, tooltip="Bảng màu tùy chỉnh")
        self.btn_pick_color.pack(side="right", padx=(0, T.SPACE.xs))

        # ---- text ---------------------------------------------------------
        section = W.InspectorSection(master, "Văn bản")
        section.pack(fill="x")
        self.text_bg_toggle = W.ToggleSwitch(
            section.body, self.text_bg_var, "Tô nền chữ",
            width=T.METRICS.sidebar_w - 32)
        self.text_bg_toggle.pack(fill="x")

        # ---- zoom ---------------------------------------------------------
        section = W.InspectorSection(master, "Thu phóng")
        section.pack(fill="x")
        zoom_row = tk.Frame(section.body, bg=T.COLORS.panel)
        zoom_row.pack(fill="x")
        self.btn_zoom_out = W.IconButton(
            zoom_row, _glyph("zoom_out"), command=lambda: self.set_zoom(0.8),
            size=28, glyph_size=14, surface=T.COLORS.panel,
            tooltip="Thu nhỏ  (Ctrl + cuộn chuột)")
        self.btn_zoom_out.pack(side="left")
        self.btn_zoom_reset = W.IconButton(
            zoom_row, _glyph("target"), command=lambda: self.set_zoom(0),
            size=28, glyph_size=14, surface=T.COLORS.panel,
            tooltip="Về tỉ lệ 1:1")
        self.btn_zoom_reset.pack(side="left", padx=T.SPACE.xs)
        self.btn_zoom_in = W.IconButton(
            zoom_row, _glyph("zoom_in"), command=lambda: self.set_zoom(1.25),
            size=28, glyph_size=14, surface=T.COLORS.panel,
            tooltip="Phóng to  (Ctrl + cuộn chuột)")
        self.btn_zoom_in.pack(side="left")
        self.zoom_label = tk.Label(zoom_row, text="100%", bg=T.COLORS.panel,
                                   fg=T.COLORS.text_secondary,
                                   font=T.FONTS.mono, anchor="e")
        self.zoom_label.pack(side="right")

        # ---- transforms ---------------------------------------------------
        section = W.InspectorSection(master, "Biến đổi")
        section.pack(fill="x")
        transform_row = tk.Frame(section.body, bg=T.COLORS.panel)
        transform_row.pack(fill="x")
        for glyph, operation, tip in (
            (_glyph("flip_h"), "flip_h", "Lật ngang"),
            (_glyph("flip_v"), "flip_v", "Lật dọc"),
            (_glyph("rotate_ccw"), "rotate_ccw", "Xoay trái 90°"),
            (_glyph("rotate_cw"), "rotate_cw", "Xoay phải 90°"),
        ):
            button = W.IconButton(
                transform_row, glyph,
                command=lambda op=operation: self.transform_selection_or_document(op),
                size=28, glyph_size=15, surface=T.COLORS.panel, tooltip=tip)
            button.pack(side="left", padx=(0, T.SPACE.xs))

        hint = tk.Label(section.body,
                        text="Áp dụng cho vùng chọn, hoặc toàn ảnh nếu chưa chọn.",
                        bg=T.COLORS.panel, fg=T.COLORS.text_muted,
                        font=T.FONTS.tiny, anchor="w", wraplength=T.METRICS.sidebar_w - 40,
                        justify="left")
        hint.pack(fill="x", pady=(T.SPACE.xs, 0))

    # ------------------------------------------------------------------
    # Shell behaviour: tool hints, responsive layout, live metrics
    # ------------------------------------------------------------------
    def _tool_hint(self, value=None):
        value = value if value is not None else self.tool_var.get()
        for tool_value, caption, _glyph, _shortcut, hint in _TOOL_SPEC:
            if tool_value == value:
                return f"{caption}: {hint}"
        return "Sẵn sàng · chọn công cụ ở thanh bên trái"

    def _on_tool_changed(self):
        self.update_custom_cursor()
        self.statusbar.set_hint(self._tool_hint())
        self._refresh_metrics()

    def _on_tool_hotkey(self, event, value):
        # Never steal digits while the user is typing into the text entry.
        if self.text_entry is not None and self.top.focus_get() is self.text_entry:
            return None
        if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return None
        self.tool_var.set(value)
        self.clear_selection()
        return "break"

    def _sync_color_widgets(self):
        color = self.color_var.get()
        swatch = getattr(self, "color_btn", None)
        if swatch is not None:
            try:
                swatch.set_color(color)
            except Exception:
                pass
        label = getattr(self, "color_value_label", None)
        if label is not None:
            try:
                label.config(text=color.upper())
            except tk.TclError:
                pass

    def _sync_width_widgets(self):
        # Slider and NumberStepper repaint from their own variable traces; this
        # keeps the brush preview in sync when the value changes from elsewhere.
        if hasattr(self, "canvas"):
            self.update_custom_cursor()

    def _sync_history_buttons(self):
        try:
            self.update_history_ui()
        except tk.TclError:
            pass

    def _on_swatch_color(self, color=None):
        """Colour chosen from the swatch palette."""
        if color:
            self.color_var.set(color)
            self.apply_color_to_selected()

    def toggle_inspector(self):
        self._inspector_visible = not self._inspector_visible
        self._last_layout_width = 0
        self._apply_layout(self.top.winfo_width())

    def _on_editor_resize(self, event=None):
        if event is not None and event.widget is not self.top:
            return
        self._apply_layout(self.top.winfo_width())

    # -- inspector placement ------------------------------------------------
    def _show_inspector_overlay(self):
        """Float the inspector over the canvas when there is no room to dock it.

        Below the dock breakpoint the panel cannot share the window with the
        canvas, but the controls it holds (colour, stroke, zoom, transform,
        undo/redo) must stay reachable at every size the window allows.  So it
        becomes a drawer pinned to the right edge instead of disappearing.
        """
        if self.inspector.winfo_manager() == "pack":
            self.inspector.pack_forget()
        header_h = getattr(self, "header", None)
        header_h = max(1, header_h.winfo_height()) if header_h is not None else 1
        status_h = max(0, self.statusbar.winfo_height())
        height = max(1, self.top.winfo_height() - header_h - status_h)
        self.inspector.place(relx=1.0, y=header_h, anchor="ne",
                             width=T.METRICS.sidebar_w, height=height)
        self.inspector.lift()
        # A floating panel must announce itself as an overlay: a soft shadow
        # strip on its left edge separates it from the canvas, and the header
        # gains a close glyph so the Escape/canvas-click dismissal is
        # discoverable rather than something the user has to guess.
        if not getattr(self, "_overlay_shadow", None):
            self._overlay_shadow = tk.Frame(self.top, bg=T.COLORS.border_strong,
                                            width=2)
        self._overlay_shadow.place(relx=1.0, y=header_h,
                                   x=-T.METRICS.sidebar_w - 2,
                                   anchor="nw", width=2, height=height)
        self._overlay_shadow.lift()
        self._sync_overlay_close(True)
        self._inspector_overlay = True

    def _hide_inspector_overlay(self):
        shadow = getattr(self, "_overlay_shadow", None)
        if shadow is not None:
            try:
                shadow.place_forget()
            except tk.TclError:
                pass
        self._sync_overlay_close(False)
        if self.inspector.winfo_manager() == "place":
            self.inspector.place_forget()
        self._inspector_overlay = False

    def _apply_layout(self, width):
        """Responsive shell: dock, float, or hide the inspector; tune the rail."""
        if width <= 1 or width == self._last_layout_width:
            return
        self._last_layout_width = width

        docked = width >= _INSPECTOR_DOCK_MIN
        if self._inspector_visible and docked:
            self._hide_inspector_overlay()
            if self.inspector.winfo_manager() != "pack":
                self.inspector.pack(side="right", fill="y", before=self.body)
        elif self._inspector_visible:
            self._show_inspector_overlay()
        else:
            self._hide_inspector_overlay()
            if self.inspector.winfo_manager() == "pack":
                self.inspector.pack_forget()

        compact = width < 900
        if compact != self._rail_compact:
            self._rail_compact = compact
            self._build_rail_buttons()

        show_subtitle = width >= 1040
        if show_subtitle != self._brand_subtitle_visible:
            self._brand_subtitle_visible = show_subtitle
            if show_subtitle:
                self._brand_subtitle.pack(anchor="w")
            else:
                self._brand_subtitle.pack_forget()

    # ------------------------------------------------------------------
    # Live status readouts
    # ------------------------------------------------------------------
    def _refresh_metrics(self, cursor=None, selection=None):
        if cursor is not None:
            self._metrics["cursor"] = cursor
        if selection is not None:
            self._metrics["selection"] = selection
        self._metrics["zoom"] = self.scale
        self._metrics["size"] = (self.orig_w, self.orig_h)
        if not hasattr(self, "statusbar"):
            return
        self.statusbar.set_metrics(
            size=self._metrics["size"],
            zoom=self._metrics["zoom"],
            cursor=self._metrics["cursor"],
            selection=self._metrics["selection"],
            history=f"{self.history_index + 1}/{len(self.history)}",
        )
        label = getattr(self, "zoom_label", None)
        if label is not None:
            try:
                label.config(text=f"{int(round(self.scale * 100))}%")
            except tk.TclError:
                pass
        subtitle = getattr(self, "_brand_subtitle", None)
        if subtitle is not None:
            try:
                subtitle.config(text=f"Ảnh đã chụp · {self.orig_w}×{self.orig_h}")
            except tk.TclError:
                pass

    def _schedule_cursor_metrics(self, cx, cy):
        """Throttle cursor readouts to one update per ~40ms while dragging."""
        ix = int(round((cx - self.offset_x) / self.scale)) if self.scale else 0
        iy = int(round((cy - self.offset_y) / self.scale)) if self.scale else 0
        self._pending_cursor = (ix, iy)
        if self._cursor_after_id is not None:
            return
        self._cursor_after_id = self.top.after(40, self._flush_cursor_metrics)

    def _flush_cursor_metrics(self):
        self._cursor_after_id = None
        self._refresh_metrics(cursor=getattr(self, "_pending_cursor", None))

    def _selection_size(self):
        tags = self.selected_tags or ([self.selected_tag] if self.selected_tag else [])
        if not tags:
            return None
        x1 = y1 = float("inf")
        x2 = y2 = float("-inf")
        for tag in tags:
            shape = next((item for item in self.shapes if item.get('tag') == tag), None)
            if not shape:
                continue
            sx1, sy1, sx2, sy2 = self._shape_bounds(shape)
            x1, y1 = min(x1, sx1), min(y1, sy1)
            x2, y2 = max(x2, sx2), max(y2, sy2)
        if x1 > x2:
            return None
        return (max(0, int(round(x2 - x1))), max(0, int(round(y2 - y1))))

    def _tk_sequence(self, shortcut):
        if not isinstance(shortcut, str) or shortcut.lower() in {"double-click", ""}:
            return None
        if shortcut.strip().lower() == 'delete':
            return '<Delete>'
        parts = [part.strip().lower() for part in shortcut.replace('-', '+').split('+') if part.strip()]
        if len(parts) < 2:
            return None
        key = parts[-1]
        mods = {'ctrl': 'Control', 'control': 'Control', 'alt': 'Alt', 'shift': 'Shift'}
        modifier_text = '-'.join(mods[p] for p in parts[:-1] if p in mods)
        if not modifier_text:
            return None
        return f"<{modifier_text}-{key}>"

    def _refresh_editor_hotkeys(self):
        for sequence in getattr(self, '_custom_hotkey_sequences', []):
            self.top.unbind(sequence)
        self._custom_hotkey_sequences = []
        hotkeys = self.cfg.get('editor_hotkeys', {})
        for shortcut, callback in ((hotkeys.get('undo'), self.undo), (hotkeys.get('redo'), self.redo), (hotkeys.get('delete'), self.delete_selected)):
            sequence = self._tk_sequence(shortcut)
            if sequence:
                self.top.bind(sequence, callback)
                self._custom_hotkey_sequences.append(sequence)

    def _on_text_bg_change(self):
        self.update_custom_cursor()
        if self._syncing_text_style or not self.selected_tag:
            return
        shape = next((item for item in self.shapes if item.get('tag') == self.selected_tag), None)
        if shape and (shape.get('type') == 'text' or shape.get('source_type') == 'text'):
            shape['bg_enabled'] = bool(self.text_bg_var.get())
            if shape.get('type') == 'bitmap':
                self._rebuild_text_bitmap(shape)
            self.redraw_all()
            self.save_state()

    def _update_config(self):
        self.cfg["color"] = self.color_var.get()
        self.cfg["width"] = self.width_var.get()
        save_config(self.cfg)
        self.update_custom_cursor()

    def _save_hotkey_config(self, config):
        self.cfg = config
        save_config(self.cfg)
        self.capture_hotkey_var.set(self.cfg.get('capture_hotkey', 'Alt+X'))
        self._refresh_editor_hotkeys()

    def show_function_info(self):
        """Modern info / shortcut guide (see :mod:`ui_dialogs`)."""
        return ui_dialogs.open_info_dialog(
            self.top, self.cfg, on_open_hotkeys=self.open_hotkey_settings,
            app_version=APP_VERSION)

    def open_hotkey_settings(self):
        """Editable hotkey card, wired to the same config the tray hotkey reads."""
        return ui_dialogs.open_hotkey_dialog(
            self.top, self.cfg, self._save_hotkey_config)

    def show_shortcuts_dialog(self):
        """Legacy typed shortcut editor, kept for the existing call sites."""
        return ui_dialogs.open_shortcuts_dialog(
            self.top, self.cfg, save_callback=self._save_hotkey_config)

    def on_mouse_move_editor(self, event):
        self.last_mouse_x = self.canvas.canvasx(event.x)
        self.last_mouse_y = self.canvas.canvasy(event.y)
        self.update_custom_cursor()
        self._schedule_cursor_metrics(self.last_mouse_x, self.last_mouse_y)

    def update_custom_cursor(self, *args):
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists(): return
        
        self.canvas.delete("brush_cursor")
        
        tool = self.tool_var.get()
        x, y = self.last_mouse_x, self.last_mouse_y
        if x < -50 or y < -50: return 
        
        if tool in ['pen', 'highlight', 'rect', 'oval', 'arrow', 'text']:
            self.canvas.config(cursor="none")
            w = self.width_var.get() * self.scale
            color = self.color_var.get()
            
            if tool in ['pen', 'highlight', 'rect', 'oval', 'arrow']:
                if tool == 'highlight': w *= 4
                r = w / 2
                self.canvas.create_oval(x-r, y-r, x+r, y+r, outline="black", width=1, tags="brush_cursor")
                self.canvas.create_oval(x-r+1, y-r+1, x+r-1, y+r-1, outline="white", width=1, tags="brush_cursor")
                
                if tool in ['rect', 'oval', 'arrow']:
                    self.canvas.create_line(x-r-4, y, x+r+4, y, fill="black", tags="brush_cursor")
                    self.canvas.create_line(x, y-r-4, x, y+r+4, fill="black", tags="brush_cursor")
                    self.canvas.create_line(x-r-3, y, x+r+3, y, fill="white", tags="brush_cursor")
                    self.canvas.create_line(x, y-r-3, x, y+r+3, fill="white", tags="brush_cursor")
                    
            elif tool == 'text':
                font_tk = ("Segoe UI", max(1, int(w*4)))
                bg_enabled = self.text_bg_var.get()
                fg_col = color
                
                if bg_enabled:
                    rgb = self.top.winfo_rgb(color)
                    lum = (rgb[0]/256*0.299 + rgb[1]/256*0.587 + rgb[2]/256*0.114)
                    fg_col = "#ffffff" if lum < 128 else "#000000"
                    
                text_id = self.canvas.create_text(x, y, text="Abc", fill=fg_col, font=font_tk, anchor="nw", tags="brush_cursor")
                
                if bg_enabled:
                    bbox = self.canvas.bbox(text_id)
                    if bbox:
                        bg_id = self.canvas.create_rectangle(bbox[0]-4, bbox[1]-4, bbox[2]+4, bbox[3]+4, fill=color, outline="black", tags="brush_cursor")
                        self.canvas.tag_lower(bg_id, text_id)
        else:
            self.canvas.config(cursor="arrow" if tool == "select" else "cross")

    def on_middle_press(self, event):
        self.canvas.config(cursor="fleur")
        self.canvas.scan_mark(event.x, event.y)

    def on_middle_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_middle_release(self, event):
        self.update_custom_cursor()

    def clone_shapes(self, shapes_list):
        cloned = []
        for s in shapes_list:
            new_s = dict(s)
            new_s['coords'] = list(s['coords'])
            cloned.append(new_s)
        return cloned

    def update_history_ui(self):
        if self.history_index > 0: self.btn_undo.config(state="normal", cursor="hand2")
        else: self.btn_undo.config(state="disabled", cursor="arrow")

        if self.history_index < len(self.history) - 1: self.btn_redo.config(state="normal", cursor="hand2")
        else: self.btn_redo.config(state="disabled", cursor="arrow")

        label = getattr(self, "history_label", None)
        if label is not None and self.history:
            try:
                label.config(text=f"{self.history_index + 1}/{len(self.history)}")
            except tk.TclError:
                pass
        self._refresh_metrics()
    
    def save_state(self):
        self.history = self.history[:self.history_index + 1]
        state = {
            'image': self.pil_image.copy(),
            'w': self.orig_w, 'h': self.orig_h,
            'shapes': self.clone_shapes(self.shapes)
        }
        self.history.append(state)
        if len(self.history) > 11: self.history.pop(0)
        self.history_index = len(self.history) - 1
        self.update_history_ui()

    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            self._load_state()

    def redo(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self._load_state()
            
    def _load_state(self):
        state = self.history[self.history_index]
        self.pil_image = state['image'].copy()
        self.orig_w = state['w']
        self.orig_h = state['h']
        self.shapes = self.clone_shapes(state['shapes'])
        self.clear_selection()
        self.redraw_all()
        self.update_history_ui()

    def on_mouse_wheel(self, event):
        delta = getattr(event, 'delta', 0)
        if getattr(event, 'num', 0) == 4: delta = 1
        elif getattr(event, 'num', 0) == 5: delta = -1
        ctrl_pressed = (event.state & 0x0004) != 0

        if event.widget == self.color_btn:
            try: idx = self.palette.index(self.color_var.get())
            except ValueError: idx = 0
            idx = (idx + 1) % len(self.palette) if delta > 0 else (idx - 1) % len(self.palette)
            self.color_var.set(self.palette[idx])
            self.color_btn.config(bg=self.palette[idx])
            self.apply_color_to_selected()
        elif ctrl_pressed:
            if delta > 0: self.set_zoom(1.1)
            elif delta < 0: self.set_zoom(0.9)
        else:
            v = self.width_var.get()
            if delta > 0 and v < 50: self.width_var.set(v + 1)
            elif delta < 0 and v > 1: self.width_var.set(v - 1)

    def pick_color(self):
        c = colorchooser.askcolor(color=self.color_var.get(), title="Chọn màu")[1]
        if c:
            self.color_var.set(c)
            self.color_btn.config(bg=c)
            self.apply_color_to_selected()

    def apply_color_to_selected(self):
        tags = self.selected_tags or ([self.selected_tag] if self.selected_tag else [])
        shapes = [item for item in self.shapes if item.get('tag') in set(tags)]
        if not shapes:
            return
        for shape in shapes:
            shape['color'] = self.color_var.get()
            if shape.get('type') == 'highlight' and shape.get('orig_pil_img'):
                rgb = self.top.winfo_rgb(shape['color'])
                normalized = '#%02x%02x%02x' % tuple(max(0, min(255, value // 256)) for value in rgb)
                recolored = Image.new('RGBA', shape['orig_pil_img'].size, normalized)
                recolored.putalpha(shape['orig_pil_img'].getchannel('A'))
                shape['orig_pil_img'] = recolored
            if shape.get('type') == 'bitmap' and shape.get('source_type') == 'text':
                self._rebuild_text_bitmap(shape)
        self.redraw_all()
        self.save_state()

    def random_color(self):
        c = f"#{random.randint(20, 255):02x}{random.randint(20, 255):02x}{random.randint(20, 255):02x}"
        self.color_var.set(c)
        self.color_btn.config(bg=c)
        if c not in self.palette: self.palette.append(c)
        self.apply_color_to_selected()

    def set_zoom(self, factor):
        if factor == 0: self.scale = 1.0
        else: self.scale = max(0.2, min(self.scale * factor, 5.0))
        self.redraw_all()

    def redraw_all(self):
        self._tk_images = [] 
        self.canvas.delete("all")
        w_img, h_img = int(self.orig_w * self.scale), int(self.orig_h * self.scale)
        if w_img == 0 or h_img == 0: return
        
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10: cw, ch = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        self.offset_x = (cw - w_img) // 2 if cw > w_img else 0
        self.offset_y = (ch - h_img) // 2 if ch > h_img else 0

        scaled_pil = self.pil_image.resize((w_img, h_img), RESAMPLE)
        self.tk_image = ImageTk.PhotoImage(scaled_pil)
        self._tk_images.append(self.tk_image)
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_image, tags="bg")
        self.canvas.config(scrollregion=(0, 0, max(cw, w_img), max(ch, h_img)))

        for s in self.shapes:
            t, tag, col = s['type'], s['tag'], s['color']
            w_shape = s['width'] * self.scale
            c = [(v * self.scale + (self.offset_x if i%2==0 else self.offset_y)) for i, v in enumerate(s['coords'])]
            
            if t in ['blur', 'highlight', 'bitmap'] and 'orig_pil_img' in s:
                img = s['orig_pil_img']
                sc_img = img.resize((int(img.width * self.scale), int(img.height * self.scale)), RESAMPLE)
                tk_img = ImageTk.PhotoImage(sc_img)
                self._tk_images.append(tk_img) 
                s['tk_img'] = tk_img
                draw_x = s['min_x'] * self.scale + self.offset_x
                draw_y = s['min_y'] * self.scale + self.offset_y
                self.canvas.create_image(draw_x, draw_y, anchor="nw", image=tk_img, tags=(tag,))
                
            elif t == 'pen':
                self.canvas.create_line(c, fill=col, width=w_shape, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, tags=(tag,))
            elif t == 'rect':
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline=col, width=w_shape, tags=(tag,))
            elif t == 'oval':
                self.canvas.create_oval(c[0], c[1], c[2], c[3], outline=col, width=w_shape, tags=(tag,))
            elif t == 'arrow':
                self.canvas.create_line(c[0], c[1], c[2], c[3], fill=col, width=w_shape, arrow=tk.LAST, arrowshape=(w_shape*3, w_shape*3+2, w_shape), tags=(tag,))
            elif t == 'crop' and self.crop_pending:
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline='#0078d4', dash=(6, 4), width=2, tags=(tag,))
            elif t == 'text':
                font_tk = ("Segoe UI", max(1, int(w_shape*4)))
                fg_col, bg_col = self._text_colors(col, s.get('bg_enabled', False))
                    
                text_id = self.canvas.create_text(c[0], c[1], text=s['text'], fill=fg_col, font=font_tk, anchor="nw", tags=(tag,))
                
                if s.get('bg_enabled'):
                    bbox = self.canvas.bbox(text_id)
                    if bbox:
                        bg_id = self.canvas.create_rectangle(bbox[0]-4, bbox[1]-4, bbox[2]+4, bbox[3]+4, fill=bg_col, outline=bg_col, tags=(tag,))
                        self.canvas.tag_lower(bg_id, text_id)
                        
        self.update_custom_cursor()
        self._refresh_metrics(selection=self._selection_size())

    def get_new_tag(self):
        self.shape_counter += 1
        return f"shape_{self.shape_counter}"

    def clear_selection(self):
        self.selected_tag = None
        self.selected_tags = []
        self.selection_marquee = False
        self.canvas.delete("sel_box")
        self.canvas.delete("selection_marquee")
        self.update_custom_cursor()

    def _shape_bounds(self, shape):
        if shape.get('type') in ('blur', 'highlight', 'bitmap') and 'orig_pil_img' in shape:
            return (shape.get('min_x', 0), shape.get('min_y', 0), shape.get('min_x', 0) + shape['orig_pil_img'].width, shape.get('min_y', 0) + shape['orig_pil_img'].height)
        coords = shape.get('coords', [])
        if len(coords) < 2:
            return (0, 0, 0, 0)
        return (min(coords[0::2]), min(coords[1::2]), max(coords[0::2]), max(coords[1::2]))

    def draw_selection_box(self):
        self.canvas.delete("sel_box")
        tags = self.selected_tags or ([self.selected_tag] if self.selected_tag else [])
        for tag in tags:
            shape = next((item for item in self.shapes if item.get('tag') == tag), None)
            if not shape:
                continue
            x1, y1, x2, y2 = self._shape_bounds(shape)
            pad = shape.get('width', 2) * self.scale + 2
            self.canvas.create_rectangle(x1 * self.scale + self.offset_x - pad, y1 * self.scale + self.offset_y - pad,
                                         x2 * self.scale + self.offset_x + pad, y2 * self.scale + self.offset_y + pad,
                                         outline=T.COLORS.focus_ring, dash=(4, 4), width=2, tags="sel_box")
        self._refresh_metrics(selection=self._selection_size())

    def handle_select_all_shortcut(self):
        if self.text_entry and self.top.focus_get() == self.text_entry:
            self.text_entry.selection_range(0, 'end')
            return
        self.select_all()

    def move_selected_by(self, dx, dy):
        if self.text_entry and self.top.focus_get() == self.text_entry:
            return
        tags = self.selected_tags or ([self.selected_tag] if self.selected_tag else [])
        if not tags:
            return
        for shape in self.shapes:
            if shape.get('tag') not in tags:
                continue
            shape['coords'] = [value + (dx if index % 2 == 0 else dy) for index, value in enumerate(shape.get('coords', []))]
            if shape.get('type') in ('blur', 'highlight', 'bitmap'):
                shape['min_x'] = shape.get('min_x', 0) + dx
                shape['min_y'] = shape.get('min_y', 0) + dy
        self.redraw_all()
        self.draw_selection_box()
        self.save_state()

    def select_all(self, event=None):
        self.selected_tags = [shape['tag'] for shape in self.shapes if shape.get('type') != 'crop']
        self.selected_tag = self.selected_tags[0] if self.selected_tags else None
        self.draw_selection_box()

    def delete_selected(self, event=None):
        tags = set(self.selected_tags or ([self.selected_tag] if self.selected_tag else []))
        if tags:
            for tag in tags:
                self.canvas.delete(tag)
            self.shapes = [s for s in self.shapes if s.get('tag') not in tags]
            self.clear_selection()
            self.redraw_all()
            self.save_state()

    def on_press(self, event):
        if self.text_entry: self.commit_text()
        tool = self.tool_var.get()
        if tool == 'crop':
            self.shapes = [item for item in self.shapes if item.get('type') != 'crop']
            self.crop_pending = False
            self.canvas.delete('temp_drag')
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.start_cx, self.start_cy = cx, cy
        self.prev_cx, self.prev_cy = cx, cy
        self.axis_locked = None; self.has_moved = False

        if tool == "select":
            items = self.canvas.find_withtag("current")
            tag = next((t for i in items for t in self.canvas.gettags(i) if t.startswith("shape_")), None)
            ctrl = bool(event.state & 0x0004)
            if tag:
                if ctrl:
                    if tag in self.selected_tags:
                        self.selected_tags.remove(tag)
                    else:
                        self.selected_tags.append(tag)
                else:
                    self.selected_tags = [tag]
                self.selected_tag = self.selected_tags[0] if self.selected_tags else None
                selected = next((item for item in self.shapes if item.get('tag') == self.selected_tag), None)
                if selected and selected.get('type') == 'text':
                    self._syncing_text_style = True
                    self.text_bg_var.set(bool(selected.get('bg_enabled', False)))
                    self._syncing_text_style = False
                self.draw_selection_box()
            else:
                self.selection_marquee = True
                self.selected_tags = []
                self.selected_tag = None
                self.canvas.delete('selection_marquee')
            return

        tag, width, color = self.get_new_tag(), self.width_var.get(), self.color_var.get()
        ix, iy = (cx - self.offset_x) / self.scale, (cy - self.offset_y) / self.scale
        shape = {'tag': tag, 'type': tool, 'color': color, 'width': width, 'text': ''}
        
        if tool in ['pen', 'highlight']: shape['coords'] = [ix, iy]
        elif tool in ['rect', 'oval', 'arrow', 'blur', 'crop', 'erase']: shape['coords'] = [ix, iy, ix, iy]
        elif tool == "text":
            bg_enabled = self.text_bg_var.get()
            fg_col, bg_col = self._text_colors(color, bg_enabled)
                
            self.text_entry = tk.Entry(self.canvas, font=("Segoe UI", int(width*4*self.scale)), fg=fg_col, bg=bg_col, borderwidth=1)
            self.canvas.create_window(cx, cy, window=self.text_entry, anchor="nw")
            self.text_entry.focus_set()
            self.text_entry.bind("<Return>", lambda e: self.commit_text())
            shape['coords'] = [ix, iy]
            shape['bg_enabled'] = bg_enabled
            
        self.shapes.append(shape)

    def on_drag(self, event):
        tool = self.tool_var.get()
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.last_mouse_x = cx
        self.last_mouse_y = cy
        self.update_custom_cursor()
        
        if event.state & 0x0001:
            if tool == 'oval':
                # Shift constrains an oval to a circle while preserving drag direction.
                dx, dy = cx - self.start_cx, cy - self.start_cy
                side = max(abs(dx), abs(dy))
                cx = self.start_cx + (side if dx >= 0 else -side)
                cy = self.start_cy + (side if dy >= 0 else -side)
            else:
                if self.axis_locked is None:
                    self.axis_locked = 'x' if abs(cx - self.start_cx) > abs(cy - self.start_cy) else 'y'
                if self.axis_locked == 'x': cy = self.start_cy
                elif self.axis_locked == 'y': cx = self.start_cx
        else:
            self.axis_locked = None

        ix, iy = (cx - self.offset_x) / self.scale, (cy - self.offset_y) / self.scale

        if tool == "select" and self.selection_marquee:
            self.canvas.delete('selection_marquee')
            self.canvas.create_rectangle(self.start_cx, self.start_cy, cx, cy, outline='#0078d4', dash=(5, 3), tags='selection_marquee')
            return

        if tool == "select" and self.selected_tags:
            self.has_moved = True
            dx, dy = cx - self.prev_cx, cy - self.prev_cy
            dx_img, dy_img = dx / self.scale, dy / self.scale
            for tag in self.selected_tags:
                self.canvas.move(tag, dx, dy)
                shape = next((item for item in self.shapes if item.get('tag') == tag), None)
                if shape:
                    shape['coords'] = [v + (dx_img if i % 2 == 0 else dy_img) for i, v in enumerate(shape['coords'])]
                    if shape.get('type') in ['blur', 'highlight', 'bitmap']:
                        shape['min_x'] += dx_img
                        shape['min_y'] += dy_img
            self.prev_cx, self.prev_cy = cx, cy
            self.draw_selection_box()
            return
            
        if not self.shapes or tool == "text": return
        s = self.shapes[-1]
        
        if tool == 'pen':
            s['coords'].extend([ix, iy])
            w_sc = s['width'] * self.scale
            self.canvas.create_line(s['coords'][-4]*self.scale + self.offset_x, s['coords'][-3]*self.scale + self.offset_y, cx, cy, fill=s['color'], width=w_sc, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=(s['tag'],))
        elif tool == 'highlight':
            s['coords'].extend([ix, iy])
            w_sc = s['width'] * 4 * self.scale
            self.canvas.create_line(s['coords'][-4]*self.scale + self.offset_x, s['coords'][-3]*self.scale + self.offset_y, cx, cy, fill=s['color'], width=w_sc, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=(s['tag'], "temp_drag"))
        elif tool in ['rect', 'oval', 'arrow', 'blur', 'crop', 'erase']:
            s['coords'][2], s['coords'][3] = ix, iy
            self.canvas.delete(s['tag'] if tool not in ['blur', 'crop', 'erase'] else "temp_drag")
            c = [v * self.scale + (self.offset_x if i%2==0 else self.offset_y) for i, v in enumerate(s['coords'])]
            w_sc = s['width'] * self.scale
            if tool == 'rect':
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline=s['color'], width=w_sc, tags=(s['tag'],))
            elif tool == 'oval':
                self.canvas.create_oval(c[0], c[1], c[2], c[3], outline=s['color'], width=w_sc, tags=(s['tag'],))
            elif tool == 'arrow':
                self.canvas.create_line(c[0], c[1], c[2], c[3], fill=s['color'], width=w_sc, arrow=tk.LAST, arrowshape=(w_sc*3, w_sc*3+2, w_sc), tags=(s['tag'],))
            elif tool == 'blur':
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline="gray", dash=(4,4), tags=("temp_drag",))
            elif tool == 'crop':
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline="#0088ff", dash=(4,4), width=2, tags=("temp_drag",))
            elif tool == 'erase':
                self.canvas.create_rectangle(c[0], c[1], c[2], c[3], outline="red", dash=(4,4), width=2, tags=("temp_drag",))

    def erase_pixels(self, box):
        """Erase raster pixels while preserving editable annotations."""
        self.pil_image = self.pil_image.copy().convert('RGBA')
        self.pil_image.paste((0, 0, 0, 0), tuple(int(value) for value in box))
        self.orig_w, self.orig_h = self.pil_image.size

    def on_release(self, event):
        if self.tool_var.get() == "select":
            if self.selection_marquee:
                x1, x2 = sorted((self.start_cx, self.canvas.canvasx(event.x)))
                y1, y2 = sorted((self.start_cy, self.canvas.canvasy(event.y)))
                self.selected_tags = []
                for shape in self.shapes:
                    if shape.get('type') == 'crop':
                        continue
                    sx1, sy1, sx2, sy2 = self._shape_bounds(shape)
                    if sx1 * self.scale + self.offset_x >= x1 and sy1 * self.scale + self.offset_y >= y1 and sx2 * self.scale + self.offset_x <= x2 and sy2 * self.scale + self.offset_y <= y2:
                        self.selected_tags.append(shape['tag'])
                self.selected_tag = self.selected_tags[0] if self.selected_tags else None
                self.selection_marquee = False
                self.canvas.delete('selection_marquee')
                self.draw_selection_box()
            elif self.has_moved:
                self.save_state()
                self.has_moved = False
            return
            
        if not self.shapes: return
        s = self.shapes[-1]
        t = s['type']

        if t == "highlight":
            self.canvas.delete("temp_drag")
            c = s['coords']
            if len(c) < 4: self.shapes.pop(); return
            
            w = s['width'] * 4; pad = w + 4
            min_x, max_x = min(c[0::2]) - pad, max(c[0::2]) + pad
            min_y, max_y = min(c[1::2]) - pad, max(c[1::2]) + pad
            bw, bh = int(max_x - min_x), int(max_y - min_y)
            
            scale_aa = 4
            hl_img_aa = Image.new("RGBA", (bw * scale_aa, bh * scale_aa), (0,0,0,0))
            draw = ImageDraw.Draw(hl_img_aa)
            
            flat_local = [(v - min_x)*scale_aa if i%2==0 else (v - min_y)*scale_aa for i, v in enumerate(c)]
            rgb = self.top.winfo_rgb(s['color'])
            hl_color = (rgb[0]//256, rgb[1]//256, rgb[2]//256, 120)
            
            draw.line(flat_local, fill=hl_color, width=int(w*scale_aa), joint="curve")
            r = int(w * scale_aa / 2)
            draw.ellipse([flat_local[0]-r, flat_local[1]-r, flat_local[0]+r, flat_local[1]+r], fill=hl_color)
            draw.ellipse([flat_local[-2]-r, flat_local[-1]-r, flat_local[-2]+r, flat_local[-1]+r], fill=hl_color)
            
            s['orig_pil_img'] = hl_img_aa.resize((bw, bh), RESAMPLE)
            s['min_x'], s['min_y'] = min_x, min_y
            self.redraw_all(); self.save_state()
            
        elif t == "blur":
            self.canvas.delete("temp_drag")
            c = s['coords']
            x1, y1, x2, y2 = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
            self.shapes.pop() 
            
            if x2 - x1 > 5 and y2 - y1 > 5:
                base_img = self.render_final_image()
                self.shapes.append(s) 
                
                box = (int(x1), int(y1), int(x2), int(y2))
                cropped = base_img.crop(box)
                
                # Chuyển sang RGB để làm mờ (tránh viền bị lem trong suốt)
                blurred = cropped.convert("RGB").filter(ImageFilter.GaussianBlur(15))
                
                # Ghép lại kênh Alpha gốc để giữ độ sắc nét 100% cho viền ảnh
                if cropped.mode in ("RGBA", "LA"):
                    blurred.putalpha(cropped.split()[-1])
                    
                s['orig_pil_img'] = blurred 
                s['min_x'], s['min_y'] = box[0], box[1]
                self.redraw_all()
                self.save_state()
            
        elif t == "crop":
            # Keep the crop rectangle visible until Enter confirms it.
            self.canvas.delete("temp_drag")
            if abs(s['coords'][2] - s['coords'][0]) <= 5 or abs(s['coords'][3] - s['coords'][1]) <= 5:
                self.shapes.pop()
            else:
                self.crop_pending = True
                self.redraw_all()

        elif t == "erase":
            self.canvas.delete("temp_drag")
            c = s['coords']
            x1, y1, x2, y2 = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
            self.shapes.pop()
            
            if x2 - x1 > 5 and y2 - y1 > 5:
                # Erase only raster pixels; keep annotation objects as editable model data.
                self.erase_pixels((x1, y1, x2, y2))
                self.clear_selection()
                self.redraw_all()
                self.save_state()

        elif t in ["pen", "rect", "oval", "arrow"]:
            self.save_state()

    def cancel_crop_or_text(self):
        if self.text_entry:
            self.cancel_text_edit()
            return
        if self.tool_var.get() == 'crop' and self.crop_pending:
            crop_shape = next((item for item in self.shapes if item.get('type') == 'crop'), None)
            if crop_shape:
                self.shapes.remove(crop_shape)
            self.crop_pending = False
            self.redraw_all()
            self.clear_selection()
        elif self.selected_tag:
            self.clear_selection()

    def confirm_crop(self):
        if self.tool_var.get() != 'crop' or not self.crop_pending:
            return
        crop_shape = next((item for item in self.shapes if item.get('type') == 'crop'), None)
        if not crop_shape:
            self.crop_pending = False
            return
        c = crop_shape['coords']
        x1, y1, x2, y2 = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
        self.pil_image = self.pil_image.crop((int(x1), int(y1), int(x2), int(y2)))
        self.orig_w, self.orig_h = self.pil_image.size
        self.shapes.remove(crop_shape)
        for shape in self.shapes:
            coords = shape.get('coords', [])
            shape['coords'] = [v - (x1 if i % 2 == 0 else y1) for i, v in enumerate(coords)]
            if shape.get('type') in ('blur', 'highlight', 'bitmap') and 'min_x' in shape:
                shape['min_x'] -= x1
                shape['min_y'] -= y1
        self.crop_pending = False
        self.clear_selection()
        self.redraw_all()
        self.save_state()

    def begin_text_edit(self, tag):
        shape = next((item for item in self.shapes if item.get('tag') == tag and item.get('type') == 'text'), None)
        if not shape:
            return
        if self.text_entry:
            self.commit_text()
        self.editing_tag = tag
        x, y = shape['coords'][:2]
        cx = x * self.scale + self.offset_x
        cy = y * self.scale + self.offset_y
        fg_col, bg_col = self._text_colors(shape['color'], shape.get('bg_enabled', False))
        self.text_entry = tk.Entry(self.canvas, font=('Segoe UI', max(1, int(shape['width'] * 4 * self.scale))),
                                   fg=fg_col, bg=bg_col, borderwidth=1)
        self.canvas.create_window(cx, cy, window=self.text_entry, anchor='nw')
        self.text_entry.insert(0, shape.get('text', ''))
        self.text_entry.focus_set()
        self.text_entry.bind('<Return>', lambda e: self.commit_text())
        self.text_entry.bind('<Escape>', lambda e: self.cancel_text_edit())

    def cancel_text_edit(self):
        if self.text_entry:
            self.text_entry.destroy()
        self.text_entry = None
        self.editing_tag = None
        self.redraw_all()

    def on_double_click(self, event):
        if self.tool_var.get() != 'select':
            return
        items = self.canvas.find_withtag('current')
        tag = next((t for i in items for t in self.canvas.gettags(i) if t.startswith('shape_')), None)
        if tag:
            self.selected_tag = tag
            self.begin_text_edit(tag)

    def _text_colors(self, color, bg_enabled):
        rgb = self.top.winfo_rgb(color)
        normalized = '#%02x%02x%02x' % tuple(max(0, min(255, value // 256)) for value in rgb)
        if not bg_enabled:
            return normalized, 'white'
        lum = (rgb[0] / 256 * 0.299 + rgb[1] / 256 * 0.587 + rgb[2] / 256 * 0.114)
        return ('#ffffff' if lum < 128 else '#000000'), normalized

    def commit_text(self, save_history=True):
        if not self.text_entry:
            return
        txt = self.text_entry.get().strip()
        target = next((item for item in self.shapes if item.get('tag') == self.editing_tag), None) if self.editing_tag else (self.shapes[-1] if self.shapes else None)
        editing_existing = self.editing_tag is not None
        if target and txt:
            target['text'] = txt
            if save_history:
                self.save_state()
        elif target and not editing_existing:
            self.shapes.remove(target)
        self.text_entry.destroy()
        self.text_entry = None
        self.editing_tag = None
        self.redraw_all()

    def render_final_image(self):
        final = self.pil_image.copy().convert("RGBA")
        
        for s in self.shapes:
            c, w, col = s['coords'], s['width'], s['color']
            
            if s['type'] == 'highlight' and 'orig_pil_img' in s:
                overlay = Image.new("RGBA", final.size, (0, 0, 0, 0))
                overlay.paste(s['orig_pil_img'], (int(s['min_x']), int(s['min_y'])))
                final = Image.alpha_composite(final, overlay)
                
            elif s['type'] in ('blur', 'bitmap') and 'orig_pil_img' in s:
                final.paste(s['orig_pil_img'], (int(s['min_x']), int(s['min_y'])), s['orig_pil_img'])
                
            elif s['type'] in ['pen', 'rect', 'oval', 'arrow']:
                # Dùng Kỹ thuật SSAA 4x (Supersampling Anti-Aliasing) để khử răng cưa và bo tròn mượt mà
                scale_aa = 4
                pad = w * 4 + 20
                min_x, max_x = min(c[0::2]) - pad, max(c[0::2]) + pad
                min_y, max_y = min(c[1::2]) - pad, max(c[1::2]) + pad
                
                bw, bh = int(max_x - min_x), int(max_y - min_y)
                if bw <= 0 or bh <= 0: continue
                
                layer_aa = Image.new("RGBA", (bw * scale_aa, bh * scale_aa), (0, 0, 0, 0))
                draw_aa = ImageDraw.Draw(layer_aa)
                
                c_aa = [(v - min_x) * scale_aa if i%2==0 else (v - min_y) * scale_aa for i, v in enumerate(c)]
                w_aa = w * scale_aa
                
                if s['type'] == 'pen':
                    draw_aa.line(c_aa, fill=col, width=int(w_aa), joint="curve")
                    r = w_aa / 2
                    draw_aa.ellipse([c_aa[0]-r, c_aa[1]-r, c_aa[0]+r, c_aa[1]+r], fill=col)
                    draw_aa.ellipse([c_aa[-2]-r, c_aa[-1]-r, c_aa[-2]+r, c_aa[-1]+r], fill=col)
                    
                elif s['type'] == 'rect':
                    # Bù trừ tọa độ do PIL vẽ viền hướng vào trong (inward)
                    # Phải mở rộng khung ra ngoài 1 nửa độ dày nét (w_aa / 2) để khớp với Tkinter (centered)
                    half_w = w_aa / 2.0
                    
                    x1 = min(c_aa[0], c_aa[2]) - half_w
                    y1 = min(c_aa[1], c_aa[3]) - half_w
                    x2 = max(c_aa[0], c_aa[2]) + half_w
                    y2 = max(c_aa[1], c_aa[3]) + half_w
                    
                    draw_aa.rectangle([x1, y1, x2, y2], outline=col, width=int(w_aa))

                elif s['type'] == 'oval':
                    half_w = w_aa / 2.0
                    x1 = min(c_aa[0], c_aa[2]) - half_w
                    y1 = min(c_aa[1], c_aa[3]) - half_w
                    x2 = max(c_aa[0], c_aa[2]) + half_w
                    y2 = max(c_aa[1], c_aa[3]) + half_w
                    draw_aa.ellipse([x1, y1, x2, y2], outline=col, width=int(w_aa))

                elif s['type'] == 'arrow':
                    r = w_aa * 3 + 4 * scale_aa
                    angle = math.atan2(c_aa[3] - c_aa[1], c_aa[2] - c_aa[0])
                    
                    # Lùi thân mũi tên lại đúng bằng chiều cao tam giác để chóp luôn nhọn hoắt
                    shift_dist = r * math.cos(math.pi / 6)
                    dist = math.hypot(c_aa[2] - c_aa[0], c_aa[3] - c_aa[1])
                    
                    if dist > shift_dist:
                        end_x = c_aa[2] - shift_dist * math.cos(angle)
                        end_y = c_aa[3] - shift_dist * math.sin(angle)
                    else:
                        end_x, end_y = c_aa[0], c_aa[1]
                        
                    # Vẽ thân mũi tên dừng ở đáy tam giác
                    draw_aa.line([c_aa[0], c_aa[1], end_x, end_y], fill=col, width=int(w_aa))
                    
                    # Vẽ chóp mũi tên
                    p1 = (c_aa[2] - r * math.cos(angle - math.pi/6), c_aa[3] - r * math.sin(angle - math.pi/6))
                    p2 = (c_aa[2] - r * math.cos(angle + math.pi/6), c_aa[3] - r * math.sin(angle + math.pi/6))
                    draw_aa.polygon([(c_aa[2], c_aa[3]), p1, p2], fill=col)
                    
                    # Bo tròn đầu bắt đầu của đường thẳng và điểm nối giữa thân và đầu mũi tên
                    rad = w_aa / 2
                    draw_aa.ellipse([c_aa[0]-rad, c_aa[1]-rad, c_aa[0]+rad, c_aa[1]+rad], fill=col)
                    draw_aa.ellipse([end_x-rad, end_y-rad, end_x+rad, end_y+rad], fill=col)

                # Thu nhỏ bằng LANCZOS
                layer_down = layer_aa.resize((bw, bh), RESAMPLE)
                overlay = Image.new("RGBA", final.size, (0, 0, 0, 0))
                overlay.paste(layer_down, (int(min_x), int(min_y)))
                final = Image.alpha_composite(final, overlay)
                
            elif s['type'] == 'text':
                draw = ImageDraw.Draw(final)
                
                # 1. BẮT ĐÚNG DPI THỰC TẾ CỦA MÀN HÌNH (Bao gồm cả Windows Scale 125%, 150%...)
                # Use the same logical size as the Tk preview so the background bounds match.
                font_size_px = max(1, int(w * 4))
                
                try: 
                    font = ImageFont.truetype("segoeui.ttf", font_size_px)
                except OSError: 
                    font = ImageFont.load_default()
                
                fg_col, bg_col = self._text_colors(col, s.get('bg_enabled', False))
                if s.get('bg_enabled'):
                    # Match the 4px Tk preview padding in the exported image.
                    try:
                        bbox = draw.textbbox((c[0], c[1]), s['text'], font=font, anchor="la")
                        draw.rectangle([bbox[0]-4, bbox[1]-4, bbox[2]+4, bbox[3]+4], fill=bg_col)
                    except Exception:
                        pass
                    
                # Vẽ chữ chuẩn mỏ neo "la" không cần offset_y
                try:
                    draw.text((c[0], c[1]), s['text'], fill=fg_col, font=font, anchor="la")
                except (ValueError, TypeError):
                    draw.text((c[0], c[1]), s['text'], fill=fg_col, font=font)
                
        return final

    def transform_selection_or_document(self, operation):
        """Transform the selected annotation, otherwise transform the whole document."""
        if self.selected_tag:
            shape = next((s for s in self.shapes if s['tag'] == self.selected_tag), None)
            if shape:
                self.transform_selected_shape(shape, operation)
                return
        self.transform_document(operation)

    def _rebuild_text_bitmap(self, shape):
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        font_size = max(1, int(shape.get('width', 4) * 4 * dpi / 72.0))
        try:
            font = ImageFont.truetype('segoeui.ttf', font_size)
        except Exception:
            font = ImageFont.load_default()
        probe = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        bbox = ImageDraw.Draw(probe).textbbox((0, 0), shape.get('text', ''), font=font, anchor='la')
        pad = 6
        bitmap = Image.new('RGBA', (max(1, bbox[2] - bbox[0] + pad * 2), max(1, bbox[3] - bbox[1] + pad * 2)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bitmap)
        fg, bg = self._text_colors(shape.get('color', '#000000'), shape.get('bg_enabled', False))
        if shape.get('bg_enabled'):
            draw.rectangle((0, 0, bitmap.width - 1, bitmap.height - 1), fill=bg)
        draw.text((pad - bbox[0], pad - bbox[1]), shape.get('text', ''), font=font, fill=fg, anchor='la')
        for operation in shape.get('text_transform', []):
            if operation == 'flip_h':
                bitmap = bitmap.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif operation == 'flip_v':
                bitmap = bitmap.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            elif operation == 'rotate_cw':
                bitmap = bitmap.transpose(Image.Transpose.ROTATE_270)
            elif operation == 'rotate_ccw':
                bitmap = bitmap.transpose(Image.Transpose.ROTATE_90)
        shape['orig_pil_img'] = bitmap
        shape['coords'] = [shape.get('min_x', shape['coords'][0]), shape.get('min_y', shape['coords'][1]), shape.get('min_x', shape['coords'][0]) + bitmap.width, shape.get('min_y', shape['coords'][1]) + bitmap.height]

    def transform_selected_shape(self, shape, operation):
        # Rasterize text on first object transform so rotation/flip is visible.
        if shape.get('type') == 'text' and shape.get('text'):
            try:
                dpi = ctypes.windll.user32.GetDpiForSystem()
            except Exception:
                dpi = 96
            font_size = max(1, int(shape.get('width', 4) * 4 * dpi / 72.0))
            try:
                font = ImageFont.truetype('segoeui.ttf', font_size)
            except Exception:
                font = ImageFont.load_default()
            probe = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
            probe_draw = ImageDraw.Draw(probe)
            bbox = probe_draw.textbbox((0, 0), shape['text'], font=font, anchor='la')
            pad = 6
            bitmap = Image.new('RGBA', (max(1, bbox[2] - bbox[0] + pad * 2), max(1, bbox[3] - bbox[1] + pad * 2)), (0, 0, 0, 0))
            draw = ImageDraw.Draw(bitmap)
            fg = shape.get('color', '#000000')
            if shape.get('bg_enabled'):
                draw.rectangle((0, 0, bitmap.width - 1, bitmap.height - 1), fill=fg)
                fg = '#ffffff' if self.top.winfo_rgb(shape.get('color', '#000000'))[0] / 256 * 0.299 + self.top.winfo_rgb(shape.get('color', '#000000'))[1] / 256 * 0.587 + self.top.winfo_rgb(shape.get('color', '#000000'))[2] / 256 * 0.114 < 128 else '#000000'
            draw.text((pad - bbox[0], pad - bbox[1]), shape['text'], font=font, fill=fg, anchor='la')
            shape['type'] = 'bitmap'
            shape['source_type'] = 'text'
            shape['text_transform'] = []
            shape['orig_pil_img'] = bitmap
            x, y = shape['coords'][:2]
            shape['min_x'], shape['min_y'] = x, y
            shape['coords'] = [x, y, x + bitmap.width, y + bitmap.height]
        coords = shape.get('coords', [])
        if len(coords) < 2:
            return
        xs, ys = coords[0::2], coords[1::2]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        cx, cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
        def map_point(x, y):
            if operation == 'flip_h':
                return 2 * cx - x, y
            if operation == 'flip_v':
                return x, 2 * cy - y
            if operation == 'rotate_cw':
                return cx + (cy - y), cy + (x - cx)
            return cx + (y - cy), cy - (x - cx)
        mapped = []
        for x, y in zip(xs, ys):
            nx, ny = map_point(x, y)
            mapped.extend([nx, ny])
        shape['coords'] = mapped
        if shape.get('type') in ('blur', 'highlight', 'bitmap') and shape.get('orig_pil_img'):
            if shape.get('source_type') == 'text':
                shape.setdefault('text_transform', []).append(operation)
            image = shape['orig_pil_img']
            if operation == 'flip_h':
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif operation == 'flip_v':
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            elif operation == 'rotate_cw':
                image = image.transpose(Image.Transpose.ROTATE_270)
            else:
                image = image.transpose(Image.Transpose.ROTATE_90)
            shape['orig_pil_img'] = image
            shape['min_x'] = min(mapped[0::2])
            shape['min_y'] = min(mapped[1::2])
            shape['coords'] = [shape['min_x'], shape['min_y'], shape['min_x'] + image.width, shape['min_y'] + image.height]
        self.clear_selection()
        self.redraw_all()
        self.save_state()

    def transform_document(self, operation):
        if self.text_entry:
            self.commit_text(save_history=False)
        old_w, old_h = self.orig_w, self.orig_h
        if operation == 'flip_h':
            transformed = self.pil_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            map_point = lambda x, y: (old_w - x, y)
            image_operation = Image.Transpose.FLIP_LEFT_RIGHT
        elif operation == 'flip_v':
            transformed = self.pil_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            map_point = lambda x, y: (x, old_h - y)
            image_operation = Image.Transpose.FLIP_TOP_BOTTOM
        elif operation == 'rotate_cw':
            transformed = self.pil_image.transpose(Image.Transpose.ROTATE_270)
            map_point = lambda x, y: (old_h - y, x)
            image_operation = Image.Transpose.ROTATE_270
        elif operation == 'rotate_ccw':
            transformed = self.pil_image.transpose(Image.Transpose.ROTATE_90)
            map_point = lambda x, y: (y, old_w - x)
            image_operation = Image.Transpose.ROTATE_90
        else:
            return
        for shape in self.shapes:
            coords = shape.get('coords', [])
            mapped = []
            for x, y in zip(coords[0::2], coords[1::2]):
                nx, ny = map_point(x, y)
                mapped.extend([nx, ny])
            shape['coords'] = mapped
            if shape.get('type') in ('blur', 'highlight', 'bitmap') and shape.get('orig_pil_img'):
                if shape.get('source_type') == 'text':
                    shape.setdefault('text_transform', []).append(operation)
                shape['orig_pil_img'] = shape['orig_pil_img'].transpose(image_operation)
                shape['min_x'] = min(mapped[0::2])
                shape['min_y'] = min(mapped[1::2])
                shape['coords'] = [shape['min_x'], shape['min_y'], shape['min_x'] + shape['orig_pil_img'].width, shape['min_y'] + shape['orig_pil_img'].height]
        self.pil_image = transformed
        self.orig_w, self.orig_h = transformed.size
        self.clear_selection()
        self.redraw_all()
        self.save_state()

    # save_clipboard / _restore_copy_label / _cancel_copy_reset / save_file are
    # provided by ui_editor_io.EditorExportMixin (see the class statement).

# The capture overlay and result toast live in ``ui_capture`` so the editor
# module stays focused on annotation.  ``SnippingTool`` is re-exported below
# for backwards compatibility with anything that still looks it up here.
SnippingTool = ui_capture.SnippingTool
ResultToast = ui_capture.ResultToast


def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối, hoạt động cho cả lúc code (dev) và lúc chạy file .exe """
    try:
        # PyInstaller tạo ra biến _MEIPASS chứa đường dẫn thư mục tạm
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def create_tray_icon():
    try:
        # Sử dụng hàm resource_path để tìm đúng file icon
        icon_path = resource_path("icon_ScreenShotTool.ico")
        return Image.open(icon_path)
    except (OSError, ValueError):
        # Dự phòng: Nếu mất file ảnh thì tự vẽ lại ô màu xanh
        return Image.new('RGB', (64, 64), color="#0078D4")

def open_editor_for(image):
    """Callback handed to :class:`ui_capture.ResultToast`.

    The toast lives in a different module and must not import this one, so the
    editor is opened through this injected hook instead.
    """
    try:
        ImageEditor(root_window_for_tk(), image)
    except Exception:
        logging.exception("Could not open the editor for the captured image")


_root_ref = None


def root_window_for_tk():
    """The hidden Tk root created by :func:`main`, used as the editor master."""
    global _root_ref
    if _root_ref is None:
        _root_ref = tk.Tk()
        _root_ref.withdraw()
    return _root_ref


def _hotkey_label(modifier_mask, vk):
    """Render (modifiers, vk) back into something the user can recognise."""
    names = [name for name, bit in (("Ctrl", 0x0002), ("Alt", 0x0001),
                                    ("Shift", 0x0004), ("Win", 0x0008))
             if modifier_mask & bit]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        names.append(chr(vk))
    elif 0x70 <= vk <= 0x87:
        names.append("F%d" % (vk - 0x6F))
    return "+".join(names)


# Set once the tray icon exists, so the hotkey listener (which starts earlier)
# can surface a failure to the user instead of only to the log.
_tray_icon_ref = None
_warned_hotkeys = set()


def _warn_hotkey_unavailable(modifier_mask, vk):
    """Tell the user their capture hotkey did not take, once per combination."""
    label = _hotkey_label(modifier_mask, vk)
    if label in _warned_hotkeys:
        return
    _warned_hotkeys.add(label)
    message = (
        "%s đang được ứng dụng khác sử dụng nên không đăng ký được.\n"
        "Bạn vẫn chụp được bằng menu khay hệ thống, hoặc chọn phím khác "
        "trong Cài đặt phím tắt." % label
    )
    icon = _tray_icon_ref
    if icon is not None:
        try:
            icon.notify(message, "ScreenShotTool")
            return
        except Exception:
            logging.debug("Tray notification unavailable", exc_info=True)
    logging.warning("Hotkey %s unavailable: %s", label, message.replace("\n", " "))


def _run_hotkey_listener(root, app, hotkey_stop):
    """Register the capture hotkey and pump its messages until stopped.

    Pulled out of main() so the re-registration logic can be read (and tested)
    without the tray, the Tk root and the menu all in scope.
    """
    user32 = ctypes.windll.user32
    WM_HOTKEY = 0x0312
    PM_REMOVE = 0x0001
    registered = None
    # Tracks the combination we last *attempted*.  Without it a failed
    # RegisterHotKey (another app owns Alt+X, or the key is reserved) never
    # leaves ``desired != registered``, so the loop re-registered and
    # re-logged every 100 ms forever instead of waiting for a config change.
    attempted = None
    msg = ctypes.wintypes.MSG()
    while not hotkey_stop.is_set():
        desired = parse_hotkey(load_config().get("capture_hotkey", "Alt+X")) or (HOTKEY_MODIFIERS["ALT"], ord("X"))
        if desired != attempted:
            attempted = desired
            if registered is not None:
                user32.UnregisterHotKey(None, 1)
                registered = None
            if user32.RegisterHotKey(None, 1, desired[0], desired[1]):
                registered = desired
                logging.info("Capture hotkey registered: %s", load_config().get("capture_hotkey", "Alt+X"))
            else:
                # Another app owns the combination (or Windows reserved it).
                # Logging alone hid this: the tray kept working, so the user
                # had no way to learn why their hotkey did nothing. Tell them
                # once per failed combination, not every 100 ms.
                logging.warning("Could not register capture hotkey; tray remains available")
                _warn_hotkey_unavailable(desired)
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_HOTKEY:
                root.after(0, app.start_snipping)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.1)
    if registered is not None:
        user32.UnregisterHotKey(None, 1)


def main():
    global _root_ref, _tray_icon_ref
    root = tk.Tk()
    _root_ref = root
    root.iconbitmap(resource_path("icon_ScreenShotTool.ico"))
    logging.info("%s %s starting (config: %s)", APP_NAME, APP_VERSION, CONFIG_FILE)
    app = SnippingTool(
        root,
        resource_path=resource_path,
        send_to_clipboard=send_to_clipboard,
        open_editor=open_editor_for,
    )

    # The listener re-registers the moment the config changes.
    hotkey_stop = threading.Event()
    threading.Thread(target=lambda: _run_hotkey_listener(root, app, hotkey_stop),
                     daemon=True).start()

    def on_quit(icon, item):
        hotkey_stop.set()
        icon.stop()
        root.destroy()
        os._exit(0)

    def check_for_updates(icon, menu_item):
        """Ask GitHub for the latest release without blocking the tray."""
        def report(release, current):
            def show():
                if release is None:
                    messagebox.showinfo(
                        "Kiểm tra cập nhật",
                        "Không kiểm tra được bản mới.\n"
                        "Hãy kiểm tra kết nối mạng rồi thử lại.",
                        parent=root)
                    return
                tag = release.get("tag") or "(không rõ)"
                if ui_updates.is_newer(tag, current):
                    messagebox.showinfo(
                        "Có bản mới",
                        "Bản hiện tại: %s\nBản mới nhất: %s\n\n%s\n\n"
                        "Mở trang tải về?" % (current, tag, release.get("url", "")),
                        parent=root)
                else:
                    messagebox.showinfo(
                        "Kiểm tra cập nhật",
                        "Bạn đang dùng bản mới nhất (%s)." % current,
                        parent=root)
            root.after(0, show)

        ui_updates.check_async(APP_VERSION, report)

    icon = pystray.Icon("SnippingTool", create_tray_icon(), "Công cụ Chụp màn hình", menu=pystray.Menu(
        item(f'Chụp màn hình ({load_config().get("capture_hotkey", "Alt+X")})', lambda icon, menu_item: root.after(0, app.start_snipping)),
        # A delay lets a menu finish closing or a tooltip appear before the
        # screen freezes. The hotkey stays instant; this is the deliberate path.
        pystray.MenuItem('Chụp sau', pystray.Menu(
            item('Ngay lập tức', lambda icon, menu_item: root.after(0, app.start_snipping)),
            item('3 giây', lambda icon, menu_item: root.after(0, lambda: app.start_snipping(3))),
            item('5 giây', lambda icon, menu_item: root.after(0, lambda: app.start_snipping(5))),
            item('10 giây', lambda icon, menu_item: root.after(0, lambda: app.start_snipping(10))),
        )),
        item('Khởi động cùng Windows', toggle_startup, checked=lambda item: check_startup()),
        pystray.Menu.SEPARATOR,
        item('Kiểm tra cập nhật', check_for_updates),
        item(f'Giới thiệu (v{APP_VERSION})', lambda icon, menu_item: root.after(0, app.show_function_info)),
        pystray.Menu.SEPARATOR,
        item('Thoát', on_quit)
    ))
    _tray_icon_ref = icon  # let the hotkey listener notify through it
    threading.Thread(target=icon.run, daemon=True).start()
    
    root.mainloop()

if __name__ == '__main__':
    main()