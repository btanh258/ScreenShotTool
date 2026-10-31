# -*- coding: utf-8 -*-
"""ui_widgets.py - ScreenShotTool custom widget library.

Stock Tk cannot draw a rounded corner, a soft hover state or a pill toggle, so
every interactive control in the redesigned UI is a small ``tk.Canvas`` subclass
that paints itself.  To keep the rest of the application readable, each widget
speaks the classic Tk dialect as well: ``.config(state="disabled")``,
``.cget("text")``, ``.config(bg=...)`` and ``.invoke()`` all behave the way
application code expects (see :class:`ui_theme.ThemedBase`).

Everything here is theme-driven - no hard-coded colours - so the whole product
restyles from :mod:`ui_theme`.

WIDGETS
-------
RailButton      vertical icon+caption tool button for the left tool rail
IconButton      square glyph-only button (undo, redo, zoom, close)
PillButton      rounded text button: primary/secondary/ghost/danger/success
SegmentedControl mutually exclusive segmented switch
ColorSwatch     current-colour well with palette popover + random
NumberStepper   compact -/+ numeric field with drag-free arrows
Slider          canvas-drawn track + handle for stroke width
ToggleSwitch    animated-ish on/off switch with caption
InspectorSection  titled group container for the right inspector
Tooltip         delayed hover tooltip for any widget
Divider         hairline separator
StatusBar       bottom status strip with live zoom / size / hint readouts
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import ui_theme as T

__all__ = [
    "RailButton", "IconButton", "PillButton", "SegmentedControl", "ColorSwatch",
    "NumberStepper", "Slider", "ToggleSwitch", "InspectorSection", "Tooltip",
    "Divider", "StatusBar", "measure_text",
]


def measure_text(spec, text: str) -> int:
    """Pixel width of ``text`` in ``spec`` (a Tk font tuple)."""
    try:
        return tkfont.Font(font=spec).measure(text)
    except Exception:
        return int(len(text) * 7)


def _draw_glyph(canvas, x, y, glyph, color, size, weight="normal"):
    return canvas.create_text(x, y, text=glyph, fill=color,
                              font=(T.FONT_FAMILY, size, weight))


# ==========================================================================
# Tooltip
# ==========================================================================
class Tooltip:
    """Delayed hover tooltip.  ``Tooltip(widget, "Chụp màn hình  (Alt+X)")``."""

    _open: "Tooltip | None" = None
    _delay = 420
    # Hints can be a full sentence ("kéo vùng cần giữ · Enter để cắt"), so the
    # label wraps instead of running off the edge of the screen.
    _wrap = 340

    def __init__(self, widget, text, *, delay=None, placement="right"):
        self.widget = widget
        self.text = text
        self.delay = delay if delay is not None else Tooltip._delay
        self.placement = placement
        self._after_id = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        try:
            if not self.widget.winfo_viewable():
                return
        except tk.TclError:
            return
        if Tooltip._open is not None:
            Tooltip._open._hide()
        tip = tk.Toplevel(self.widget)
        self._window = tip
        Tooltip._open = self
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        try:
            tip.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        frame = tk.Frame(tip, bg=T.COLORS.border_strong)
        frame.pack()
        label = tk.Label(frame, text=self.text, bg=T.COLORS.elevated,
                         fg=T.COLORS.text_primary, font=T.FONTS.small,
                         padx=10, pady=6, justify="left", anchor="w",
                         wraplength=Tooltip._wrap, borderwidth=0,
                         highlightthickness=0)
        label.pack(padx=1, pady=1)
        tip.update_idletasks()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + (self.widget.winfo_height() - h) // 2
        if self.placement == "below":
            x = self.widget.winfo_rootx() + (self.widget.winfo_width() - w) // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        if x + w > self.widget.winfo_screenwidth():
            x = self.widget.winfo_rootx() - w - 8
        if y + h > self.widget.winfo_screenheight():
            y = self.widget.winfo_screenheight() - h - 4
        tip.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        try:
            tip.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    def _hide(self, _event=None):
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
        if Tooltip._open is self:
            Tooltip._open = None


# ==========================================================================
# Divider
# ==========================================================================
class Divider(tk.Frame):
    """1px hairline, horizontal by default."""

    def __init__(self, master, orient="horizontal", *, color=None, pad=0, **kwargs):
        bg = color or T.COLORS.border
        if orient == "vertical":
            super().__init__(master, width=1, bg=bg, **kwargs)
            self.pack_propagate(False)
        else:
            super().__init__(master, height=1, bg=bg, **kwargs)
        self._orient = orient


# ==========================================================================
# RailButton - left tool rail
# ==========================================================================
class RailButton(T.ThemedBase):
    """Icon-above-caption button used for the ten editor tools."""

    def __init__(self, master, glyph, caption, value, variable, *, command=None,
                 width=60, height=52, tooltip=None):
        super().__init__(master, surface=T.COLORS.chrome, width=width, height=height)
        self.configure(width=width, height=height)
        self.glyph = glyph
        self.caption = caption
        self.value = value
        self.variable = variable
        self._command = command
        self._radius = T.RADIUS.md
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.variable.trace_add("write", lambda *_: self._safe_render())
        if tooltip:
            Tooltip(self, tooltip)
        self._finish_init()

    def _selected(self) -> bool:
        try:
            return self.variable.get() == self.value
        except Exception:
            return False

    def _on_press(self, _event=None):
        if not self._is_enabled():
            return "break"
        self._pressed = True
        self._render()
        return "break"

    def _on_release(self, event=None):
        if not self._is_enabled():
            return "break"
        was_pressed = self._pressed
        self._pressed = False
        inside = True
        if event is not None:
            inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if was_pressed and inside:
            self.variable.set(self.value)
            self.invoke()
        self._render()
        return "break"

    def _render(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        selected = self._selected()
        enabled = self._is_enabled()
        if selected:
            bg = T.COLORS.accent_soft
            fg = T.COLORS.accent_hover
        elif self._pressed:
            bg = T.COLORS.border
            fg = T.COLORS.text_primary
        elif self._hovering and enabled:
            bg = T.COLORS.hover
            fg = T.COLORS.text_primary
        else:
            bg = T.COLORS.chrome
            fg = T.COLORS.text_secondary
        if not enabled:
            fg = T.COLORS.text_muted
        T.round_rect(self, 4, 3, w - 4, h - 3, self._radius, fill=bg, outline="")
        if selected:
            self.create_rectangle(4, 12, 6, h - 12, fill=T.COLORS.accent, outline="")
        _draw_glyph(self, w / 2, h / 2 - 7, self.glyph, fg, 15)
        self.create_text(w / 2, h / 2 + 12, text=self.caption, fill=fg,
                         font=(T.FONT_FAMILY, 8), anchor="center")


# ==========================================================================
# IconButton
# ==========================================================================
class IconButton(T.ThemedBase):
    """Square glyph-only button with hover/press/disabled states."""

    def __init__(self, master, glyph, command=None, *, size=34, glyph_size=14,
                 variant="ghost", tooltip=None, surface=None):
        super().__init__(master, surface=surface or T.COLORS.chrome,
                         width=size, height=size)
        self.configure(width=size, height=size)
        self.glyph = glyph
        self.glyph_size = glyph_size
        self.variant = variant
        self._command = command
        self._pad = 2
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        if tooltip:
            Tooltip(self, tooltip)
        self._finish_init()

    def set_glyph(self, glyph):
        self.glyph = glyph
        self._render()

    def _on_press(self, _event=None):
        if not self._is_enabled():
            return "break"
        self._pressed = True
        self._render()
        return "break"

    def _on_release(self, event=None):
        if not self._is_enabled():
            return "break"
        was_pressed = self._pressed
        self._pressed = False
        inside = True
        if event is not None:
            inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._render()
        if was_pressed and inside:
            self.invoke()
        return "break"

    def _colors(self):
        enabled = self._is_enabled()
        if not enabled:
            return self._surface, T.COLORS.text_muted
        if self.variant == "primary":
            base, fg = T.COLORS.accent, T.COLORS.text_on_accent
            hover, pressed = T.COLORS.accent_hover, T.COLORS.accent_pressed
        elif self.variant == "danger":
            base, fg = T.COLORS.danger, T.COLORS.text_on_accent
            hover, pressed = T.COLORS.danger_hover, T.COLORS.danger_pressed
        elif self.variant == "success":
            base, fg = T.COLORS.success, T.COLORS.text_on_accent
            hover, pressed = T.COLORS.success_hover, T.COLORS.success_pressed
        else:
            base, fg = self._surface, T.COLORS.text_secondary
            hover, pressed = T.COLORS.hover, T.COLORS.border
        if self._pressed and self.variant == "ghost":
            base = pressed
        elif self._hovering:
            base = hover
        if self.variant != "ghost" and self._hovering:
            fg = T.COLORS.text_on_accent
        elif self.variant == "ghost" and (self._hovering or self._pressed):
            fg = T.COLORS.text_primary
        return base, fg

    def _render(self):
        self.delete("all")
        w = int(self.winfo_reqwidth())
        h = int(self.winfo_reqheight())
        bg, fg = self._colors()
        if bg != self._surface:
            T.round_rect(self, self._pad, self._pad, w - self._pad, h - self._pad,
                         T.RADIUS.sm, fill=bg, outline="")
        _draw_glyph(self, w / 2, h / 2, self.glyph, fg, self.glyph_size)


# ==========================================================================
# PillButton
# ==========================================================================
class PillButton(T.ThemedBase):
    """Rounded text button.  Variants: primary, secondary, ghost, danger, success."""

    @staticmethod
    def _variants():
        """Variant colours, resolved at call time.

        This used to be a class-level dict. Class bodies run once at import, so
        every button built afterwards kept the palette that happened to be
        active then - in light mode the Save button rendered as a dark slab
        because it was bound to the dark "secondary" fill. Reading the tokens per
        call keeps buttons in step with the active theme.
        """
        return {
            "primary": (T.COLORS.accent, T.COLORS.text_on_accent,
                        T.COLORS.accent_hover, T.COLORS.accent_pressed, None),
            "success": (T.COLORS.success, T.COLORS.text_on_accent,
                        T.COLORS.success_hover, T.COLORS.success_pressed, None),
            "danger": (T.COLORS.danger, T.COLORS.text_on_accent,
                       T.COLORS.danger_hover, T.COLORS.danger_pressed, None),
            "secondary": (T.COLORS.elevated, T.COLORS.text_primary,
                          T.COLORS.hover, T.COLORS.border, T.COLORS.border_strong),
            "ghost": (None, T.COLORS.text_secondary,
                      T.COLORS.hover, T.COLORS.border, None),
        }

    def __init__(self, master, text="", command=None, *, variant="secondary",
                 glyph=None, fontspec=None, padx=16, height=None, tooltip=None,
                 surface=None, min_width=0):
        height = height or T.METRICS.control_h
        self.fontspec = fontspec or T.FONTS.body
        self.glyph = glyph
        self.padx = padx
        self.min_width = min_width
        width = self._measure(text)
        super().__init__(master, surface=surface or T.COLORS.chrome,
                         width=width, height=height)
        self.configure(width=width, height=height)
        self.variant = variant
        self._command = command
        self._text = text
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        if tooltip:
            Tooltip(self, tooltip)
        self._finish_init()

    def _measure(self, text):
        glyph_w = 20 if self.glyph else 0
        return max(self.min_width, measure_text(self.fontspec, text) + self.padx * 2 + glyph_w)

    def set_text(self, text):
        self._text = text
        width = self._measure(text)
        self.configure(width=width)
        self._render()

    def _on_press(self, _event=None):
        if not self._is_enabled():
            return "break"
        self._pressed = True
        self._render()
        return "break"

    def _on_release(self, event=None):
        if not self._is_enabled():
            return "break"
        was_pressed = self._pressed
        self._pressed = False
        inside = True
        if event is not None:
            inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._render()
        if was_pressed and inside:
            self.invoke()
        return "break"

    def _render(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        variants = self._variants()
        base, fg, hover, pressed, border = variants.get(
            self.variant, variants["secondary"])
        bg = base if base else self._surface
        outline = border or ""
        if not self._is_enabled():
            bg, fg = T.COLORS.elevated, T.COLORS.text_muted
            outline = ""
        elif self._pressed:
            bg = pressed
        elif self._hovering:
            bg = hover
        T.round_rect(self, 0, 0, w - 1, h - 1, T.RADIUS.sm, fill=bg, outline=outline)
        if self.glyph:
            gx = self.padx - 2
            _draw_glyph(self, gx, h / 2, self.glyph, fg, 12)
            self.create_text(gx + 14, h / 2, text=self._text, fill=fg,
                             font=self.fontspec, anchor="w")
        else:
            self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self.fontspec)


# ==========================================================================
# SegmentedControl
# ==========================================================================
class SegmentedControl(T.ThemedBase):
    """Mutually exclusive pill switch, e.g. Light / Dark or 1:1 / Fit."""

    def __init__(self, master, options, variable=None, command=None, *,
                 height=None, surface=None, fontspec=None, padding=12):
        self.options = list(options)          # list of (value, caption) or value
        self.fontspec = fontspec or T.FONTS.small
        self.padding = padding
        self.variable = variable or tk.StringVar(value=self._value_of(self.options[0]))
        self._command = command
        height = height or T.METRICS.control_h
        seg_w = max(measure_text(self.fontspec, self._label_of(o)) + padding * 2
                    for o in self.options)
        width = seg_w * len(self.options) + 4
        super().__init__(master, surface=surface or T.COLORS.chrome,
                         width=width, height=height)
        self.configure(width=width, height=height)
        self.seg_w = seg_w
        self.bind("<Button-1>", self._on_click)
        self.variable.trace_add("write", lambda *_: self._safe_render())
        self._finish_init()

    @staticmethod
    def _value_of(option):
        return option[0] if isinstance(option, (tuple, list)) else option

    @staticmethod
    def _label_of(option):
        return option[1] if isinstance(option, (tuple, list)) else str(option)

    def _on_click(self, event):
        if not self._is_enabled():
            return "break"
        index = int((event.x - 2) // self.seg_w)
        index = max(0, min(len(self.options) - 1, index))
        self.variable.set(self._value_of(self.options[index]))
        if callable(self._command):
            self._command(self.variable.get())
        return "break"

    def _render(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        T.round_rect(self, 0, 0, w - 1, h - 1, T.RADIUS.sm,
                     fill=T.COLORS.panel, outline=T.COLORS.border)
        current = self.variable.get()
        for index, option in enumerate(self.options):
            x1 = 2 + index * self.seg_w
            x2 = x1 + self.seg_w
            active = self._value_of(option) == current
            if active:
                T.round_rect(self, x1, 2, x2, h - 2, T.RADIUS.sm - 1,
                             fill=T.COLORS.accent, outline="")
            fg = T.COLORS.text_on_accent if active else T.COLORS.text_secondary
            self.create_text((x1 + x2) / 2, h / 2, text=self._label_of(option),
                             fill=fg, font=self.fontspec)


# ==========================================================================
# ColorSwatch
# ==========================================================================
class ColorSwatch(T.ThemedBase):
    """Current-colour well.  Click -> palette popover; right-click -> picker."""

    def __init__(self, master, color="#ff0000", *, command=None, random_command=None,
                 palette=None, size=30, tooltip=None):
        super().__init__(master, surface=T.COLORS.chrome, width=size, height=size)
        self.configure(width=size, height=size)
        self.color = color
        self._command = command
        self.random_command = random_command
        self.palette = list(palette or [
            "#ff3b30", "#ff9500", "#ffcc00", "#34c759",
            "#00c7be", "#0a84ff", "#5e5ce6", "#bf5af2",
            "#000000", "#6e6e73", "#aeaeb2", "#ffffff",
        ])
        self._popup = None
        self.bind("<Button-1>", self._toggle_popup)
        self.bind("<Button-3>", self._pick_custom)
        self.bind("<MouseWheel>", self._cycle)
        if tooltip:
            Tooltip(self, tooltip)
        self._finish_init()

    # -- public API ---------------------------------------------------------
    def configure(self, cget=False, **kwargs):
        """``config(bg=...)`` sets the *swatch colour*, matching legacy usage.

        The original toolbar mutated the colour well with
        ``color_btn.config(bg=new_color)``; here ``bg`` means "the colour this
        well displays" rather than the widget surface.
        """
        color = None
        if "bg" in kwargs:
            color = kwargs.pop("bg")
        if "background" in kwargs:
            color = kwargs.pop("background")
        if color is not None:
            self.set_color(str(color))
        if kwargs:
            super().configure(cget=cget, **kwargs)
        return None

    config = configure

    def cget(self, key):
        # Symmetric with configure(): "bg" reports the swatch colour.
        if key in ("bg", "background"):
            return self.color
        return super().cget(key)

    def set_color(self, color):
        self.color = color
        if color and color.lower() not in [c.lower() for c in self.palette]:
            self.palette.append(color)
        self._render()

    get_color = lambda self: self.color  # noqa: E731

    # -- events -------------------------------------------------------------
    def _cycle(self, event):
        if not self.palette:
            return "break"
        try:
            index = [c.lower() for c in self.palette].index(self.color.lower())
        except ValueError:
            index = 0
        step = 1 if getattr(event, "delta", 0) > 0 else -1
        self.set_color(self.palette[(index + step) % len(self.palette)])
        if callable(self._command):
            self._command(self.color)
        return "break"

    def _pick_custom(self, _event=None):
        from tkinter import colorchooser
        chosen = colorchooser.askcolor(color=self.color, title="Chọn màu")[1]
        if chosen:
            self.set_color(chosen)
            if callable(self._command):
                self._command(self.color)

    def _toggle_popup(self, _event=None):
        if self._popup is not None:
            self._close_popup()
            return "break"
        popup = tk.Toplevel(self)
        self._popup = popup
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)
        outer = tk.Frame(popup, bg=T.COLORS.border_strong)
        outer.pack()
        body = tk.Frame(outer, bg=T.COLORS.elevated, padx=8, pady=8)
        body.pack(padx=1, pady=1)
        tk.Label(body, text="Bảng màu", bg=T.COLORS.elevated, fg=T.COLORS.text_secondary,
                 font=T.FONTS.small).grid(row=0, column=0, columnspan=4, sticky="w",
                                          pady=(0, 6))
        for index, swatch in enumerate(self.palette):
            cell = tk.Frame(body, bg=swatch, width=26, height=26, cursor="hand2",
                            highlightthickness=1,
                            highlightbackground=T.COLORS.border_strong)
            cell.grid(row=1 + index // 4, column=index % 4, padx=3, pady=3)
            cell.pack_propagate(False)
            cell.bind("<Button-1>", lambda e, c=swatch: self._choose(c))
        row = 1 + (len(self.palette) + 3) // 4
        more = tk.Label(body, text="＋  Màu tùy chọn", bg=T.COLORS.elevated,
                        fg=T.COLORS.accent, font=T.FONTS.small, cursor="hand2",
                        anchor="w")
        more.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        more.bind("<Button-1>", lambda e: (self._close_popup(), self._pick_custom()))
        if self.random_command:
            rnd = tk.Label(body, text="⚄  Ngẫu nhiên", bg=T.COLORS.elevated,
                           fg=T.COLORS.text_secondary, font=T.FONTS.small,
                           cursor="hand2", anchor="e")
            rnd.grid(row=row, column=2, columnspan=2, sticky="e", pady=(6, 0))
            rnd.bind("<Button-1>", lambda e: (self._close_popup(), self.random_command()))
        popup.update_idletasks()
        x = self.winfo_rootx() - popup.winfo_reqwidth() - 10
        y = self.winfo_rooty() - 8
        if x < 0:
            x = self.winfo_rootx() + self.winfo_width() + 10
        popup.wm_geometry(f"+{x}+{y}")
        popup.bind("<FocusOut>", lambda e: self._close_popup())
        popup.bind("<Escape>", lambda e: self._close_popup())
        popup.focus_set()
        return "break"

    def _choose(self, color):
        self._close_popup()
        self.set_color(color)
        if callable(self._command):
            self._command(color)

    def _close_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _on_destroy(self, _event=None):
        self._close_popup()
        super()._on_destroy(_event)

    def _render(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        # checkerboard so transparency reads correctly, then the colour well
        T.round_rect(self, 0, 0, w - 1, h - 1, T.RADIUS.sm,
                     fill=T.COLORS.panel, outline=T.COLORS.border_strong)
        T.round_rect(self, 3, 3, w - 4, h - 4, T.RADIUS.sm - 2,
                     fill=self.color, outline=T.COLORS.border)
        if self._hovering:
            self.create_rectangle(0, 0, w - 1, h - 1, outline=T.COLORS.focus_ring)


# ==========================================================================
# NumberStepper
# ==========================================================================
class NumberStepper(T.ThemedBase):
    """Compact numeric field with -/+ buttons and optional slider popover."""

    def __init__(self, master, variable, *, minimum=1, maximum=50, step=1,
                 width=118, height=None, command=None, tooltip=None):
        height = height or T.METRICS.control_h
        super().__init__(master, surface=T.COLORS.chrome, width=width, height=height)
        self.configure(width=width, height=height)
        self.variable = variable
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self._command = command
        self._zone = None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: (setattr(self, "_zone", None), self._safe_render()))
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.variable.trace_add("write", lambda *_: self._safe_render())
        if tooltip:
            Tooltip(self, tooltip)
        self._finish_init()

    def _value(self):
        try:
            return int(self.variable.get())
        except Exception:
            return self.minimum

    def _set(self, value):
        value = max(self.minimum, min(self.maximum, int(value)))
        self.variable.set(value)
        if callable(self._command):
            self._command(value)

    def _on_motion(self, event):
        zone = "minus" if event.x < 34 else ("plus" if event.x > self.winfo_reqwidth() - 34 else "field")
        if zone != self._zone:
            self._zone = zone
            self._render()

    def _on_click(self, event):
        if event.x < 34:
            self._set(self._value() - self.step)
        elif event.x > self.winfo_reqwidth() - 34:
            self._set(self._value() + self.step)
        return "break"

    def _on_wheel(self, event):
        self._set(self._value() + (self.step if getattr(event, "delta", 0) > 0 else -self.step))
        return "break"

    def _render(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        T.round_rect(self, 0, 0, w - 1, h - 1, T.RADIUS.sm,
                     fill=T.COLORS.elevated, outline=T.COLORS.border_strong)
        hover_minus = self._zone == "minus" and self._hovering
        hover_plus = self._zone == "plus" and self._hovering
        if hover_minus:
            T.round_rect(self, 2, 2, 32, h - 2, T.RADIUS.sm - 1, fill=T.COLORS.hover, outline="")
        if hover_plus:
            T.round_rect(self, w - 33, 2, w - 2, h - 2, T.RADIUS.sm - 1, fill=T.COLORS.hover, outline="")
        _draw_glyph(self, 17, h / 2, "−", T.COLORS.text_secondary, 13, "bold")
        _draw_glyph(self, w - 17, h / 2, "＋", T.COLORS.text_secondary, 12, "bold")
        self.create_text(w / 2, h / 2, text=str(self._value()), fill=T.COLORS.text_primary,
                         font=T.FONTS.body_strong)


# ==========================================================================
# Slider
# ==========================================================================
class Slider(T.ThemedBase):
    """Canvas-drawn horizontal slider bound to a Tk variable."""

    def __init__(self, master, variable, *, minimum=1, maximum=50, step=1,
                 width=200, height=28, command=None):
        super().__init__(master, surface=T.COLORS.chrome, width=width, height=height)
        self.configure(width=width, height=height)
        self.variable = variable
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self._command = command
        self._dragging = False
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_dragging", False))
        self.variable.trace_add("write", lambda *_: self._safe_render())
        self._finish_init()

    def _track(self):
        w = int(self.winfo_reqwidth())
        return 10, w - 10

    def _value(self):
        try:
            return int(self.variable.get())
        except Exception:
            return self.minimum

    def _ratio(self):
        span = max(1, self.maximum - self.minimum)
        return (self._value() - self.minimum) / span

    def _apply(self, x):
        x1, x2 = self._track()
        ratio = max(0.0, min(1.0, (x - x1) / max(1, x2 - x1)))
        raw = self.minimum + ratio * (self.maximum - self.minimum)
        stepped = self.minimum + round((raw - self.minimum) / self.step) * self.step
        value = max(self.minimum, min(self.maximum, int(stepped)))
        if value != self._value():
            self.variable.set(value)
            if callable(self._command):
                self._command(value)

    def _on_press(self, event):
        self._dragging = True
        self._apply(event.x)
        return "break"

    def _on_drag(self, event):
        if self._dragging:
            self._apply(event.x)
        return "break"

    def _render(self):
        self.delete("all")
        _, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
        x1, x2 = self._track()
        y = h / 2
        T.round_rect(self, x1, y - 2, x2, y + 2, 2, fill=T.COLORS.border, outline="")
        hx = x1 + self._ratio() * (x2 - x1)
        T.round_rect(self, x1, y - 2, hx, y + 2, 2, fill=T.COLORS.accent, outline="")
        r = 7
        self.create_oval(hx - r, y - r, hx + r, y + r,
                         fill=T.COLORS.text_primary if self._hovering or self._dragging else T.COLORS.elevated,
                         outline=T.COLORS.accent if self._hovering or self._dragging else T.COLORS.border_strong,
                         width=2)


# ==========================================================================
# ToggleSwitch
# ==========================================================================
class ToggleSwitch(T.ThemedBase):
    """On/off switch with a caption to its right."""

    def __init__(self, master, variable, text="", *, command=None, width=190,
                 height=30):
        super().__init__(master, surface=T.COLORS.chrome, width=width, height=height)
        self.configure(width=width, height=height)
        self.variable = variable
        self.text = text
        self._command = command
        self.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *_: self._safe_render())
        self._finish_init()

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        if callable(self._command):
            self._command(self.variable.get())
        return "break"

    def _render(self):
        self.delete("all")
        h = int(self.winfo_reqheight())
        on = bool(self.variable.get())
        track_w, track_h = 34, 18
        y = h / 2
        T.round_rect(self, 0, y - track_h / 2, track_w, y + track_h / 2, track_h / 2,
                     fill=T.COLORS.accent if on else T.COLORS.border_strong, outline="")
        knob_r = 7
        kx = track_w - 10 if on else 10
        self.create_oval(kx - knob_r, y - knob_r, kx + knob_r, y + knob_r,
                         fill=T.COLORS.text_primary, outline="")
        if self.text:
            self.create_text(track_w + 10, y, text=self.text, anchor="w",
                             fill=T.COLORS.text_secondary if not on else T.COLORS.text_primary,
                             font=T.FONTS.small)


# ==========================================================================
# InspectorSection
# ==========================================================================
class InspectorSection(tk.Frame):
    """Titled group with a hairline header - the right inspector's unit."""

    def __init__(self, master, title, *, subtitle=None, padx=14, pady=(12, 14)):
        super().__init__(master, bg=T.COLORS.panel)
        header = tk.Frame(self, bg=T.COLORS.panel)
        header.pack(fill="x", padx=padx, pady=(pady[0], 2))
        tk.Label(header, text=title.upper(), bg=T.COLORS.panel, fg=T.COLORS.text_muted,
                 font=(T.FONT_FAMILY, 8, "bold")).pack(side="left")
        if subtitle:
            tk.Label(header, text=subtitle, bg=T.COLORS.panel, fg=T.COLORS.text_muted,
                     font=T.FONTS.tiny).pack(side="right")
        self.body = tk.Frame(self, bg=T.COLORS.panel)
        self.body.pack(fill="x", padx=padx, pady=(4, 0))
        hair = tk.Frame(self, bg=T.COLORS.border, height=1)
        hair.pack(fill="x", pady=(pady[1], 0))


# ==========================================================================
# StatusBar
# ==========================================================================
class StatusBar(tk.Frame):
    """Bottom strip: tool hint on the left, live metrics on the right."""

    def __init__(self, master, *, height=None):
        height = height or T.METRICS.statusbar_h
        super().__init__(master, bg=T.COLORS.chrome, height=height)
        self.pack_propagate(False)
        tk.Frame(self, bg=T.COLORS.border, height=1).pack(side="top", fill="x")
        inner = tk.Frame(self, bg=T.COLORS.chrome)
        inner.pack(fill="both", expand=True, padx=12)

        self.hint = tk.Label(inner, text="", bg=T.COLORS.chrome,
                             fg=T.COLORS.text_secondary, font=T.FONTS.small, anchor="w")
        self.hint.pack(side="left")

        self.metrics = tk.Label(inner, text="", bg=T.COLORS.chrome,
                                fg=T.COLORS.text_muted, font=T.FONTS.mono, anchor="e")
        self.metrics.pack(side="right")

        self._cache = {}

    def set_hint(self, text):
        if self._cache.get("hint") != text:
            self._cache["hint"] = text
            self.hint.config(text=text)

    def set_metrics(self, *, zoom=None, size=None, cursor=None, selection=None,
                    history=None):
        parts = []
        if size:
            parts.append(f"{size[0]}×{size[1]}")
        if zoom is not None:
            parts.append(f"{int(round(zoom * 100))}%")
        if selection:
            parts.append(f"▭ {selection[0]}×{selection[1]}")
        if cursor:
            parts.append(f"⌖ {cursor[0]}, {cursor[1]}")
        if history is not None:
            parts.append(history)
        text = "   ·   ".join(parts)
        if self._cache.get("metrics") != text:
            self._cache["metrics"] = text
            self.metrics.config(text=text)
