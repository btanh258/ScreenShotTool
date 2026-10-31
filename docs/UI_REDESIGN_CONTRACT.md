# UI Redesign Contract (frozen interfaces)

Every module in this redesign talks to its neighbours through the names below.
**Do not rename or repurpose them.** If a change is genuinely required, message
the Lead first — other agents are writing against these signatures concurrently.

Repo root: `C:\Users\anh25\Downloads\Projects\TestUI\ScreenShotTool`

---

## 1. File ownership (one writer per file)

| File | Owner | State |
|---|---|---|
| `ui_theme.py` | **Lead** | DONE - design tokens + ttk style engine, frozen |
| `ui_widgets.py` | **Lead** | DONE - custom widget library, frozen |
| `ui_capture.py` | capture-eng | to create (overlay view + toast) |
| `ui_dialogs.py` | dialogs-eng | to create (Info + hotkey dialogs) |
| `hotkey_settings.py` | dialogs-eng | to restyle (KEEP public API) |
| `ScreenShotTool.pyw` | editor-eng | to refactor (editor shell + wiring) |
| `tests/**` | verifier | to extend |
| `*.md` | Lead | final write-up |

Never edit a file you do not own. `ScreenShotTool.pyw` has exactly one writer.

---

## 2. `ui_theme.py` (Lead, frozen)

```python
COLORS        # attribute dict: .app .chrome .panel .elevated .hover .canvas_bg
              #   .border .border_strong .focus_ring
              #   .text_primary .text_secondary .text_muted .text_on_accent
              #   .accent .accent_hover .accent_pressed .accent_soft
              #   .success .danger .warning .info .scrim .hint_bg .selection
SPACE         # .xs=4 .sm=8 .md=12 .lg=16 .xl=24 .xxl=32
RADIUS        # .sm=6 .md=10 .lg=14 .xl=20 .pill
METRICS       # .toolbar_h=58 .statusbar_h=30 .rail_w=72 .sidebar_w=248
              #   .control_h=34 .control_h_sm=26 .icon_size=18 .toast_w=400
FONTS         # .display .title .heading .subheading .body .body_strong
              #   .small .small_strong .tiny .mono .mono_small
GLYPH         # .select .crop .erase .pen .highlight .rect .oval .arrow .text
              #   .blur .undo .redo .copy .save .info .zoom_in .zoom_out .fit
              #   .flip_h .flip_v .rotate_ccw .rotate_cw .close .check
              #   .warning .settings .random .keyboard .magnifier .target

FONT_FAMILY = "Segoe UI"      MONO_FAMILY = "Consolas"

def font(size=10, weight="normal", slant="roman", family=None) -> tuple
def mono_font(size=9, weight="normal") -> tuple
def mix(a, b, amount) -> str          # 0->a, 1->b
def lighten(color, amount=0.12) -> str
def darken(color, amount=0.12) -> str
def readable_on(color) -> str         # high-contrast text for a background
def round_rect(canvas, x1, y1, x2, y2, radius, **kw) -> int   # smoothed polygon
def center_window(window, width=None, height=None, parent=None)
def apply_dark_titlebar(window)       # DWM dark title bar, safe no-op
def apply_theme(root) -> ttk.Style    # idempotent; call per Toplevel

class ThemedBase(tk.Canvas)           # base for painted widgets
    configure(config=..., **kw)  /  config(...)   # accepts text/state/bg/cursor/
                                                  # command; ignores ttk-only keys
    cget("text"|"state"|"bg") -> value
    invoke();  set_text(s);  get_text();  set_enabled(bool)
    _finish_init()   # call at the END of a subclass __init__ to paint it
    _safe_render()   # repaint; no-op during construction - use in traces

Style names: STYLE_APP_FRAME, STYLE_CHROME_FRAME, STYLE_PANEL_FRAME,
STYLE_CARD_FRAME, STYLE_TITLE_LABEL, STYLE_SUBTITLE_LABEL, STYLE_BODY_LABEL,
STYLE_MUTED_LABEL, STYLE_CHROME_LABEL, STYLE_PRIMARY_BUTTON,
STYLE_SECONDARY_BUTTON, STYLE_GHOST_BUTTON, STYLE_DANGER_BUTTON,
STYLE_SUCCESS_BUTTON, STYLE_ACTION_BUTTON, STYLE_COMBOBOX, STYLE_ENTRY,
STYLE_CHECKBUTTON, STYLE_VSCROLL, STYLE_HSCROLL, STYLE_SEPARATOR
```

`apply_theme()` already configures the legacy `Toolbutton` ttk style, so any
widget not yet migrated still looks intentional.

---

## 3. `ui_widgets.py` (Lead, frozen)

```python
Tooltip(widget, text, *, delay=420, placement="right"|"below")

Divider(master, orient="horizontal"|"vertical", *, color=None)

RailButton(master, glyph, caption, value, variable, *, command=None,
           width=60, height=52, tooltip=None)
    # vertical icon+caption tool button; writes `value` into `variable`

IconButton(master, glyph, command=None, *, size=34, glyph_size=14,
           variant="ghost"|"primary"|"danger"|"success", tooltip=None, surface=None)
    set_glyph(g)

PillButton(master, text="", command=None, *, variant="primary"|"secondary"
           |"ghost"|"danger"|"success", glyph=None, fontspec=None, padx=16,
           height=None, tooltip=None, surface=None, min_width=0)
    set_text(t)

SegmentedControl(master, options, variable=None, command=None, *,
                 height=None, surface=None, fontspec=None, padding=12)
    # options = [(value, caption), ...]

ColorSwatch(master, color="#ff0000", *, command=None, random_command=None,
            palette=None, size=30, tooltip=None)
    set_color(c);  get_color();  config(bg=c) also sets the colour

NumberStepper(master, variable, *, minimum=1, maximum=50, step=1, width=118,
              height=None, command=None, tooltip=None)

Slider(master, variable, *, minimum=1, maximum=50, step=1, width=200,
       height=28, command=None)

ToggleSwitch(master, variable, text="", *, command=None, width=190, height=30)

InspectorSection(master, title, *, subtitle=None, padx=14, pady=(12, 14))
    .body  -> Frame to pack controls into

StatusBar(master, *, height=None)
    .set_hint(text)
    .set_metrics(zoom=None, size=None, cursor=None, selection=None, history=None)

measure_text(fontspec, text) -> int
```

All painted widgets accept the classic Tk dialect (`config`, `cget`, `invoke`)
so existing application code keeps working after migration.

---

## 4. `ui_capture.py` (capture-eng) - FROZEN SIGNATURES

Owns the full-screen snipping overlay **and** the result toast. `SnippingTool`
moves out of `ScreenShotTool.pyw` into this module.

```python
class SnippingTool:
    def __init__(self, root, *, resource_path=None, send_to_clipboard=None,
                 open_editor=None, keyboard_module=None):
        """Dependency injection keeps this module importable without the
        app's globals.  Defaults preserve old behaviour:
        resource_path      -> caller's resource_path
        send_to_clipboard  -> caller's PNG/DIB clipboard writer
        open_editor(img)   -> called by the toast to open ImageEditor
        keyboard_module    -> `keyboard` or None (global Esc hook)
        `mss`, `cv2`, `numpy` are imported lazily inside ui_capture; if an
        optional dep is missing the tool must degrade exactly as before."""

    is_active: bool                 # guard against re-entrant capture
    monitor_origin: tuple
    full_img: PIL.Image

    def start_snipping(self) -> None      # entry point used by hotkey + tray
    def cancel_snip(self, event=None) -> None

class ResultToast:
    """Modern capture-result card, bottom-right of the work area."""
    def __init__(self, root, image, *, copied=True, on_open_editor=None,
                 resource_path=None, duration=6000)
    def show(self)
    def destroy(self)
```

Behaviour that MUST be preserved (port it, do not rewrite it):
mss full-desktop grab, DWM extended-frame window rects, OpenCV contour rects,
click-to-snap the hovered rect, drag-to-select, magnifier, Esc (both key and
global hook), `is_active` re-entrancy lock, min 10x10 rejection, clipboard
publish + toast, toast click opens the editor, 6 s auto-dismiss.

---

## 5. `ui_dialogs.py` (dialogs-eng) - FROZEN SIGNATURES

```python
def open_info_dialog(parent, config, *, on_open_hotkeys=None) -> tk.Toplevel
def open_shortcuts_dialog(parent, config, *, save_callback=None) -> tk.Toplevel
def open_hotkey_dialog(parent, config, save_callback) -> tk.Toplevel
```

`hotkey_settings.py` MUST keep its existing public API, because
`tests/test_transform.py` imports it directly:

```python
_validate(value, require_modifier=True) -> str | None
_record_key(event, entry) -> "break"
open_hotkey_settings(parent, config, save_callback) -> tk.Toplevel
```

`open_hotkey_settings` should become a thin wrapper over
`ui_dialogs.open_hotkey_dialog` so the app gets the new design while the old
entry point and its tests keep passing.

---

## 6. `ScreenShotTool.pyw` (editor-eng)

Keep module-level: `validate_hotkey`, `parse_hotkey`, `get_exe_path`,
`check_startup`, `toggle_startup`, `load_config`, `save_config`,
`send_to_clipboard`, `resource_path`, `create_tray_icon`, `main`,
`HOTKEY_MODIFIERS`, `CONFIG_FILE`, `LEGACY_CONFIG_FILE`, `APP_NAME`, `RESAMPLE`.
Keep `class ImageEditor`.

`ImageEditor` attributes/methods that other code and tests depend on - all must
survive with identical semantics:

```
pil_image  orig_w  orig_h  shapes  selected_tag  selected_tags  text_entry
history  history_index  scale  offset_x  offset_y  crop_pending
cfg  capture_hotkey_var  tool_var  color_var  width_var  text_bg_var  palette
canvas  canvas_frame  v_scroll  h_scroll  top
btn_undo  btn_redo  btn_copy  color_btn  width_cb

_build_toolbar  update_history_ui  save_state  undo  redo  _load_state
on_mouse_wheel  pick_color  apply_color_to_selected  random_color  set_zoom
redraw_all  get_new_tag  clear_selection  draw_selection_box  select_all
delete_selected  on_press  on_drag  erase_pixels  on_release
cancel_crop_or_text  confirm_crop  begin_text_edit  cancel_text_edit
on_double_click  _text_colors  commit_text  render_final_image
transform_selection_or_document  transform_selected_shape  transform_document
save_clipboard  save_file  update_custom_cursor  on_mouse_move_editor
move_selected_by  _rebuild_text_bitmap  clone_shapes
```

`_build_toolbar` must keep creating `btn_undo`, `btn_redo`, `btn_copy`,
`color_btn`, `width_cb` and keep delegating to `undo`/`redo`/`save_file`/
`save_clipboard`/`pick_color`. `update_history_ui` must keep working against
them (it calls `.config(state=...)` / `.config(cursor=...)`).
`save_clipboard` calls `self.btn_copy.cget("text")` then `.config(text=...)`.

Legacy ttk tools may be replaced by `RailButton`s driven by `self.tool_var`.

---

## 7. Definition of done (all agents)

* `python -m unittest discover -s tests -v` passes (12 original tests + new).
* `python -c "import ScreenShotTool"`-equivalent import of the `.pyw` succeeds.
* No file you do not own is modified.
* Every widget you touch has a visible hover / active / disabled state.
* No hard-coded colours outside `ui_theme.py`.
