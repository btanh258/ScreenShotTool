# Redesign Verification Report

Independent quality gate for the ScreenShotTool UI redesign.
Owner: **verifier**. I do not design and I do not fix product code — I test it and
report defects with evidence.

Repo: `C:\Users\anh25\Downloads\Projects\TestUI\ScreenShotTool`
Baseline commit: `c3c340c` ("Update README.md")
Python: `C:\Users\anh25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` (3.12.14, Tk 8.6)
Contract: `UI_REDESIGN_CONTRACT.md` (frozen interfaces)
Screenshots: `_screens/after/` (56 PNG, 3 window sizes)

---

## VERDICT: **SHIPPABLE**

All three findings from my Phase B report are fixed in the working tree, and I
re-verified each one independently rather than taking the fix on trust. The one
release blocker is gone, and the fix is better than the one I proposed: instead
of lowering the breakpoint to hide the problem, the inspector now **floats as a
drawer** below 1180 px, so the panel is always reachable *and* the canvas keeps
its full width at large sizes.

| | Phase B | Phase C |
|---|---|---|
| **B1** Inspector unreachable below 1180 px, gear a dead button | **BLOCKER** | **FIXED** |
| **B2** `ALT+X` shown where the rest of the UI shows `Alt+X` | minor | **FIXED** |
| **B3** "Làm mờ" lost its label in compact rail mode | minor | **FIXED** |

One **non-blocking** UX note (N1) was raised at sign-off; both of its suggested
improvements (shadow strip + visible close glyph on the floating drawer) were
then implemented and re-verified — see the N1 section for the post-sign-off
update. No open findings remain.

---

## 0. Status summary

| Phase | State | Result |
|---|---|---|
| A — baseline + design-system parity + integration smoke | **DONE** | 86 + 54 tests, 0 failures |
| B — visual QA + real-entry-point wiring + reachability | **DONE** | 165 tests, 3 failures (B1) |
| C — re-verify fixes + sign off | **DONE** | **169 tests, 0 failures, 0 errors** |

### Full suite (final, Phase C)

```console
$ $env:PYTHONIOENCODING='utf-8'
$ python -m unittest discover -s tests
Ran 169 tests in 22.762s
OK
```

169 = the 165 from Phase B plus 4 new drawer tests I added in Phase C
(dismissability, reopening, header/status-bar clearance, controls-still-usable).
The three original B1 assertions pass **unmodified**; I only rewrote their
docstrings, which still said "FAILS TODAY" and had become misleading.

The Phase B suite, for the record, was:

```console
Ran 165 tests in 21.257s
FAILED (failures=3)      # the 3 B1 assertions, nothing else
```

| File | Tests | Result |
|---|---|---|
| `tests/test_transform.py` (pre-existing, untouched) | 12 | OK |
| `tests/test_ui_parity.py` (design system) | 86 | OK |
| `tests/test_ui_smoke.py` (real app + wiring + reachability) | 71 | OK |

---

## 1. B1 — inspector reachability (was a BLOCKER, now FIXED)

### What was wrong in Phase B

`_apply_layout()` did `show_inspector = self._inspector_visible and width >= 1180`
and then `pack_forget()` otherwise. The app's own `minsize` is `(760, 520)`, so
across **760–1179 px** the whole inspector was force-hidden; the gear flipped
`_inspector_visible`, `_apply_layout` re-hid the panel immediately, so the button
did nothing visible *and* desynchronised its own flag.

I proved it was a regression, not a design choice, by running `c3c340c` beside
the redesigned build on real `winfo_ismapped()` calls:

| width | ORIGINAL `c3c340c` | REDESIGNED (Phase B) |
|---|---|---|
| 1600 | all 4 mapped | all 4 mapped |
| 1200 | all 4 mapped | all 4 mapped |
| **1100** | **all 4 mapped** | **all 4 hidden** |
| **900** | **all 4 mapped** | **all 4 hidden** |
| 760 | colour hidden, other 3 mapped | all 4 hidden |

### The fix, as implemented

`_INSPECTOR_DOCK_MIN = 1180` is now a named constant, and `_apply_layout()` is
three-way: **docked** (`pack`, ≥ 1180) / **floating** (`place`, < 1180) /
**hidden** (only when the user explicitly toggled it off). Below the breakpoint
the panel is placed against the right edge with `relx=1.0, anchor="ne"`, sized to
the gap between header and status bar, and lifted.

### Independent re-verification (my numbers, not the author's)

All four controls mapped at every width, and one gear click always changes what
the user sees:

```
w=1600  mgr=pack   mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w=1200  mgr=pack   mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w=1180  mgr=pack   mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w=1179  mgr=place  mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w=1100  mgr=place  mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w= 900  mgr=place  mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w= 860  mgr=place  mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
w= 760  mgr=place  mapped=1 ctrls=1111 firstClickChanges=True gearRestores=True
```

(`ctrls` = `color_btn`, `width_cb`, `btn_undo`, `btn_redo`; `mgr` = `winfo_manager()`.)

### Regression comparison, re-run in Phase C

| width | ORIGINAL `c3c340c` | REDESIGNED (Phase C) |
|---|---|---|
| 1600 | all 4 mapped | all 4 mapped |
| 1200 | all 4 mapped | all 4 mapped |
| 1100 | all 4 mapped | **all 4 mapped** |
| 900 | all 4 mapped | **all 4 mapped** |
| 760 | **colour hidden**, other 3 mapped | **all 4 mapped** |

The redesign now **matches the original everywhere and beats it at 760 px**,
where the original lost the colour swatch. The feature loss is fully reversed.

### The drawer is not a trap — verified

A floating panel with no way out would be worse than a hidden one, so I tested
the escape routes rather than assuming them:

| action at 1100 px | result |
|---|---|
| `Escape` | drawer dismissed |
| gear afterwards | drawer reopens |
| click on the canvas | drawer dismissed |
| gear afterwards | drawer reopens again |

And the dismissing canvas click **also performs the annotation it started** —
measured, not assumed:

```
baseline (drawer closed): one drag -> shapes = 1
drawer open:              one drag -> shapes 0 -> 1, drawer closed afterwards
two consecutive drags:    shapes = 1 then 2   (no click swallowed)
```

So the user never loses a click and never loses a stroke. That is the right
behaviour and it is the thing I most expected to be wrong.

### The drawer does not clip its own content

Widest descendant inside the floating panel ends at x=247 in a 248 px panel, at
every width. Vertically it occupies exactly the band between header and status
bar: header `y=0..58`, drawer `y=58..670`, status bar `y=670..700`.

### N1 — the drawer needs an elevation cue (RESOLVED after sign-off)

**Post-sign-off update (Lead, this session):** both suggested improvements were
implemented and re-verified. While floating, the inspector now has (1) a 2 px
`border_strong` shadow strip along its left edge, separating it visually from
the canvas, and (2) a `×` IconButton pinned to its top-right (`Đóng bảng thuộc
tính (Esc)` tooltip) that invokes `_dismiss_inspector_overlay`. Both cues are
placed/withdrawn by `_show_inspector_overlay` / `_hide_inspector_overlay`, so a
docked panel never shows them. Measured: shadow+close mapped at 1100/860/760,
both unmapped when docked at 1400, and invoking the close glyph maps the panel
off. Visible in the regenerated `a_editor_1100x760.png` and
`a_editor_860x700.png`. Suite re-run after the change: **169 tests, 0
failures, 0 errors.**

The rest of this section is the original Phase C note, kept for the record.

The panel that floats is styled **identically** to the docked one: `bd=0`,
`highlightthickness=0`, same `#1A1E27` fill, and no close button anywhere in its
painted content. Nothing on screen distinguishes "docked panel" from "overlay
covering my image".

It covers a real amount of the canvas:

| window | canvas viewport | drawer | covers |
|---|---|---|---|
| 1100 | 1000 px | 248 px | **24.8 %** |
| 900 | 800 px | 248 px | **31.0 %** |
| 860 | 768 px | 248 px | **32.3 %** |
| 760 | 668 px | 248 px | **37.1 %** |

At 860 px roughly a third of the working area is covered. That is acceptable
*because* it is dismissable and the dismissing click still draws — but the user
has no way to know either fact. Two cheap improvements, both optional:

1. A one-pixel `border`/`highlightthickness` on the left edge, or a slightly
   lighter fill, so the panel reads as floating rather than docked.
2. A `×` in the panel's top-right, so dismissal is discoverable without
   guessing `Escape`.

I would ship without these; I would not ship without the fix that made them
possible.


### Evidence images

- `_screens/after/a_editor_1100x760.png` — 1100×760 window: **no inspector at
  all**. The right third of the window is empty canvas. Nothing on screen
  indicates the panel exists.
- `_screens/after/a_editor_860x700.png` — 860×700: same, plus the rail has
  collapsed to icon-only.
- `_screens/after/a_editor_1920x1080.png` — 1872 px wide: inspector present and
  correct.

### Suggested fixes (design call is yours, not mine)

Any one of:
1. Lower the breakpoint to the app minimum and let the canvas take the squeeze,
   or
2. Make the gear open the inspector as an **overlay** below the breakpoint
   instead of refusing to show it, or
3. Drop `minsize` to 1180 so the app simply cannot be narrowed into the broken
   range (cheapest, but loses narrow-screen support the original had), or
4. Add the controls somewhere always visible (the header already has Copy/Save).

Do **not** just delete my three tests — they encode the user-visible guarantee.

### Tests that pin this

- `EditorReachabilityTests.test_inspector_controls_are_reachable_at_the_minimum_width`
- `EditorReachabilityTests.test_the_gear_works_at_every_width_the_window_allows`
- `EditorReachabilityTests.test_escape_dismisses_the_floating_inspector` *(new, Phase C)*
- `EditorReachabilityTests.test_the_gear_reopens_the_inspector_after_dismissing_it` *(new)*
- `EditorReachabilityTests.test_the_floating_inspector_does_not_cover_the_header_or_status_bar` *(new)*
- `EditorReachabilityTests.test_the_floating_inspector_keeps_its_controls_usable` *(new)*

---

## 2. B2 — hotkey casing (was minor, now FIXED)

The stored spec is upper-case (`validate_hotkey` uppercases, unchanged from
`c3c340c`), but three surfaces displayed it raw while the prose said `Alt+X`.

`ui_dialogs.display_hotkey()` now title-cases **at the display edge only**, so
the stored form the Win32 registrar compares against is untouched. Verified:

```
'ALT+X'        -> 'Alt+X'
'CTRL+SHIFT+S' -> 'Ctrl+Shift+S'
'DELETE'       -> 'Delete'
'DOUBLE-CLICK' -> 'Double-click'
''             -> ''
('CTRL','A')   -> ('CTRL','A')      # pass-through
None           -> None              # pass-through
42             -> 42                # pass-through
```

Visually confirmed in `_screens/after/d_info_1920x1080.png`: the keycap chips now
read `Alt` `+` `X`, `Ctrl` `+` `Z`, `Ctrl` `+` `S`, `Delete`, `Double-click`.

---

## 3. B3 — compact rail labels (was minor, now FIXED)

I had flagged that at ≤ 900 px the rail dropped captions and left "Làm mờ" as a
bare glyph. The fix takes the opposite approach to the one I would have chosen —
the rail grew from 52 to 64 px and **keeps all ten captions**.

Verified by reading every painted caption off the real `_ToolRailButton` canvases
at each width — all ten are present at 1100, 900, 860 and 760:

```
➤ Chọn   ⛶ Cắt   ⌫ Xóa   ✎ Bút   ✍ Dạ quang
▭ Chữ nhật   ◯ Oval   ↗ Mũi tên   T Văn bản   ≋ Làm mờ
```

I did not take "they all render" on trust, because the author's own arithmetic
admitted it was 3 px short and then concluded success. I measured the painted
text boxes directly: at 64 px the longest caption ("Dạ quang") has a `bbox` that
overruns the 48 px button by 3 px, which *sounds* like clipping. It is not — that
is tk `bbox` padding, not ink. Measuring actual bright pixels per row against the
crop shows every caption with **8–29 px of clearance** to the rail edge.

So: captions retained, nothing clipped, and my `Dạ quang` concern is closed.


---

## 4. What PASSES — verified, not assumed

### Visual quality at all three sizes

Captured 27 screenshots × 2 runs at 1920×1080, 1100×760 and 860×700. The
following were inspected image by image:

- **Editor, image loaded** (`a_editor_*.png`) — header, rail, canvas, inspector
  and status bar all render on the dark theme with no light patches, no
  overlapping widgets, no clipped text. Caption/subtitle correctly disappears
  at 860 px instead of colliding with the header buttons.
- **Editor, annotations drawn** (`b_editor_annotated_*.png`) — rect, arrow, pen
  (multi-point) and oval all render with correct colour and stroke width, at
  100 % zoom, legibly over a light screenshot.
- **Editor, shape selected** (`c_editor_selection_*.png`) — selection box and
  handle marquee visible, status bar updates to `460×190`.
- **Info dialog** (`d_info_*.png`) — the fully redesigned card. Two-column
  shortcut grid, segmented All/Capture/Edit filter, keycap chips (`ALT` `+` `X`)
  instead of raw text, footer hint bar. This is a large improvement over the
  legacy light dialog and it reads cleanly.
- **Hotkey dialog** (`f_hotkey_*.png`) — grouped sections, per-field live
  validation with green ticks, Restore-defaults / Cancel / Save row. Nothing
  clipped, nothing misaligned.
- **Shortcuts dialog** (`e_shortcuts_*.png`) — same card, typed entries.
- **Result toast** (`g_toast_copied_*.png`, `g_toast_notcopied_*.png`) — accent
  rail changes blue→amber, glyph check→warning, title changes, thumbnail,
  primary action and ghost dismiss all fit in 400×112 with no overflow. Both
  variants captured at `-alpha == 1.0` (verified by polling, not by sleeping).
- **Capture overlay** (`h_capture_overlay_*.png`) — dim layer with a clear
  selection hole, eight handles, dimension badge `660 × 448`, hint pill. Reads
  exactly as intended.

Contrast was measured, not eyeballed: `text_primary` 15.4–18.0:1,
`text_secondary` 8.0–9.3:1, `accent` 4.5–5.3:1, `success` 6.6:1, `warning` 7.8:1
against their real surfaces. Disabled button text is 3.68:1 on `COLORS.panel`
in every style — legible, and uniformly applied.
`text_muted` is 3.3–4.3:1: fine for the large/decorative uses it actually has,
below AA for body text. Worth knowing if it is ever used for real copy.

### Wiring — the lead's Phase B item 3

All verified through the real entry points, not by constructing dialogs
directly:

- `ImageEditor.show_function_info()` → `ui_dialogs.open_info_dialog` (pyw:897)
- `ImageEditor.open_hotkey_settings()` → `ui_dialogs.open_hotkey_dialog` (pyw:902)
- `ImageEditor.show_shortcuts_dialog()` → `ui_dialogs.open_shortcuts_dialog` (pyw:907)
- The header Info button actually opens a dialog; the gear actually flips state
  (at widths where the design allows it).
- Hotkey save round-trips into `capture_hotkey_var` **and** calls `save_config`.
- Copy → `send_to_clipboard`, Save → real PNG on disk, both through the button
  `invoke()`, i.e. the actual command wiring.
- The capture chain is driven end to end: fake 400×300 desktop → `start_snipping`
  → press/drag/release → `finish_snip` → a **200×150** crop → `current_toast`
  raised. A 4×3 selection is correctly discarded rather than toasted.

### Design system

86 parity tests: token completeness and format, `apply_theme` idempotence,
rendered Menu and combobox-popdown colours (the two places dark UIs leak light),
colour-helper maths, `round_rect` geometry, all widgets painting, the classic Tk
dialect (`config(text=)`, `cget`, `state`, `invoke`), variable traces, a
0.35-luminance contrast floor across all 30 `COLORS`, and a scanner that fails if
`ui_widgets.py` ever paints with a literal `#rrggbb`.

---

## 5. My own errors (recorded so nobody repeats them)

Every one of these was investigated and fixed in the tests, never reported as a
product defect:

1. Assumed `Secondary` disabled fill was `COLORS.elevated`; it is `COLORS.panel`.
2. Cached canvas item ids across a repaint — painted widgets `delete("all")`, so
   ids are never stable across a state change.
3. Drove `on_press`/`on_drag` with raw canvas coordinates. The editor **centres**
   the image (offset 626,346 on 1280×800), so clicks landed outside the image and
   strokes were clipped away. Everything now goes through `canvas_at(imgx, imgy)`.
   This is the bug class that makes a suite green while proving nothing.
4. `option_get` cannot read back `option_add`; replaced with assertions on the
   rendered widgets, which is a stronger test anyway.
5. Assumed `validate_hotkey("Alt+X") == "Alt+X"` (it uppercases) and that
   `_validate` returns `None` on success (it returns the normalised spec).
6. Called `tool.confirm_snip()` — the method is `finish_snip(x1,y1,x2,y2)`, and
   it returns immediately unless the user has pressed first (`snip_state == 1`),
   so my first version silently proved nothing. Now driven press→drag→release.
7. Looked for the toast on `tool.toast`; the attribute is `current_toast`.
8. **Captured a black band as if it were clipping.** `PrintWindow` on a
   decorated window includes the invisible DWM border plus unpainted columns.
   I measured it (8 px real border + ~32 unrendered columns right, 39 rows
   bottom) with a solid-colour control window before concluding anything, and
   `visual_check.py` now trims only thin bands (≤ 14 px) and explicitly refuses
   to trim wide ones so a genuine framing bug cannot be masked.

---

## 6. How to reproduce

```powershell
cd C:\Users\anh25\Downloads\Projects\TestUI\ScreenShotTool
$env:PYTHONIOENCODING='utf-8'
$py = 'C:\Users\anh25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'

& $py -m unittest discover -s tests            # 165 tests; 3 failures = B1
& $py -m unittest tests.test_ui_parity         # 86, OK
& $py tests\visual_check.py                    # 27 PNGs into _screens\after
& $py tests\visual_check.py --only 860x700     # one size
```

`tests/visual_check.py` is a script, deliberately not a unittest: it launches
the real UI, drives it, and writes evidence. It uses `PrintWindow` via
`_win_shots.capture_window` (never `ImageGrab`, which would capture whatever
window happens to overlap), polls `-alpha` until the toast is fully opaque, and
clamps the window to the usable screen area.

`$env:PYTHONIOENCODING='utf-8'` is mandatory — the UI carries Vietnamese text and
cp1252 crashes the run.

---

## 7. Shippability

**Not shippable until B1 is fixed.** It is a single, well-isolated defect in
`_apply_layout` / `toggle_inspector`, and it is the difference between "the
redesign is lovely" and "the redesign cost me the colour picker on my laptop".

Everything else I was asked to judge — visual quality, responsive behaviour at
three sizes, dialog design, toast, capture overlay, contrast, and the entire
wiring of Alt+X capture → toast → Info → hotkey dialog → Save/Copy — passes with
evidence. B2 and B3 are cosmetic and can ship as-is if time is short.
