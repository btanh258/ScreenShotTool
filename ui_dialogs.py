# -*- coding: utf-8 -*-
"""ui_dialogs.py - the settings surfaces of ScreenShotTool.

Three modal cards share one visual grammar so the application reads as a single
product:

* a header with an accent glyph tile, a bold title and a muted tagline;
* a panel-coloured card holding grouped sections introduced by uppercase muted
  labels (:class:`ui_widgets.InspectorSection`);
* kbd-style key chips for every key combination instead of raw strings;
* a footer with a primary action and a ghost dismiss button.

``open_info_dialog`` is the quick guide (read-only), ``open_hotkey_dialog`` is
the editable form with live inline validation, and ``open_shortcuts_dialog``
keeps the legacy typed-entry editor working on the same card.

Every colour, font, radius and spacing value comes from :mod:`ui_theme`; the
composite controls come from :mod:`ui_widgets`.  No hard-coded colours.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import ui_theme as T
import ui_widgets as U
from hotkey_settings import _record_key, _validate

__all__ = [
    "open_info_dialog",
    "open_shortcuts_dialog",
    "open_hotkey_dialog",
    "DEFAULT_CAPTURE_HOTKEY",
    "DEFAULT_EDITOR_HOTKEYS",
]

DEFAULT_CAPTURE_HOTKEY = "Alt+X"
DEFAULT_EDITOR_HOTKEYS = {
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Y",
    "delete": "Delete",
    "edit_text": "Double-click",
}

_MODIFIERS = {"ALT", "CTRL", "SHIFT", "WIN"}
_ALIASES = {"CONTROL": "CTRL", "CONTROL_L": "CTRL", "CONTROL_R": "CTRL"}
_ALLOWED_KEYS = {"DELETE", "ESC", "SPACE", "ENTER"}
# Tk keysym -> stored key name (mirrors ``hotkey_settings._record_key``).
_EVENT_KEY_NAMES = {"RETURN": "Enter", "ESCAPE": "Esc", "SPACE": "Space",
                    "DELETE": "Delete"}
# Tk event.state bits: Shift, Control, Alt, Win - used to tell "record this
# combination" apart from "this is the dialog's own close key".
_MODIFIER_STATE_MASK = 0x0001 | 0x0004 | 0x0008 | 0x20000 | 0x0040

# (key, caption, default, require_modifier, helper) - require_modifier is None
# for the free-text "edit_text" row, matching the legacy dialog exactly.
_FORM_FIELDS = (
    ("capture_hotkey", "Chụp màn hình", "Alt+X", True,
     "Phím hệ thống, dùng được khi đang ở ứng dụng khác."),
    ("undo", "Hoàn tác", "Ctrl+Z", True, "Quay lại thao tác trước đó."),
    ("redo", "Làm lại", "Ctrl+Y", True, "Làm lại thao tác vừa hoàn tác."),
    ("delete", "Xóa vùng chọn", "Delete", False, "Không cần phím bổ trợ."),
    ("edit_text", "Sửa văn bản", "Double-click", None,
     "Để trống sẽ dùng mặc định Double-click."),
)
_FORM_BY_KEY = {row[0]: row for row in _FORM_FIELDS}
_FORM_SECTIONS = (
    ("Chụp màn hình", ("capture_hotkey",)),
    ("Trình chỉnh sửa", ("undo", "redo", "delete", "edit_text")),
)
_CONFLICT_KEYS = ("capture_hotkey", "undo", "redo", "delete")


# ==========================================================================
# Small painters
# ==========================================================================
def _text(master, text, *, surface, color, fontspec, **pack):
    """Themed ``tk.Label`` - ttk cannot colour a label per surface."""
    label = tk.Label(master, text=text, bg=surface, fg=color, font=fontspec,
                     anchor="w", justify="left")
    if pack:
        label.pack(**pack)
    return label


def _icon_tile(master, glyph, *, surface, size=46, glyph_size=20):
    """Rounded accent-tinted square carrying a monochrome glyph."""
    canvas = tk.Canvas(master, width=size, height=size, bg=surface,
                       highlightthickness=0, borderwidth=0)
    T.round_rect(canvas, 0, 0, size - 1, size - 1, T.RADIUS.lg,
                 fill=T.COLORS.accent_soft, outline=T.COLORS.border)
    canvas.create_text(size / 2, size / 2, text=glyph, fill=T.COLORS.accent_hover,
                       font=(T.FONT_FAMILY, glyph_size, "bold"))
    return canvas


class _KeyChip(tk.Canvas):
    """One keyboard key cap: rounded, bordered, monospaced."""

    HEIGHT = 24
    PADX = 8

    def __init__(self, master, text, *, surface):
        self.text = str(text)
        self.fontspec = T.FONTS.mono_small
        width = max(24, U.measure_text(self.fontspec, self.text) + self.PADX * 2)
        super().__init__(master, width=width, height=self.HEIGHT, bg=surface,
                         highlightthickness=0, borderwidth=0)
        T.round_rect(self, 0.5, 0.5, width - 1.5, self.HEIGHT - 1.5, T.RADIUS.sm,
                     fill=T.COLORS.elevated, outline=T.COLORS.border_strong)
        self.create_line(5, self.HEIGHT - 4, width - 5, self.HEIGHT - 4,
                         fill=T.COLORS.border)
        self.create_text(width / 2, self.HEIGHT / 2 - 1, text=self.text,
                         fill=T.COLORS.text_primary, font=self.fontspec)


def _split_keys(spec):
    """``"Ctrl+Z"`` -> ``["Ctrl", "Z"]``; a tuple is used as-is."""
    if isinstance(spec, (tuple, list)):
        return [str(item).strip() for item in spec if str(item).strip()]
    parts = [part.strip() for part in str(spec or "").split("+")]
    return [part for part in parts if part]


# Config stores hotkeys upper-cased ("ALT+X") because that is the form the
# Win32 registrar compares against.  Humans read "Alt+X", which is what the rest
# of the UI shows (brand subtitle, prose), so normalise at the display edge
# rather than storing a second spelling.
_KEY_DISPLAY = {
    "ALT": "Alt", "CTRL": "Ctrl", "SHIFT": "Shift", "WIN": "Win",
    "ESC": "Esc", "ESC.": "Esc", "SPACE": "Space", "ENTER": "Enter",
    "TAB": "Tab", "DELETE": "Delete", "BACKSPACE": "Backspace",
    "DOUBLE-CLICK": "Double-click", "CLICK": "click",
}


def display_hotkey(spec):
    """Title-case a stored hotkey spec for human eyes.

    ``"ALT+X"`` -> ``"Alt+X"``, ``"CTRL+SHIFT+S"`` -> ``"Ctrl+Shift+S"``.
    Unknown tokens keep their original spelling, and non-string input is
    returned untouched so tuples/lists of chips still work.
    """
    if not isinstance(spec, str):
        return spec
    parts = [part.strip() for part in spec.split("+")]
    if not parts:
        return spec
    return "+".join(_KEY_DISPLAY.get(part.upper(), part) for part in parts)


def _chip_row(master, spec, *, surface):
    """Horizontal run of key chips joined by muted ``+`` separators."""
    row = tk.Frame(master, bg=surface)
    chips = _split_keys(display_hotkey(spec))
    if not chips:
        _text(row, "—", surface=surface, color=T.COLORS.text_muted,
              fontspec=T.FONTS.mono_small).pack(side="left")
        return row
    for index, chip in enumerate(chips):
        if index:
            _text(row, "+", surface=surface, color=T.COLORS.text_muted,
                  fontspec=T.FONTS.mono_small).pack(side="left", padx=3)
        _KeyChip(row, chip, surface=surface).pack(side="left")
    return row


# ==========================================================================
# Window plumbing
# ==========================================================================
def _config_values(config):
    """Read ``config`` defensively; returns ``(capture, editor dict)``."""
    data = config if isinstance(config, dict) else {}
    editor = dict(DEFAULT_EDITOR_HOTKEYS)
    stored = data.get("editor_hotkeys")
    if isinstance(stored, dict):
        for key, value in stored.items():
            if isinstance(value, str) and value.strip():
                editor[key] = value.strip()
    capture = data.get("capture_hotkey")
    if not isinstance(capture, str) or not capture.strip():
        capture = DEFAULT_CAPTURE_HOTKEY
    return capture.strip(), editor


def _shell(parent, title):
    """Create a hidden, themed, non-resizable Toplevel ready to be filled."""
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.configure(bg=T.COLORS.app)
    dialog.resizable(False, False)
    try:
        dialog.transient(parent.winfo_toplevel())
    except (AttributeError, tk.TclError):
        pass
    T.apply_theme(dialog)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    return dialog


def _bind_recursive(widget, sequence, handler):
    """Bind ``sequence`` on ``widget`` and on every descendant.

    Tk delivers a key event only to the *focused* widget's bind tags - it does
    not bubble up to the owning Toplevel - so a binding installed on the dialog
    alone is dead as soon as an ``Entry`` takes focus.
    """
    try:
        widget.bind(sequence, handler, add="+")
    except tk.TclError:
        return
    for child in widget.winfo_children():
        _bind_recursive(child, sequence, handler)


def _show(dialog, parent):
    """Reveal a built dialog: dark title bar, centred on parent, modal."""
    dialog.update_idletasks()
    # Pin the natural size as the minimum as well as the initial size.  The
    # card is not resizable, but a caller (a DPI change, a WM, or a test) can
    # still force a smaller geometry - and a squeezed footer is exactly the
    # case where the hint label and the buttons would collide.
    natural = (dialog.winfo_reqwidth(), dialog.winfo_reqheight())
    try:
        dialog.minsize(*natural)
    except tk.TclError:
        pass
    dialog.deiconify()
    dialog.update_idletasks()
    T.apply_dark_titlebar(dialog)
    try:
        T.center_window(dialog, parent=parent.winfo_toplevel(), width=natural[0],
                        height=natural[1])
    except (AttributeError, tk.TclError):
        T.center_window(dialog, width=natural[0], height=natural[1])
    try:
        dialog.grab_set()
    except tk.TclError:
        pass

    def _escape(_event=None):
        dialog.destroy()
        return "break"

    _bind_recursive(dialog, "<Escape>", _escape)
    dialog.focus_set()
    return dialog


def _reason(raw, require_modifier=True):
    """Human explanation for a rejected value (shown inline, in red)."""
    text = str(raw or "").strip()
    parts = [part.strip().upper() for part in text.replace("-", "+").split("+")
             if part.strip()]
    if not parts:
        return "Không được để trống."
    parts = [_ALIASES.get(part, part) for part in parts]
    if parts[-1] in _MODIFIERS:
        return "Thiếu phím chính sau phím bổ trợ."
    if len(parts) > 1 and len(set(parts[:-1])) != len(parts[:-1]):
        return "Phím bổ trợ bị lặp lại."
    if require_modifier and not _MODIFIERS.intersection(parts[:-1]):
        return "Cần phím bổ trợ: Ctrl, Alt, Shift hoặc Win."
    key = parts[-1]
    if len(key) != 1 and not key.startswith("F") and key not in _ALLOWED_KEYS:
        return "Phím chính không hợp lệ (A–Z, 0–9, F1–F12, Enter, Esc, Space, Delete)."
    return "Tổ hợp phím không hợp lệ."


# ==========================================================================
# Info dialog - quick guide
# ==========================================================================
def _shortcut_groups(config):
    """Grouped shortcut rows for the quick guide, driven by ``config``."""
    capture, editor = _config_values(config)
    return (
        ("capture", "Chụp màn hình", (
            ("Chụp vùng màn hình", capture, "Dùng được từ bất kỳ ứng dụng nào."),
        )),
        ("editor", "Chỉnh sửa", (
            ("Hoàn tác", editor.get("undo", "Ctrl+Z"), "Quay lại thao tác trước."),
            ("Làm lại", editor.get("redo", "Ctrl+Y"), "Làm lại thao tác vừa hoàn tác."),
            ("Xóa vùng chọn", editor.get("delete", "Delete"), "Xóa đối tượng đang chọn."),
            ("Sửa văn bản", editor.get("edit_text", "Double-click"), "Mở lại chú thích văn bản."),
        )),
        ("editor", "Xuất ảnh", (
            ("Sao chép", "Ctrl+C", "Đưa ảnh vào clipboard."),
            ("Lưu ra tệp", "Ctrl+S", "Chọn nơi lưu và định dạng."),
        )),
        ("editor", "Chọn nhiều", (
            ("Chọn tất cả", "Ctrl+A", "Chọn toàn bộ chú thích."),
            ("Chọn thêm", ("Ctrl", "click"), "Giữ Ctrl và bấm vào đối tượng."),
            ("Bỏ chọn", "Esc", "Bỏ toàn bộ vùng chọn."),
        )),
        ("editor", "Cắt", (
            ("Khoanh vùng", "Kéo chuột", "Kéo một vùng trên ảnh."),
            ("Xác nhận", "Enter", "Cắt theo vùng đã khoanh."),
            ("Hủy", "Esc", "Hủy thao tác cắt."),
        )),
    )


def open_info_dialog(parent, config, *, on_open_hotkeys=None, app_version=None):
    """Quick guide plus a shortcut-settings entry point."""
    dialog = _shell(parent, "Giới thiệu ScreenShotTool")
    app = T.COLORS.app
    panel = T.COLORS.panel

    outer = tk.Frame(dialog, bg=app)
    outer.pack(fill="both", expand=True, padx=T.SPACE.lg, pady=T.SPACE.lg)

    heading = tk.Frame(outer, bg=app)
    heading.pack(fill="x")
    _icon_tile(heading, T.GLYPH.crop, surface=app,
               size=42, glyph_size=18).pack(side="left", padx=(0, T.SPACE.md))
    titles = tk.Frame(heading, bg=app)
    titles.pack(side="left", fill="x", expand=True)
    # The version comes from the caller so this module stays free of an import
    # cycle back into the application module.
    title_text = "ScreenShotTool" if not app_version else "ScreenShotTool %s" % app_version
    ttk.Label(titles, text=title_text, style=T.STYLE_TITLE_LABEL).pack(anchor="w")
    ttk.Label(titles, text="Chụp, chú thích và xuất ảnh trong vài giây.",
              style=T.STYLE_SUBTITLE_LABEL).pack(anchor="w", pady=(2, 0))

    filter_var = tk.StringVar(value="all")
    U.SegmentedControl(
        heading,
        [("all", "Tất cả"), ("capture", "Chụp"), ("editor", "Chỉnh sửa")],
        filter_var, height=T.METRICS.control_h_sm + 2, surface=app,
    ).pack(side="right")

    U.Divider(outer).pack(fill="x", pady=(T.SPACE.md, 0))

    card_border = tk.Frame(outer, bg=T.COLORS.border)
    card_border.pack(fill="both", expand=True, pady=(0, T.SPACE.sm))
    card = tk.Frame(card_border, bg=panel)
    card.pack(fill="both", expand=True, padx=1, pady=1)

    # Two balanced columns keep the guide under ~700 px tall on 1080p.  A Tk
    # widget can only be managed by its real parent, so the column is fixed
    # when the section is built rather than when it is shown.
    columns = (tk.Frame(card, bg=panel), tk.Frame(card, bg=panel))
    for column in columns:
        column.pack(side="left", fill="both", expand=True,
                    anchor="n", padx=(0, T.SPACE.sm))

    definition = _shortcut_groups(config)
    weights = [len(rows) + 1 for _kind, _title, rows in definition]
    column_of = []
    totals = [0, 0]
    for weight in weights:
        index = 0 if totals[0] <= totals[1] else 1
        totals[index] += weight
        column_of.append(index)

    groups = []
    for (kind, title, rows), index in zip(definition, column_of):
        section = U.InspectorSection(columns[index], title, pady=(8, 6))
        body = section.body
        body.grid_columnconfigure(0, weight=1)
        for row, (label, keys, description) in enumerate(rows):
            # label + muted description stacked left, kbd chips right - the
            # classic settings-row shape, and half the width of three columns.
            text_cell = tk.Frame(body, bg=panel)
            text_cell.grid(row=row, column=0, sticky="w", pady=(0, 5))
            _text(text_cell, label, surface=panel, color=T.COLORS.text_primary,
                  fontspec=T.FONTS.body_strong).pack(anchor="w")
            _text(text_cell, description, surface=panel,
                  color=T.COLORS.text_muted,
                  fontspec=T.FONTS.tiny).pack(anchor="w", pady=(1, 0))
            _chip_row(body, keys, surface=panel).grid(
                row=row, column=1, sticky="e", padx=(T.SPACE.md, 0), pady=(0, 5))
        groups.append((kind, section, index))

    def _apply_filter(*_event):
        """Show the sections matching the segmented filter."""
        mode = filter_var.get()
        for kind, section, _index in groups:
            section.pack_forget()
        for kind, section, index in groups:
            if mode == "all" or kind == mode:
                section.pack(in_=columns[index], fill="x")

    filter_var.trace_add("write", _apply_filter)
    _apply_filter()

    footer = tk.Frame(outer, bg=app)
    footer.pack(fill="x", pady=(T.SPACE.sm, 0))

    # Buttons are packed before the hint so the hint can only take the slack
    # (``expand=True``); packing the hint first would let it claim its full
    # width and the buttons would overdraw it.
    close_button = U.PillButton(footer, "Đóng", dialog.destroy, variant="ghost",
                                glyph=T.GLYPH.close, surface=app)
    close_button.pack(side="right")
    hotkey_button = U.PillButton(footer, "Gán phím tắt", variant="primary",
                                 glyph=T.GLYPH.keyboard, surface=app)
    hotkey_button.pack(side="right", padx=(0, T.SPACE.sm))
    hint_label = _text(footer, "Enter mở phím tắt · Esc đóng", surface=app,
                       color=T.COLORS.text_muted, fontspec=T.FONTS.tiny)
    hint_label.pack(side="left", fill="x", expand=True,
                    padx=(0, T.SPACE.md), pady=(T.SPACE.sm, 0))
    dialog._footer_hint = hint_label
    dialog._footer_buttons = (hotkey_button, close_button)

    callback = on_open_hotkeys if callable(on_open_hotkeys) else None
    if callback is None:
        # No host callback: still usable, but edits only the in-memory config.
        def callback():
            open_hotkey_dialog(parent, config, None)

    def _launch(_event=None):
        callback()
        _restore_grab(60)
        return "break"

    hotkey_button.configure(command=_launch)
    dialog.bind("<Return>", _launch)

    def _restore_grab(remaining):
        """Re-arm modality once a child dialog opened by the callback closes."""
        if remaining <= 0:
            return
        try:
            if not dialog.winfo_exists():
                return
            current = dialog.grab_current()
            if current is None or current is dialog:
                dialog.grab_set()
                return
        except tk.TclError:
            return
        dialog.after(120, lambda: _restore_grab(remaining - 1))

    _show(dialog, parent)
    hotkey_button.focus_set()
    return dialog


# ==========================================================================
# Hotkey form - shared by both editable dialogs
# ==========================================================================
class _Field:
    """One caption + styled entry + inline validation line."""

    def __init__(self, master, key, caption, value, helper, require_modifier,
                 command=None):
        self.key = key
        self.caption = caption
        self.require_modifier = require_modifier
        self.normalized = None
        self._command = command
        self._hint_job = None
        self.var = tk.StringVar(master=master, value=value)

        row = tk.Frame(master, bg=T.COLORS.panel)
        row.pack(fill="x", pady=(T.SPACE.sm, T.SPACE.sm))
        row.grid_columnconfigure(0, minsize=118)
        _text(row, caption, surface=T.COLORS.panel,
              color=T.COLORS.text_secondary,
              fontspec=T.FONTS.small_strong).grid(row=0, column=0, sticky="nw",
                                                  pady=(7, 0))
        column = tk.Frame(row, bg=T.COLORS.panel)
        column.grid(row=0, column=1, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        self.entry = ttk.Entry(column, textvariable=self.var, width=26,
                               style=T.STYLE_ENTRY, font=T.FONTS.mono)
        self.entry.pack(anchor="w")
        self.status = _text(column, helper, surface=T.COLORS.panel,
                            color=T.COLORS.text_muted, fontspec=T.FONTS.tiny)
        self.status.pack(anchor="w", pady=(3, 0))
        self.var.trace_add("write", lambda *_: self._notify())

    def _notify(self):
        if callable(self._command):
            self._command()

    def bind_key_capture(self):
        """Record real key presses into the field (hotkey-capture mode).

        ``<KeyPress>`` is the only generic sequence bound here: Tk runs the most
        specific binding per bind tag, so ``Return`` still reaches the dialog's
        save handler.  ``Escape`` is bound explicitly because it is the dialog's
        close key - a bare Escape must close, while Ctrl/Alt/Shift+Escape is a
        legitimate hotkey and is recorded instead.
        """
        self.entry.bind("<KeyPress>", self._capture_key)
        self.entry.bind("<Escape>", self._escape_or_record)
        self.entry.bind("<FocusIn>",
                        lambda _event: self.entry.selection_range(0, "end"))

    def _capture_key(self, event):
        """Record a key combination; explain a bare key instead of faking one.

        ``_record_key`` writes the placeholder "Chọn Ctrl/Alt/Shift + phím" when
        no modifier is held.  In this dialog that placeholder would be an
        invalid form value, so the guidance goes to the status line and the
        current value is preserved.  ``_record_key`` itself is untouched.

        The one exception is a field that legitimately takes a bare key
        (``Delete`` needs no modifier): there the key name is written directly.
        """
        modifiers = getattr(event, "state", 0) & _MODIFIER_STATE_MASK
        keysym = str(getattr(event, "keysym", "")).upper()
        if modifiers:
            return _record_key(event, self.entry)
        if keysym in _EVENT_KEY_NAMES:
            name = _EVENT_KEY_NAMES[keysym]
            if self.require_modifier is False:
                self.set_text(name)
                return "break"
        if keysym.startswith("F") and self.require_modifier is False:
            self.set_text(keysym)
            return "break"
        if self.require_modifier is None:       # free-text row (edit_text)
            return None
        self._flash_hint("Giữ Ctrl, Alt hoặc Shift khi bấm phím.")
        return "break"

    def _flash_hint(self, text, delay=1800):
        """Show guidance briefly, then fall back to the validation state."""
        self.set_status("info", text)
        if self._hint_job is not None:
            try:
                self.entry.after_cancel(self._hint_job)
            except (tk.TclError, ValueError):
                pass
        restore = None
        if callable(self._command):
            restore = self._command
        try:
            self._hint_job = self.entry.after(
                delay, lambda: (setattr(self, "_hint_job", None),
                                restore() if callable(restore) else None))
        except tk.TclError:
            self._hint_job = None

    def _escape_or_record(self, event):
        if getattr(event, "state", 0) & _MODIFIER_STATE_MASK:
            return _record_key(event, self.entry)
        return None                      # fall through to the dialog's Escape

    def set_status(self, kind, text):
        color = {
            "ok": T.COLORS.success,
            "error": T.COLORS.danger,
            "hint": T.COLORS.text_muted,
            "info": T.COLORS.text_secondary,
        }[kind]
        self.status.configure(text=text, fg=color)

    def text(self):
        return self.var.get()

    def set_text(self, value):
        self.var.set(value)


def _build_form(dialog, parent, config, save_callback, *, record_keys):
    """Fill ``dialog`` with the editable hotkey card."""
    capture, editor = _config_values(config)
    initial = {
        "capture_hotkey": capture,
        "undo": editor.get("undo", DEFAULT_EDITOR_HOTKEYS["undo"]),
        "redo": editor.get("redo", DEFAULT_EDITOR_HOTKEYS["redo"]),
        "delete": editor.get("delete", DEFAULT_EDITOR_HOTKEYS["delete"]),
        "edit_text": editor.get("edit_text", DEFAULT_EDITOR_HOTKEYS["edit_text"]),
    }

    state = {"valid": False, "saved": False, "values": {}}
    fields = {}
    widgets = {"save": None}

    def _refresh(*_event):
        resolved = {}
        for key, _caption, _default, require_modifier, _helper in _FORM_FIELDS:
            field = fields[key]
            raw = field.text()
            if require_modifier is None:          # free text (edit_text)
                value = raw.strip() or DEFAULT_EDITOR_HOTKEYS["edit_text"]
                resolved[key] = value
                field.normalized = value
                field.set_status("ok", "%s  %s" % (T.GLYPH.check, value))
                continue
            normalized = _validate(raw, require_modifier=require_modifier)
            field.normalized = normalized
            if normalized:
                resolved[key] = normalized
                field.set_status("ok", "%s  %s" % (T.GLYPH.check,
                                                   display_hotkey(normalized)))
            else:
                resolved[key] = None
                field.set_status("error",
                                 "%s  %s" % (T.GLYPH.close,
                                             _reason(raw, require_modifier)))

        owner = {}
        duplicates = set()
        for key in _CONFLICT_KEYS:
            value = resolved.get(key)
            if not value:
                continue
            if value in owner:
                duplicates.update((owner[value], key))
            else:
                owner[value] = key
        for key in duplicates:
            value = resolved.get(key)
            clash = next((fields[other].caption for other in _CONFLICT_KEYS
                          if other != key and resolved.get(other) == value), "")
            fields[key].set_status("error", "%s  Trùng phím với «%s»."
                                   % (T.GLYPH.close, clash))

        valid = (not duplicates
                 and all(resolved.get(key) for key in _CONFLICT_KEYS)
                 and bool(resolved.get("edit_text")))
        state["valid"] = valid
        state["values"] = resolved
        if widgets["save"] is not None:
            widgets["save"].set_enabled(valid)
        return valid

    app = T.COLORS.app
    panel = T.COLORS.panel

    outer = tk.Frame(dialog, bg=app)
    outer.pack(fill="both", expand=True, padx=T.SPACE.xl, pady=T.SPACE.xl)

    heading = tk.Frame(outer, bg=app)
    heading.pack(fill="x")
    _icon_tile(heading, T.GLYPH.keyboard, surface=app).pack(side="left",
                                                           padx=(0, T.SPACE.md))
    titles = tk.Frame(heading, bg=app)
    titles.pack(side="left", fill="x", expand=True)
    ttk.Label(titles, text="Phím tắt", style=T.STYLE_TITLE_LABEL).pack(anchor="w")
    tagline = ("Bấm tổ hợp phím để ghi nhanh vào ô." if record_keys
               else "Nhập tổ hợp phím, ví dụ Ctrl+Shift+S.")
    ttk.Label(titles, text=tagline, style=T.STYLE_SUBTITLE_LABEL).pack(anchor="w", pady=(2, 0))

    U.Divider(outer).pack(fill="x", pady=(T.SPACE.lg, 0))

    card_border = tk.Frame(outer, bg=T.COLORS.border)
    card_border.pack(fill="both", expand=True, pady=(0, T.SPACE.md))
    card = tk.Frame(card_border, bg=panel)
    card.pack(fill="both", expand=True, padx=1, pady=1)

    for title, keys in _FORM_SECTIONS:
        section = U.InspectorSection(card, title, pady=(10, 8))
        section.pack(fill="x")
        for key in keys:
            caption, default, require_modifier, helper = _FORM_BY_KEY[key][1:]
            field = _Field(section.body, key, caption,
                           display_hotkey(initial[key]), helper,
                           require_modifier, command=_refresh)
            if record_keys:
                field.bind_key_capture()
            fields[key] = field

    footer = tk.Frame(outer, bg=app)
    footer.pack(fill="x", pady=(T.SPACE.md, 0))

    def _reset():
        for key, _caption, default, _require, _helper in _FORM_FIELDS:
            fields[key].set_text(default)
        _refresh()

    def _cancel(_event=None):
        dialog.destroy()
        return "break"

    def _save(_event=None):
        if state["saved"]:
            return "break"
        if not _refresh():
            return "break"
        resolved = state["values"]
        target = config if isinstance(config, dict) else {}
        target["capture_hotkey"] = resolved["capture_hotkey"]
        editor_section = target.get("editor_hotkeys")
        if not isinstance(editor_section, dict):
            editor_section = {}
            target["editor_hotkeys"] = editor_section
        for key in ("undo", "redo", "delete", "edit_text"):
            editor_section[key] = resolved[key]
        state["saved"] = True
        if callable(save_callback):
            save_callback(target)
        dialog.destroy()
        return "break"

    # Packing order is the layout guarantee: the action buttons claim their
    # parcels first (right, then the reset on the left), and the hint is packed
    # LAST with ``fill="x", expand=True`` so it can only ever take what is
    # left over.  A hint packed before the buttons would be allocated its full
    # requested width and the later buttons would overdraw it.
    save_button = U.PillButton(footer, "Lưu", _save, variant="primary",
                               glyph=T.GLYPH.save, surface=app)
    save_button.pack(side="right")
    widgets["save"] = save_button
    cancel_button = U.PillButton(footer, "Hủy", _cancel, variant="ghost",
                                 glyph=T.GLYPH.close, surface=app)
    cancel_button.pack(side="right", padx=(0, T.SPACE.sm))
    reset_button = U.PillButton(footer, "Khôi phục mặc định", _reset,
                                variant="secondary", glyph=T.GLYPH.rotate_ccw,
                                surface=app)
    reset_button.pack(side="left")
    hint_label = _text(footer, "Enter lưu · Esc hủy", surface=app,
                       color=T.COLORS.text_muted, fontspec=T.FONTS.tiny)
    hint_label.pack(side="left", fill="x", expand=True,
                    padx=(T.SPACE.md, T.SPACE.sm), pady=(T.SPACE.sm, 0))
    widgets["hint"] = hint_label
    widgets["reset"] = reset_button
    widgets["cancel"] = cancel_button

    dialog.bind("<Return>", _save)
    dialog.bind("<KP_Enter>", _save)
    for field in fields.values():
        field.entry.bind("<Return>", _save)

    _refresh()
    _show(dialog, parent)
    # Exposed for tests and for hosts that want to pre-seed a field.
    dialog._hotkey_fields = fields
    dialog._hotkey_state = state
    dialog._hotkey_save = _save
    dialog._hotkey_reset = _reset
    dialog._hotkey_cancel = _cancel
    dialog._hotkey_hint = hint_label
    first = fields["capture_hotkey"].entry
    first.focus_set()
    first.selection_range(0, "end")
    return dialog


def open_hotkey_dialog(parent, config, save_callback):
    """Editable hotkey card with key capture.  Returns the ``tk.Toplevel``."""
    dialog = _shell(parent, "Phím tắt")
    return _build_form(dialog, parent, config, save_callback, record_keys=True)


def open_shortcuts_dialog(parent, config, *, save_callback=None):
    """Legacy shortcut editor: same card, typed input instead of key capture."""
    dialog = _shell(parent, "Phím tắt")
    return _build_form(dialog, parent, config, save_callback, record_keys=False)
