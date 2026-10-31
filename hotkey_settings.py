# -*- coding: utf-8 -*-
"""hotkey_settings.py - hotkey validation and the legacy settings entry point.

The parsing rules in this module are shared by the whole application: the
capture listener, the editor key bindings, the hotkey dialog and
``tests/test_transform.py`` all depend on :func:`_validate` and
:func:`_record_key` behaving exactly as before, so those two functions are kept
verbatim.

The UI itself now lives in :mod:`ui_dialogs` (one modern card for every
settings surface); ``open_hotkey_settings`` stays as a thin wrapper so existing
call sites keep working.
"""

from __future__ import annotations

import tkinter as tk


def _validate(value, require_modifier=True):
    if not isinstance(value, str):
        return None
    aliases = {'CONTROL': 'CTRL', 'CONTROL_L': 'CTRL', 'CONTROL_R': 'CTRL', 'ESCAPE': 'ESC', 'RETURN': 'ENTER'}
    parts = [p.strip().upper() for p in value.replace('-', '+').split('+') if p.strip()]
    parts = [aliases.get(part, part) for part in parts]
    modifiers = {'ALT', 'CTRL', 'SHIFT', 'WIN'}
    if not parts or parts[-1] in modifiers:
        return None
    if require_modifier and (len(parts) < 2 or not modifiers.intersection(parts[:-1])):
        return None
    if len(parts) > 1 and len(parts[:-1]) != len(set(parts[:-1])):
        return None
    if len(parts[-1]) != 1 and not parts[-1].startswith('F') and parts[-1] not in {'DELETE', 'ESC', 'SPACE', 'ENTER'}:
        return None
    return '+'.join(parts)


def _record_key(event, entry):
    key = event.keysym.upper()
    if key in {'SHIFT_L', 'SHIFT_R', 'CONTROL_L', 'CONTROL_R', 'ALT_L', 'ALT_R', 'WIN_L', 'WIN_R'}:
        return 'break'
    modifiers = []
    if event.state & 0x0004:
        modifiers.append('Ctrl')
    if event.state & 0x0001:
        modifiers.append('Shift')
    if event.state & (0x0008 | 0x20000):
        modifiers.append('Alt')
    if event.state & 0x0040:
        modifiers.append('Win')
    if not modifiers:
        entry.delete(0, 'end')
        entry.insert(0, 'Chọn Ctrl/Alt/Shift + phím')
        return 'break'
    key_map = {'RETURN': 'Enter', 'ESCAPE': 'Esc', 'SPACE': 'Space', 'DELETE': 'Delete'}
    key = key_map.get(key, key)
    entry.delete(0, 'end')
    entry.insert(0, '+'.join(modifiers + [key]))
    return 'break'


def open_hotkey_settings(parent, config, save_callback) -> tk.Toplevel:
    """Legacy entry point - delegates to the redesigned dialog."""
    import ui_dialogs                       # lazy: ui_dialogs imports this module
    return ui_dialogs.open_hotkey_dialog(parent, config, save_callback)
