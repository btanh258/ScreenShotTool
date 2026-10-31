# -*- coding: utf-8 -*-
"""ui_theme.py - ScreenShotTool design system.

Single source of truth for colour, typography, spacing, radii, glyphs and the
ttk style engine.  Every UI module (``ui_widgets``, ``ui_capture``,
``ui_dialogs``, ``ScreenShotTool.pyw``) imports its visual tokens from here so
that the whole application stays visually consistent.

DESIGN DIRECTION
----------------
A "pro tool" dark shell: deep slate chrome so that the captured screenshot is
the brightest thing on screen and therefore the visual focus.  A single azure
accent carries interactivity, a three-tier text ramp carries hierarchy, and a
4/8/12/16/24 spacing scale keeps rhythm regular.

FROZEN CONTRACT
---------------
Public names below are imported by sibling modules.  Do not rename them.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import ttk

__all__ = [
    "APP_TITLE", "FONT_FAMILY", "MONO_FAMILY",
    "COLORS", "SPACE", "RADIUS", "METRICS", "FONTS", "GLYPH",
    "font", "mono_font", "mix", "lighten", "darken", "round_rect",
    "apply_theme", "apply_dark_titlebar", "center_window", "ThemedBase",
    # style names
    "STYLE_APP_FRAME", "STYLE_CHROME_FRAME", "STYLE_PANEL_FRAME",
    "STYLE_CARD_FRAME", "STYLE_TITLE_LABEL", "STYLE_SUBTITLE_LABEL",
    "STYLE_BODY_LABEL", "STYLE_MUTED_LABEL", "STYLE_CHROME_LABEL",
    "STYLE_PRIMARY_BUTTON", "STYLE_SECONDARY_BUTTON", "STYLE_GHOST_BUTTON",
    "STYLE_DANGER_BUTTON", "STYLE_SUCCESS_BUTTON", "STYLE_ACTION_BUTTON",
    "STYLE_COMBOBOX", "STYLE_ENTRY", "STYLE_CHECKBUTTON",
    "STYLE_VSCROLL", "STYLE_HSCROLL", "STYLE_SEPARATOR",
]

APP_TITLE = "ScreenShotTool"
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


class _NS:
    """Mapping with attribute access: ``COLORS.accent`` and ``COLORS['accent']``.

    Deliberately NOT a ``dict`` subclass.  If it were, keys that collide with
    built-in dict methods (``copy``, ``keys``, ``items``, ``values``, ``get``...)
    would resolve to the method instead of the token -- ``GLYPH.copy`` would
    return ``dict.copy``, which Tk then stringifies into garbage.  Here every
    attribute lookup goes through ``_data``, so ``GLYPH.copy`` is the glyph.
    """

    __slots__ = ("_data",)

    def __init__(self, **kwargs):
        object.__setattr__(self, "_data", dict(kwargs))

    # -- attribute access ---------------------------------------------------
    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_data")[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self._data[name] = value

    # -- mapping protocol ---------------------------------------------------
    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"{type(self).__name__}({self._data!r})"

    # str/repr must not be shadowed by a token named "str" etc.
    def __str__(self):
        return repr(self)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def get(self, key, default=None):
        return self._data.get(key, default)


# --------------------------------------------------------------------------
# Colour ramp
# --------------------------------------------------------------------------
COLORS = _NS(
    # surfaces, darkest -> lightest
    app="#0B0D12",            # window background
    chrome="#14171F",         # toolbar / header bars
    panel="#1A1E27",          # panels, popovers
    elevated="#222734",       # cards, hovered rows
    hover="#2B3140",          # hover state
    canvas_bg="#08090D",      # the void behind the screenshot image

    # lines
    border="#2A3040",
    border_strong="#3A4356",
    focus_ring="#3B82F6",

    # text ramp
    text_primary="#F3F6FC",
    text_secondary="#A9B4C7",
    text_muted="#6C7789",
    text_on_accent="#FFFFFF",

    # accent + semantics
    accent="#3B82F6",
    accent_hover="#5B9BFF",
    accent_pressed="#2563EB",
    accent_soft="#1B2C4D",
    success="#10B981",
    success_hover="#34D399",
    success_pressed="#059669",
    danger="#EF4444",
    danger_hover="#F87171",
    danger_pressed="#DC2626",
    warning="#F59E0B",
    info="#60A5FA",

    # overlay
    scrim="#000000",
    hint_bg="#14171F",
    hint_text="#E7ECF5",
    selection="#3B82F6",
    selection_alt="#F59E0B",
)

# --------------------------------------------------------------------------
# Spacing / radius / metrics scale
# --------------------------------------------------------------------------
SPACE = _NS(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
RADIUS = _NS(sm=6, md=10, lg=14, xl=20, pill=999)
METRICS = _NS(
    toolbar_h=58,
    statusbar_h=30,
    rail_w=72,
    sidebar_w=248,
    control_h=34,
    control_h_sm=26,
    icon_size=18,
    toast_w=400,
)


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
def font(size: int = 10, weight: str = "normal", slant: str = "roman",
         family: str | None = None) -> tuple:
    """Build a Tk font tuple.  Prefer :data:`FONTS` for common roles."""
    spec: list = [family or FONT_FAMILY, size]
    if weight and weight != "normal":
        spec.append(weight)
    if slant and slant != "roman":
        spec.append(slant)
    return tuple(spec)


def mono_font(size: int = 9, weight: str = "normal") -> tuple:
    return font(size, weight, family=MONO_FAMILY)


FONTS = _NS(
    display=font(20, "bold"),
    title=font(15, "bold"),
    heading=font(11, "bold"),
    subheading=font(10, "bold"),
    body=font(10),
    body_strong=font(10, "bold"),
    small=font(9),
    small_strong=font(9, "bold"),
    tiny=font(8),
    mono=mono_font(9),
    mono_small=mono_font(8),
)


# --------------------------------------------------------------------------
# Glyphs - monochrome symbols from Segoe UI Symbol, so they inherit colour and
# stay crisp at any size.  (Delete / Escape etc. are handled as key names.)
# --------------------------------------------------------------------------
GLYPH = _NS(
    select="➤",
    crop="⛶",
    erase="⌫",
    pen="✎",
    highlight="✍",
    rect="▭",
    oval="◯",
    arrow="↗",
    text="T",
    blur="≋",
    undo="↶",
    redo="↷",
    copy="⧉",
    save="⤓",
    info="ⓘ",
    zoom_in="＋",
    zoom_out="－",
    fit="⤢",
    flip_h="⇋",
    flip_v="⇅",
    rotate_ccw="↺",
    rotate_cw="↻",
    close="✕",
    check="✔",
    warning="⚠",
    settings="⚙",
    random="⚄",
    keyboard="⌨",
    image="🖼",
    magnifier="⌕",
    target="◎",
)


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def _to_rgb(color: str) -> tuple:
    color = color.strip()
    if color.startswith("#"):
        color = color[1:]
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        raise ValueError(f"unsupported colour: {color!r}")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _to_hex(rgb: tuple) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(color_a: str, color_b: str, amount: float) -> str:
    """Linear blend.  ``amount=0`` -> color_a, ``amount=1`` -> color_b."""
    amount = max(0.0, min(1.0, float(amount)))
    ra, ga, ba = _to_rgb(color_a)
    rb, gb, bb = _to_rgb(color_b)
    return _to_hex((
        ra + (rb - ra) * amount,
        ga + (gb - ga) * amount,
        ba + (bb - ba) * amount,
    ))


def lighten(color: str, amount: float = 0.12) -> str:
    return mix(color, "#FFFFFF", amount)


def darken(color: str, amount: float = 0.12) -> str:
    return mix(color, "#000000", amount)


def readable_on(color: str) -> str:
    """Return a high-contrast text colour for the given background."""
    r, g, b = _to_rgb(color)
    luminance = (r * 0.299 + g * 0.587 + b * 0.114) / 255.0
    return COLORS.app if luminance > 0.6 else COLORS.text_on_accent


# --------------------------------------------------------------------------
# Canvas helpers
# --------------------------------------------------------------------------
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """Draw a rounded rectangle on ``canvas`` and return its item id.

    Uses a smoothed polygon: the portable way to get real rounded corners in
    plain Tk without image assets.
    """
    x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    radius = max(0.0, min(float(radius), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def center_window(window: tk.Misc, width: int | None = None,
                  height: int | None = None, parent: tk.Misc | None = None) -> None:
    """Centre ``window`` on its parent (or on the screen)."""
    window.update_idletasks()
    width = int(width or window.winfo_reqwidth())
    height = int(height or window.winfo_reqheight())
    if parent is not None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except tk.TclError:
            px = py = 0
            pw = window.winfo_screenwidth()
            ph = window.winfo_screenheight()
    else:
        px = py = 0
        pw = window.winfo_screenwidth()
        ph = window.winfo_screenheight()
    x = max(0, px + (pw - width) // 2)
    y = max(0, py + (ph - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def apply_dark_titlebar(window: tk.Misc) -> None:
    """Ask DWM for a dark native title bar.  Safe no-op on failure."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        enabled = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / legacy)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
    except Exception:
        pass


# --------------------------------------------------------------------------
# Style names (frozen contract)
# --------------------------------------------------------------------------
STYLE_APP_FRAME = "App.TFrame"
STYLE_CHROME_FRAME = "Chrome.TFrame"
STYLE_PANEL_FRAME = "Panel.TFrame"
STYLE_CARD_FRAME = "Card.TFrame"
STYLE_TITLE_LABEL = "Title.TLabel"
STYLE_SUBTITLE_LABEL = "Subtitle.TLabel"
STYLE_BODY_LABEL = "Body.TLabel"
STYLE_MUTED_LABEL = "Muted.TLabel"
STYLE_CHROME_LABEL = "Chrome.TLabel"
STYLE_PRIMARY_BUTTON = "Primary.TButton"
STYLE_SECONDARY_BUTTON = "Secondary.TButton"
STYLE_GHOST_BUTTON = "Ghost.TButton"
STYLE_DANGER_BUTTON = "Danger.TButton"
STYLE_SUCCESS_BUTTON = "Success.TButton"
STYLE_ACTION_BUTTON = "Action.TButton"      # legacy alias -> primary
STYLE_COMBOBOX = "Modern.TCombobox"
STYLE_ENTRY = "Modern.TEntry"
STYLE_CHECKBUTTON = "Modern.TCheckbutton"
STYLE_VSCROLL = "Modern.Vertical.TScrollbar"
STYLE_HSCROLL = "Modern.Horizontal.TScrollbar"
STYLE_SEPARATOR = "Modern.TSeparator"


def apply_theme(root: tk.Misc):
    """Install the ScreenShotTool look on ``root``'s ttk style engine.

    Idempotent and safe to call for every Toplevel.  Returns the ``ttk.Style``
    instance so callers can add their own variants.
    """
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    w = root.winfo_toplevel()
    try:
        w.configure(bg=COLORS.app)
    except tk.TclError:
        pass

    # ---- frames -----------------------------------------------------------
    for name, background in (
        (STYLE_APP_FRAME, COLORS.app),
        (STYLE_CHROME_FRAME, COLORS.chrome),
        (STYLE_PANEL_FRAME, COLORS.panel),
        (STYLE_CARD_FRAME, COLORS.elevated),
    ):
        style.configure(name, background=background, borderwidth=0, relief="flat")
    style.configure("TFrame", background=COLORS.app, borderwidth=0)

    # ---- labels -----------------------------------------------------------
    for name, foreground, fnt, background in (
        (STYLE_TITLE_LABEL, COLORS.text_primary, FONTS.title, COLORS.app),
        (STYLE_SUBTITLE_LABEL, COLORS.text_secondary, FONTS.small, COLORS.app),
        (STYLE_BODY_LABEL, COLORS.text_primary, FONTS.body, COLORS.app),
        (STYLE_MUTED_LABEL, COLORS.text_muted, FONTS.small, COLORS.app),
        (STYLE_CHROME_LABEL, COLORS.text_secondary, FONTS.small, COLORS.chrome),
    ):
        style.configure(name, background=background, foreground=foreground, font=fnt)
    style.configure("TLabel", background=COLORS.app, foreground=COLORS.text_primary,
                    font=FONTS.body)

    # ---- buttons ----------------------------------------------------------
    def button(name, bg, fg, hover, pressed, *, border=None, fontspec=FONTS.body,
               disabled_bg=None):
        style.configure(name, background=bg, foreground=fg, font=fontspec,
                        borderwidth=0, focusthickness=0, relief="flat",
                        padding=(14, 8), anchor="center")
        if border:
            style.configure(name, bordercolor=border, borderwidth=1)
        # NOTE: ttk ``map()`` replaces an option's state map instead of merging,
        # so every state must be supplied in a single call.
        style.map(
            name,
            background=[("disabled", disabled_bg or COLORS.elevated),
                        ("pressed", pressed), ("active", hover)],
            foreground=[("disabled", COLORS.text_muted)],
            bordercolor=[("disabled", COLORS.border), ("active", border or hover)],
        )

    button(STYLE_PRIMARY_BUTTON, COLORS.accent, COLORS.text_on_accent,
           COLORS.accent_hover, COLORS.accent_pressed, fontspec=FONTS.body_strong,
           disabled_bg=COLORS.panel)
    # Secondary rests on COLORS.elevated, so its disabled fill is a step *down*
    # (COLORS.panel) rather than the same neutral it would otherwise inherit.
    button(STYLE_SECONDARY_BUTTON, COLORS.elevated, COLORS.text_primary,
           COLORS.hover, COLORS.border_strong, border=COLORS.border_strong,
           disabled_bg=COLORS.panel)
    # Ghost rests on COLORS.chrome; hover must still be visibly lighter.
    button(STYLE_GHOST_BUTTON, COLORS.chrome, COLORS.text_secondary,
           COLORS.hover, COLORS.elevated, disabled_bg=COLORS.panel)
    button(STYLE_DANGER_BUTTON, COLORS.danger, COLORS.text_on_accent,
           COLORS.danger_hover, COLORS.danger_pressed, fontspec=FONTS.body_strong,
           disabled_bg=COLORS.panel)
    button(STYLE_SUCCESS_BUTTON, COLORS.success, COLORS.text_on_accent,
           COLORS.success_hover, COLORS.success_pressed, fontspec=FONTS.body_strong,
           disabled_bg=COLORS.panel)
    button(STYLE_ACTION_BUTTON, COLORS.accent, COLORS.text_on_accent,
           COLORS.accent_hover, COLORS.accent_pressed, fontspec=FONTS.body_strong,
           disabled_bg=COLORS.panel)

    # Legacy toolbutton style - still themed so no surface is left unstyled.
    style.configure("Toolbutton", background=COLORS.chrome, foreground=COLORS.text_secondary,
                    font=FONTS.small, padding=(10, 6), borderwidth=0, relief="flat",
                    focuscolor=COLORS.chrome)
    style.map("Toolbutton",
              background=[("selected", COLORS.accent_soft), ("active", COLORS.hover)],
              foreground=[("selected", COLORS.accent_hover), ("active", COLORS.text_primary)],
              indicatorcolor=[("selected", COLORS.accent)])

    # ---- inputs -----------------------------------------------------------
    style.configure(STYLE_COMBOBOX,
                    fieldbackground=COLORS.elevated, background=COLORS.elevated,
                    foreground=COLORS.text_primary, arrowcolor=COLORS.text_secondary,
                    bordercolor=COLORS.border_strong, lightcolor=COLORS.elevated,
                    darkcolor=COLORS.elevated, selectbackground=COLORS.elevated,
                    selectforeground=COLORS.text_primary, padding=(8, 4),
                    relief="flat", borderwidth=1, arrowsize=14)
    style.map(STYLE_COMBOBOX,
              fieldbackground=[("readonly", COLORS.elevated), ("disabled", COLORS.panel)],
              foreground=[("readonly", COLORS.text_primary), ("disabled", COLORS.text_muted)],
              bordercolor=[("focus", COLORS.focus_ring), ("hover", COLORS.border_strong)],
              arrowcolor=[("active", COLORS.accent_hover)],
              selectbackground=[("readonly", COLORS.elevated)],
              selectforeground=[("readonly", COLORS.text_primary)])

    style.configure(STYLE_ENTRY,
                    fieldbackground=COLORS.elevated, background=COLORS.elevated,
                    foreground=COLORS.text_primary, insertcolor=COLORS.text_primary,
                    bordercolor=COLORS.border_strong, lightcolor=COLORS.border_strong,
                    darkcolor=COLORS.border_strong, padding=(8, 6),
                    relief="flat", borderwidth=1)
    style.map(STYLE_ENTRY,
              fieldbackground=[("focus", COLORS.panel), ("disabled", COLORS.panel)],
              bordercolor=[("focus", COLORS.focus_ring)],
              foreground=[("disabled", COLORS.text_muted)])

    style.configure(STYLE_CHECKBUTTON,
                    background=COLORS.chrome, foreground=COLORS.text_secondary,
                    focuscolor=COLORS.chrome, font=FONTS.small,
                    indicatorcolor=COLORS.panel, indicatorrelief="flat",
                    bordercolor=COLORS.border_strong, padding=(2, 2))
    style.map(STYLE_CHECKBUTTON,
              background=[("active", COLORS.chrome)],
              foreground=[("selected", COLORS.text_primary), ("active", COLORS.text_primary)],
              indicatorcolor=[("selected", COLORS.accent), ("pressed", COLORS.accent_pressed)])

    # ---- scrollbars -------------------------------------------------------
    for name, orient in ((STYLE_VSCROLL, "vertical"), (STYLE_HSCROLL, "horizontal")):
        style.configure(name, background=COLORS.border, troughcolor=COLORS.app,
                        bordercolor=COLORS.app, arrowcolor=COLORS.text_muted,
                        darkcolor=COLORS.border, lightcolor=COLORS.border,
                        relief="flat", borderwidth=0, arrowsize=12,
                        width=12 if orient == "vertical" else 0)
        style.map(name,
                  background=[("pressed", COLORS.accent), ("active", COLORS.border_strong)],
                  arrowcolor=[("active", COLORS.text_secondary)])

    style.configure(STYLE_SEPARATOR, background=COLORS.border)

    # ---- native tk defaults that ttk cannot reach -------------------------
    root.option_add("*TCombobox*Listbox.background", COLORS.elevated)
    root.option_add("*TCombobox*Listbox.foreground", COLORS.text_primary)
    root.option_add("*TCombobox*Listbox.selectBackground", COLORS.accent)
    root.option_add("*TCombobox*Listbox.selectForeground", COLORS.text_on_accent)
    root.option_add("*TCombobox*Listbox.font", FONTS.body)
    root.option_add("*Menu.background", COLORS.panel)
    root.option_add("*Menu.foreground", COLORS.text_primary)
    root.option_add("*Menu.activeBackground", COLORS.accent)
    root.option_add("*Menu.activeForeground", COLORS.text_on_accent)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    return style


# --------------------------------------------------------------------------
# ThemedBase - canvas widget with ttk-style ``config`` compatibility
# --------------------------------------------------------------------------
class ThemedBase(tk.Canvas):
    """Base class for the custom rounded widgets.

    Custom widgets are drawn on a ``tk.Canvas`` (the only way to get rounded
    corners and real hover states in stock Tk).  Application code, however,
    still speaks the classic widget dialect - ``.config(state=...)``,
    ``.cget("text")``, ``.config(bg=...)`` - so this base translates those
    options instead of raising ``TclError``.
    """

    def __init__(self, master, *, surface: str | None = None, height: int = METRICS.control_h,
                 width: int | None = None, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        kwargs.setdefault("relief", "flat")
        kwargs.pop("bd", None)
        self._surface = surface or _surface_of(master)
        kwargs.setdefault("bg", self._surface)
        if width is not None:
            kwargs["width"] = width
        super().__init__(master, height=height, **kwargs)
        self._state = "normal"
        self._text = ""
        self._hovering = False
        self._pressed = False
        self._enabled = True
        # Subclasses call ``configure()`` while still assigning their own
        # attributes; rendering before they finish would raise AttributeError.
        self._ready = False
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _finish_init(self):
        """Mark construction complete and paint the widget once."""
        self._ready = True
        self._render()

    def _safe_render(self):
        """Repaint, but never during construction or after destruction.

        Bound to Tk variable traces, which can fire while the owning widget is
        still being built.
        """
        if getattr(self, "_ready", False) and getattr(self, "_enabled", False):
            self._render()

    # -- state plumbing -----------------------------------------------------
    def _on_destroy(self, _event=None):
        self._enabled = False
        self._ready = False

    def _on_enter(self, _event=None):
        self._hovering = True
        if self._is_enabled():
            self._render()

    def _on_leave(self, _event=None):
        self._hovering = False
        self._pressed = False
        if self._is_enabled():
            self._render()

    def _is_enabled(self) -> bool:
        return self._enabled and self._state != "disabled" and getattr(self, "_ready", False)

    def _render(self):  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    # -- classic widget dialect --------------------------------------------
    _TEXT_KEYS = ("text",)
    _STATE_KEYS = ("state",)
    _SURFACE_KEYS = ("bg", "background")
    _IGNORED_KEYS = ("style", "compound", "image", "takefocus", "focuscolor",
                     "highlightcolor", "activebackground", "activeforeground",
                     "disabledforeground", "relief", "overrelief", "padx", "pady",
                     "wraplength", "justify", "anchor", "default", "underline")

    def configure(self, cget=False, **kwargs):
        passthrough = {}
        for key, value in kwargs.items():
            if key in self._TEXT_KEYS:
                self._text = "" if value is None else str(value)
            elif key in self._STATE_KEYS:
                self._state = str(value)
            elif key in self._SURFACE_KEYS:
                self._surface = str(value)
                try:
                    super().configure(bg=self._surface)
                except tk.TclError:
                    pass
            elif key in ("cursor", "command"):
                if key == "command":
                    self._command = value
                else:
                    super().configure(cursor=value)
            elif key in self._IGNORED_KEYS:
                continue
            else:
                passthrough[key] = value
        if passthrough:
            try:
                super().configure(**passthrough)
            except tk.TclError:
                pass
        # Repaint only once the subclass has finished wiring its own
        # attributes; during construction ``_finish_init`` paints instead.
        if getattr(self, "_ready", False):
            self._render()
        return None

    config = configure

    def cget(self, key):
        if key in self._TEXT_KEYS:
            return self._text
        if key in self._STATE_KEYS:
            return self._state
        if key in self._SURFACE_KEYS:
            return self._surface
        return super().cget(key)

    # convenience
    def set_text(self, text):
        self.configure(text=text)

    def get_text(self):
        return self._text

    def set_enabled(self, enabled: bool):
        self.configure(state="normal" if enabled else "disabled")

    def invoke(self):
        command = getattr(self, "_command", None)
        if callable(command) and self._is_enabled():
            command()


def _surface_of(master) -> str:
    """Best-effort read of the master's background so custom widgets blend in."""
    try:
        return master.cget("background")
    except Exception:
        pass
    try:
        return master.cget("bg")
    except Exception:
        return COLORS.chrome
