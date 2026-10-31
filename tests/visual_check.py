# -*- coding: utf-8 -*-
"""tests/visual_check.py - visual QA harness for the ScreenShotTool redesign.

NOT a unittest: this launches the real UI, drives it, and writes PNG evidence to
``_screens/after/``.  Run it directly:

    $env:PYTHONIOENCODING='utf-8'
    python tests/visual_check.py            # default 1920x1080 + 1100x760 + 860x700
    python tests/visual_check.py --only 1100x760

Capture method: ``PrintWindow`` via ``_win_shots.capture_window``, because
``PIL.ImageGrab`` copies screen pixels and any overlapping window (including the
Tk windows a previous step left behind) ruins the shot.

The ResultToast fades in with ``-alpha`` over ~0.5 s, so every animation is
drained to completion before the shutter: capturing at 25 % opacity would make
the card look broken when it is only mid-fade.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import _win_shots
import ui_theme as T

OUT = REPO / "_screens" / "after"

SIZES = {
    "1920x1080": (1920, 1080),
    "1100x760": (1100, 760),
    "860x700": (860, 700),
}

# A screenshot stand-in that looks like a real captured window, so the canvas
# contrast and the annotation colours can be judged against something plausible.
def sample_screenshot(width=1400, height=880):
    image = Image.new("RGB", (width, height), (246, 247, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 54], fill=(32, 38, 52))
    draw.rectangle([0, 54, 210, height], fill=(240, 242, 247))
    for row in range(9):
        y = 92 + row * 44
        draw.rectangle([28, y, 180, y + 22], fill=(206, 212, 224))
    draw.rectangle([250, 88, 880, 128], fill=(58, 110, 220))
    draw.rectangle([250, 150, 1240, 300], fill=(255, 255, 255),
                   outline=(214, 219, 230), width=2)
    draw.rectangle([250, 322, 1240, 472], fill=(255, 255, 255),
                   outline=(214, 219, 230), width=2)
    draw.rectangle([250, 494, 700, 760], fill=(255, 255, 255),
                   outline=(214, 219, 230), width=2)
    draw.rectangle([720, 494, 1240, 760], fill=(255, 255, 255),
                   outline=(214, 219, 230), width=2)
    for i in range(14):
        draw.rectangle([272, 170 + i * 9, 272 + (90 + (i * 37) % 500), 174 + i * 9],
                       fill=(226, 230, 238))
        draw.rectangle([272, 344 + i * 9, 272 + (90 + (i * 53) % 560), 348 + i * 9],
                       fill=(226, 230, 238))
    for col in range(3):
        for row in range(4):
            draw.ellipse([790 + col * 150, 530 + row * 56,
                          838 + col * 150, 578 + row * 56],
                         fill=(120 + col * 30, 150, 230 - row * 20))
    return image


# --------------------------------------------------------------------------
# Harness plumbing
# --------------------------------------------------------------------------
def load_app():
    spec = importlib.util.spec_from_file_location("sst_visual", REPO / "ScreenShotTool.pyw")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sst_visual"] = module
    spec.loader.exec_module(module)
    # Never touch the developer's real config while driving the UI.
    module.CONFIG_FILE = str(OUT / "_visual_config.json")
    module.save_config = lambda cfg: None
    return module


def settle(root, pulses=6, delay=0.02):
    """Pump Tk until it stops doing work (layouts, queued after() calls)."""
    for _ in range(pulses):
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            return
        time.sleep(delay)


def wait_for_alpha(window, target=1.0, timeout=3.0, root=None):
    """Block until a fading Toplevel is fully opaque.

    ResultToast animates ``-alpha`` from 0 to 1 over ~8 steps; capturing at
    25 % yields a washed-out card that looks like a bug but is not one.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if root is not None:
                root.update_idletasks()
                root.update()
            value = float(window.attributes("-alpha"))
        except (tk.TclError, ValueError):
            return None
        last = value
        if value >= target:
            return value
        time.sleep(0.03)
    return last


def trim_capture_band(path, reference_colors=None):
    """Remove the black band ``PrintWindow`` leaves around a decorated window.

    For a normal Toplevel, ``GetWindowRect`` includes the invisible DWM resize
    border, and the bitmap ``PrintWindow`` fills is slightly larger than the
    client area, so the capture ends up with a black margin (measured: 8 px of
    real border plus ~32 unrendered columns on the right, 39 rows at the
    bottom). That margin is an artefact of the capture, NOT of the layout, and
    leaving it in makes every screenshot look like the inspector is clipped.
    Trimming it here keeps the evidence honest.
    """
    from PIL import Image as _Image

    image = _Image.open(path).convert("RGB")
    width, height = image.size
    colors = set(reference_colors or ())
    if not colors:
        # Sample a few interior pixels to learn the surfaces actually in use.
        for point in ((4, height // 2), (width // 2, 4), (width - 60, height // 2),
                      (width // 2, height - 60), (width // 2, height // 2)):
            colors.add(image.getpixel(point))

    def is_content(xy):
        return image.getpixel(xy) not in ((0, 0, 0),)

    right = width - 1
    while right > 0 and not is_content((right, height // 2)):
        right -= 1
    bottom = height - 1
    while bottom > 0 and not is_content((width // 2, bottom)):
        bottom -= 1
    left = 0
    while left < right and not is_content((left, height // 2)):
        left += 1
    top = 0
    while top < bottom and not is_content((width // 2, top)):
        top += 1

    # A window that is partly off-screen leaves a *wide* black band because DWM
    # never painted those columns. Cropping that away would hide a real framing
    # bug, so only ever trim the thin decoration border.
    MAX_BAND = 14
    bands = (left, top, width - 1 - right, height - 1 - bottom)
    if max(bands) > MAX_BAND:
        print("    !! wide black band l=%d t=%d r=%d b=%d - NOT trimmed "
              "(window likely partly off-screen)" % bands)
        return image

    if (left, top, right, bottom) != (0, 0, width - 1, height - 1):
        image = image.crop((left, top, right + 1, bottom + 1))
        image.save(path)
        print("    trimmed capture band: %dx%d -> %dx%d"
              % (width, height, image.width, image.height))
    return image


def capture(widget, path, trim=True):
    _win_shots.capture_window(widget, path)
    if trim:
        trim_capture_band(path)
    return path


def report(path):
    try:
        return "%s (%s)" % (path.relative_to(REPO), Image.open(path).size)
    except Exception:
        return str(path)


# --------------------------------------------------------------------------
# Scenes
# --------------------------------------------------------------------------
def scene_editor(module, root, size, name):
    """(a) editor with an image loaded, and (b) with an annotation drawn."""
    saved = []
    editor = module.ImageEditor(root, sample_screenshot())
    # ImageEditor.__init__ maximises itself on any screen >= 1600x900, which
    # silently overrides a geometry() call made before the window is mapped.
    # Force a normal, explicitly sized window so the narrow breakpoints are
    # actually exercised instead of three identical 1920-wide shots.
    editor.top.state("normal")
    editor.top.update_idletasks()
    # A 1920-wide window on a 1920-wide display cannot fit once the frame border
    # is counted, and DWM then leaves unpainted columns that look like clipping.
    # Clamp to the usable area so every capture shows the whole widget.
    screen_w = editor.top.winfo_screenwidth()
    screen_h = editor.top.winfo_screenheight()
    win_w = min(size[0], screen_w - 48)
    win_h = min(size[1], screen_h - 96)
    pos_x = max(0, (screen_w - win_w) // 2)
    pos_y = max(0, min(24, screen_h - win_h - 60))
    editor.top.geometry("%dx%d+%d+%d" % (win_w, win_h, pos_x, pos_y))
    editor.top.update_idletasks()
    settle(root, 12, 0.03)
    got = (editor.top.winfo_width(), editor.top.winfo_height())
    print("  editor window %dx%d (requested %dx%d)" % (got + size))
    if got[0] < size[0] - 120:
        print("  !! window refused the requested width (%dx%d vs %dx%d)"
              % (got + size))
    editor.redraw_all()
    settle(root, 6)

    path_a = OUT / ("a_editor_%s.png" % name)
    capture(editor.top, path_a)
    saved.append(path_a)

    # Draw one of each interesting annotation so overlap/legibility is visible.
    def drag(tool, start, end):
        editor.tool_var.set(tool)
        editor._apply_layout(editor.top.winfo_width())
        settle(root, 2)
        mk = lambda x, y: type("E", (), {
            "x": int(x * editor.scale + editor.offset_x),
            "y": int(y * editor.scale + editor.offset_y),
            "state": 0, "widget": editor.canvas})()
        editor.on_press(mk(*start))
        steps = 6
        for i in range(1, steps + 1):
            editor.on_drag(mk(start[0] + (end[0] - start[0]) * i / steps,
                              start[1] + (end[1] - start[1]) * i / steps))
        editor.on_release(mk(*end))
        settle(root, 2)

    editor.width_var.set(5)
    editor.color_var.set("#e5484d")
    drag("rect", (60, 60), (520, 250))
    editor.color_var.set("#f5a623")
    drag("arrow", (600, 90), (900, 260))
    editor.color_var.set("#3b82f6")
    drag("pen", (80, 300), (420, 380))
    drag("pen", (420, 380), (520, 300))
    editor.color_var.set("#10b981")
    drag("oval", (600, 320), (860, 470))
    editor.tool_var.set("rect")     # one tool active for the shot
    editor._apply_layout(editor.top.winfo_width())
    settle(root, 8)

    path_b = OUT / ("b_editor_annotated_%s.png" % name)
    capture(editor.top, path_b)
    saved.append(path_b)

    # (c) a selected shape, to expose the selection chrome
    if editor.shapes:
        editor.tool_var.set("select")
        settle(root, 2)
        first = editor.shapes[0]["tag"]
        editor.selected_tag = first
        editor.selected_tags = [first]
        editor.draw_selection_box()
        editor._refresh_metrics(selection=(int(abs(editor.shapes[0]["coords"][2] -
                                                   editor.shapes[0]["coords"][0])),
                                           int(abs(editor.shapes[0]["coords"][3] -
                                                   editor.shapes[0]["coords"][1]))))
        settle(root, 6)
        path_sel = OUT / ("c_editor_selection_%s.png" % name)
        capture(editor.top, path_sel)
        saved.append(path_sel)

    return editor, saved


def scene_dialogs(module, editor, root, name):
    saved = []
    dialogs = []

    # (d) Info dialog through the real app entry point.
    try:
        editor.show_function_info()
        settle(root, 8, 0.04)
        for child in editor.top.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                dialogs.append(("d_info", child))
                break
    except Exception as exc:
        print("  !! show_function_info failed: %s: %s" % (type(exc).__name__, exc))

    # (e) Shortcuts dialog through the real app entry point.
    try:
        editor.show_shortcuts_dialog()
        settle(root, 8, 0.04)
        for child in editor.top.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                if all(child is not d for _n, d in dialogs):
                    dialogs.append(("e_shortcuts", child))
                    break
    except Exception as exc:
        print("  !! show_shortcuts_dialog failed: %s: %s" % (type(exc).__name__, exc))

    # (f) Hotkey dialog through the frozen ui_dialogs signature.
    try:
        import ui_dialogs
        hk = ui_dialogs.open_hotkey_dialog(editor.top, dict(editor.cfg),
                                           lambda cfg: None)
        settle(root, 8, 0.04)
        dialogs.append(("f_hotkey", hk))
    except Exception as exc:
        print("  !! open_hotkey_dialog failed: %s: %s" % (type(exc).__name__, exc))

    for label, dialog in dialogs:
        try:
            dialog.update_idletasks()
            dialog.lift()
            settle(root, 4)
            path = OUT / ("%s_%s.png" % (label, name))
            capture(dialog, path)
            saved.append(path)
        except Exception as exc:
            print("  !! capture %s failed: %s: %s" % (label, type(exc).__name__, exc))
        finally:
            try:
                dialog.destroy()
            except Exception:
                pass

    return saved


def scene_toast(module, root, name):
    """(g) capture result toast, fully faded in."""
    saved = []
    try:
        import ui_capture
        image = sample_screenshot(900, 620)
        for variant, copied in (("copied", True), ("notcopied", False)):
            toast = ui_capture.ResultToast(root, image, copied=copied,
                                           on_open_editor=lambda img: None,
                                           duration=30000)
            toast.show()
            settle(root, 4)
            window = getattr(toast, "window", None)
            alpha = wait_for_alpha(window, 1.0, 3.0, root) if window is not None else None
            print("  toast[%s] alpha settled at %s" % (variant, alpha))
            settle(root, 4)
            path = OUT / ("g_toast_%s_%s.png" % (variant, name))
            capture(window or root, path)
            saved.append(path)
            toast.destroy()
            settle(root, 3)
    except Exception as exc:
        print("  !! toast capture failed: %s: %s" % (type(exc).__name__, exc))
    return saved


def scene_capture_overlay(module, root, name):
    """(h) the snipping overlay itself, against a fake 1280x800 desktop."""
    saved = []
    try:
        from unittest import mock
        import ui_capture

        # mss hands back BGRA bytes; give the overlay a plausible desktop so the
        # dim layer, the selection hole and the handles can all be judged.
        desk = sample_screenshot(1280, 800).convert("RGB").tobytes("raw", "BGRX")
        fake = mock.MagicMock()
        fake.size = (1280, 800)
        fake.bgra = desk
        session = mock.MagicMock()
        session.monitors = [{"left": 0, "top": 0, "width": 1280, "height": 800}]
        session.grab.return_value = fake

        tool = ui_capture.SnippingTool(root, keyboard_module=False)
        with mock.patch.object(ui_capture, "mss",
                               mock.MagicMock(**{"mss.return_value": session})):
            tool.start_snipping()
            settle(root, 8, 0.03)
            # draw a live selection so handles/badge/magnifier are visible
            if getattr(tool, "full_img", None) is not None:
                tool.draw_selection(240, 180, 900, 620)
                settle(root, 6)
            path = OUT / ("h_capture_overlay_%s.png" % name)
            capture(root, path)
            saved.append(path)
            tool.cancel_snip()
            settle(root, 4)
    except Exception as exc:
        print("  !! overlay capture failed: %s: %s" % (type(exc).__name__, exc))
    return saved


def run_size(module, label):
    width, height = SIZES[label]
    print("\n== %s ==" % label)
    OUT.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.geometry("%dx%d+20+20" % (width, height))
    T.apply_theme(root)
    settle(root, 4)

    saved = []
    editor = None
    try:
        editor, shots = scene_editor(module, root, (width, height), label)
        saved += shots
        saved += scene_dialogs(module, editor, root, label)
        saved += scene_toast(module, root, label)
        saved += scene_capture_overlay(module, root, label)
    finally:
        if editor is not None:
            try:
                editor.top.destroy()
            except Exception:
                pass
        settle(root, 3)
        try:
            root.destroy()
        except Exception:
            pass

    for path in saved:
        print("  ->", report(path))
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", choices=sorted(SIZES),
                        help="capture only the given size (repeatable)")
    args = parser.parse_args()

    labels = args.only or list(SIZES)
    OUT.mkdir(parents=True, exist_ok=True)
    module = load_app()

    everything = []
    for label in labels:
        everything += run_size(module, label)

    print("\n%d screenshot(s) written to %s" % (len(everything), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
