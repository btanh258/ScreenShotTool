"""Tests for the features added in the UI/feature review.

Covers: copy-on-write undo and its memory budget, fit-to-window, the resize
debounce, the extra export formats, the capture history, the pinned window, and
theme switching including WCAG contrast. Nothing here touches the UI contract
pinned by test_transform.py.
"""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_editor_io
import ui_extras
import ui_theme as T

# Same trick as test_ui_smoke: point the config at a file that never exists so a
# developer's real settings cannot change what these tests observe.
_NEVER = str(TESTS_DIR / "_test_config_never_exists.json")


def _app():
    """Load ScreenShotTool.pyw once per class.

    Must not swap sys.modules while re-executing the module: replacing it breaks
    the C extension imports that Pillow and Tk perform during module init
    ("PyCapsule_Import could not import module datetime").
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sst_app_under_test", ROOT / "ScreenShotTool.pyw")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ThemeTests(unittest.TestCase):
    """Theme switching must swap every token and be reversible."""

    def tearDown(self):
        T.set_theme("dark")

    def test_light_and_dark_declare_the_same_tokens(self):
        self.assertEqual(set(T.COLORS_DARK.keys()), set(T.COLORS_LIGHT.keys()),
                         "a token present in one palette only would be undefined "
                         "in the other")

    def test_switching_to_light_changes_every_token(self):
        T.set_theme("light")
        stale = [name for name in T.COLORS_LIGHT.keys()
                 if T.COLORS[name] != T.COLORS_LIGHT[name]]
        self.assertEqual(stale, [])
        self.assertEqual(T.get_theme(), "light")

    def test_switching_back_restores_the_dark_palette(self):
        T.set_theme("light")
        T.set_theme("dark")
        self.assertEqual(T.get_theme(), "dark")
        for name in T.COLORS_DARK.keys():
            self.assertEqual(T.COLORS[name], T.COLORS_DARK[name], name)

    def test_unknown_theme_falls_back_to_dark(self):
        T.set_theme("hotdog")
        self.assertEqual(T.get_theme(), "dark")

    def test_resolve_theme_honours_explicit_choices(self):
        self.assertEqual(T.resolve_theme("light"), "light")
        self.assertEqual(T.resolve_theme("dark"), "dark")
        # "system" defers to the OS, so only assert it yields a real palette.
        self.assertIn(T.resolve_theme("system"), ("light", "dark"))

    def test_light_text_meets_wcag_contrast(self):
        """The first light palette measured 3.2:1 and 2.2:1 for secondary/muted."""
        def luminance(value):
            value = value.lstrip("#")
            r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        def ratio(fg, bg):
            a, b = luminance(fg), luminance(bg)
            high, low = max(a, b), min(a, b)
            return (high + 0.05) / (low + 0.05)

        palette = T.COLORS_LIGHT
        cases = [
            ("text_primary", "app", 4.5),
            ("text_primary", "panel", 4.5),
            ("text_secondary", "panel", 4.5),
            ("text_secondary", "app", 4.5),
            ("text_muted", "panel", 3.0),
            ("text_muted", "app", 3.0),
            ("success", "panel", 3.0),
            ("danger", "panel", 3.0),
            ("warning", "panel", 3.0),
            ("info", "panel", 3.0),
        ]
        for fg, bg, minimum in cases:
            with self.subTest(fg=fg, bg=bg):
                measured = ratio(palette[fg], palette[bg])
                self.assertGreaterEqual(
                    measured, minimum,
                    "%s on %s is %.2f:1, below %.1f:1" % (fg, bg, measured, minimum))


class ExportFormatTests(unittest.TestCase):
    """The three new formats must write a file another tool can reopen."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        self.image = Image.new("RGBA", (80, 60), (10, 120, 200, 255))

    def _save_as(self, suffix):
        """Call save_file with the dialog and the confirm prompt stubbed out."""
        host = mock.Mock()
        host.text_entry = None
        host.top = mock.Mock()
        path = os.path.join(self.dir, "out" + suffix)
        host.render_final_image = lambda: self.image
        with mock.patch.object(ui_editor_io.filedialog, "asksaveasfilename",
                              return_value=path), \
                mock.patch.object(ui_editor_io.messagebox, "askyesno",
                                  return_value=True):
            result = ui_editor_io.EditorExportMixin.save_file(host)
        return result, path

    def test_webp_is_written_losslessly_with_alpha(self):
        result, path = self._save_as(".webp")
        self.assertEqual(result, path)
        with Image.open(path) as check:
            check.load()
            self.assertEqual(check.format, "WEBP")
            self.assertEqual(check.size, self.image.size)

    def test_bmp_is_written_without_an_alpha_channel(self):
        result, path = self._save_as(".bmp")
        self.assertEqual(result, path)
        with Image.open(path) as check:
            check.load()
            self.assertEqual(check.format, "BMP")
            self.assertNotIn("A", check.mode,
                             "BMP has no alpha; leaving it in loses data silently")

    def test_jpeg_is_flattened_onto_white(self):
        transparent = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        flat = ui_editor_io._flatten_on_white(transparent)
        self.assertEqual(flat.mode, "RGB")
        self.assertEqual(flat.getpixel((0, 0)), (255, 255, 255),
                         "transparent pixels must not turn black in JPEG")

    def test_png_keeps_transparency(self):
        _, path = self._save_as(".png")
        with Image.open(path) as check:
            check.load()
            self.assertEqual(check.format, "PNG")
            self.assertIn("A", check.mode)

    def test_an_rgb_image_passes_through_flatten_untouched(self):
        rgb = Image.new("RGB", (4, 4), (1, 2, 3))
        self.assertIs(ui_editor_io._flatten_on_white(rgb), rgb)


class CaptureHistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.join(self._tmp.name, "history")

    def test_saving_stores_a_readable_png(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=5)
        path = history.save(Image.new("RGB", (30, 20), "#336699"))
        self.assertTrue(os.path.exists(path))
        with Image.open(path) as check:
            check.load()
            self.assertEqual(check.size, (30, 20))

    def test_the_oldest_entries_are_pruned(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=3)
        saved = [history.save(Image.new("RGB", (8, 8), (i * 10, 0, 0)))
                 for i in range(6)]
        remaining = history.entries()
        self.assertEqual(len(remaining), 3)
        for path in saved[-3:]:
            self.assertTrue(os.path.exists(path), "a recent entry was pruned")
        for path in saved[:-3]:
            self.assertFalse(os.path.exists(path), "an old entry survived")

    def test_newest_entry_sorts_first(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=10)
        first = history.save(Image.new("RGB", (4, 4), "#000000"))
        second = history.save(Image.new("RGB", (4, 4), "#111111"))
        self.assertEqual(history.entries()[0], second)
        self.assertEqual(history.entries()[-1], first)

    def test_transparent_captures_are_flattened_not_written_with_holes(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=5)
        path = history.save(Image.new("RGBA", (10, 10), (255, 0, 0, 0)))
        with Image.open(path) as check:
            check.load()
            self.assertEqual(check.mode, "RGB")

    def test_clear_removes_everything(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=5)
        for _ in range(3):
            history.save(Image.new("RGB", (4, 4), "#123456"))
        self.assertEqual(history.clear(), 3)
        self.assertEqual(history.entries(), [])

    def test_a_missing_directory_reports_no_entries(self):
        history = ui_extras.CaptureHistory(os.path.join(self.dir, "nope", "deeper"))
        self.assertEqual(history.entries(), [])

    def test_an_unwritable_directory_returns_none_instead_of_raising(self):
        history = ui_extras.CaptureHistory(self.dir, max_entries=5)
        with mock.patch.object(ui_extras.Image.Image, "save",
                               side_effect=OSError("disk full")):
            self.assertIsNone(history.save(Image.new("RGB", (4, 4), "#000000")))


class UndoHistoryTests(unittest.TestCase):
    """The history must be correct first and cheap second."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = self.app.ImageEditor(
            self.root, Image.new("RGB", (120, 90), (10, 200, 30)))
        self.editor.top.state("normal")
        for _ in range(6):
            self.root.update()
        self.addCleanup(self._teardown)

    def _teardown(self):
        try:
            self.editor.top.destroy()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_snapshots_share_one_image_when_only_annotations_change(self):
        for i in range(12):
            self.editor.shapes.append(
                {"type": "rect", "tag": "r%d" % i, "color": "#ff0000",
                 "width": 2, "coords": [i, i, 20 + i, 20 + i]})
            self.editor.save_state()
        images = {id(state["image"]) for state in self.editor.history}
        self.assertEqual(len(images), 1,
                         "annotation-only edits must not copy the image per step")
        self.assertGreater(len(self.editor.history), 12)

    def test_undo_after_erase_restores_the_untouched_pixels(self):
        original = self.editor.pil_image.getpixel((30, 30))
        self.editor.save_state()
        self.editor.erase_pixels((10, 10, 60, 60))
        self.editor.save_state()
        self.assertEqual(self.editor.pil_image.getpixel((30, 30))[3], 0,
                         "erase did not take effect")
        self.editor.undo()
        self.assertEqual(self.editor.pil_image.getpixel((30, 30))[:3], original[:3],
                         "undo brought back erased pixels - the shared snapshot "
                         "was mutated in place")

    def test_redo_returns_to_the_edited_state(self):
        self.editor.save_state()
        self.editor.pil_image = self.editor.pil_image.crop((0, 0, 60, 45))
        self.editor.orig_w, self.editor.orig_h = self.editor.pil_image.size
        self.editor.save_state()
        self.editor.undo()
        self.assertEqual(self.editor.pil_image.size, (120, 90))
        self.editor.redo()
        self.assertEqual(self.editor.pil_image.size, (60, 45))

    def test_history_stays_within_the_memory_budget(self):
        self.editor.MAX_HISTORY_BYTES = 200_000
        for index in range(25):
            self.editor.pil_image = self.editor.pil_image.crop(
                (0, 0, 120 - index, 90 - index)) if index < 60 else self.editor.pil_image
            self.editor.orig_w, self.editor.orig_h = self.editor.pil_image.size
            self.editor.save_state()
        self.assertLessEqual(self.editor._history_bytes(),
                             self.editor.MAX_HISTORY_BYTES,
                             "the budget did not bound destructive-edit history")

    def test_history_never_exceeds_the_step_cap(self):
        for _ in range(self.editor.MAX_HISTORY + 20):
            self.editor.save_state()
        self.assertLessEqual(len(self.editor.history), self.editor.MAX_HISTORY)

    def test_the_visible_state_is_never_pruned_away(self):
        self.editor.MAX_HISTORY = 5
        for _ in range(12):
            self.editor.save_state()
        self.assertGreaterEqual(self.editor.history_index, 0)
        self.assertLess(self.editor.history_index, len(self.editor.history))

    def test_editing_after_undo_discards_the_redo_branch(self):
        self.editor.save_state()
        self.editor.save_state()
        self.editor.undo()
        self.editor.save_state()
        self.assertEqual(self.editor.history_index, len(self.editor.history) - 1)


class FitToWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._destroy)

    def _destroy(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _editor(self, size):
        editor = self.app.ImageEditor(self.root, Image.new("RGB", size, "#556677"))
        editor.top.state("normal")
        editor.top.geometry("900x620+40+40")
        for _ in range(15):
            self.root.update()
        self.addCleanup(lambda: self._safe_destroy(editor.top))
        return editor

    @staticmethod
    def _safe_destroy(window):
        try:
            window.destroy()
        except tk.TclError:
            pass

    def test_a_large_image_is_scaled_down_to_fit(self):
        editor = self._editor((1920, 1080))
        scale = editor.fit_to_window()
        self.assertLess(scale, 1.0, "a 1920px image did not shrink on a 900px canvas")
        self.assertLessEqual(int(1920 * scale), editor.canvas.winfo_width())
        self.assertLessEqual(int(1080 * scale), editor.canvas.winfo_height())

    def test_a_small_image_is_never_magnified(self):
        editor = self._editor((100, 80))
        self.assertEqual(editor.fit_to_window(), 1.0,
                         "fit must not blow a small image up")

    def test_fit_never_goes_below_the_zoom_floor(self):
        editor = self._editor((6000, 4000))
        self.assertGreaterEqual(editor.fit_to_window(), 0.2)


class DebounceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = self.app.ImageEditor(
            self.root, Image.new("RGB", (300, 200), "#334455"))
        self.editor.top.state("normal")
        for _ in range(8):
            self.root.update()
        self.calls = 0
        original = self.editor.redraw_all

        def counting():
            self.calls += 1
            return original()

        self.editor.redraw_all = counting
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for widget in (self.editor.top, self.root):
            try:
                widget.destroy()
            except tk.TclError:
                pass

    def test_a_burst_of_resize_events_coalesces_into_one_redraw(self):
        import time
        self.calls = 0
        for width in range(400, 430):
            self.editor._on_canvas_configure(None)
            self.root.update()
        time.sleep(0.12)
        self.root.update()
        self.assertLessEqual(self.calls, 2,
                             "each <Configure> repainted; the drag would stutter")

    def test_a_pending_redraw_can_be_cancelled(self):
        self.editor._on_canvas_configure(None)
        timer = self.editor._configure_redraw_id
        self.assertIsNotNone(timer)
        self.editor._cancel_configure_redraw()
        self.assertIsNone(self.editor._configure_redraw_id)


class PinnedImageTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_the_window_is_topmost_and_carries_the_image_size(self):
        image = Image.new("RGB", (120, 80), "#aabbcc")
        pin = ui_extras.PinnedImage(self.root, image)
        self.addCleanup(pin.close)
        self.root.update()
        self.assertEqual(int(pin.window.attributes("-topmost")), 1)
        self.assertEqual((pin.image.width, pin.image.height), (120, 80))

    def test_alpha_is_clamped_to_a_visible_range(self):
        pin = ui_extras.PinnedImage(self.root, Image.new("RGB", (40, 40), "#000000"))
        self.addCleanup(pin.close)
        self.assertEqual(pin.set_alpha(0.0), ui_extras.PinnedImage.MIN_ALPHA,
                         "fading to zero would hide the window irrecoverably")
        self.assertEqual(pin.set_alpha(9.0), 1.0)

    def test_close_is_safe_to_call_twice(self):
        pin = ui_extras.PinnedImage(self.root, Image.new("RGB", (20, 20), "#111111"))
        pin.close()
        pin.close()


class LiveThemeSwitchTests(unittest.TestCase):
    """The editor's theme button must repaint live and keep the document.

    Tk freezes a widget's colours at creation, so the switch rebuilds the whole
    widget tree. These tests exist because the first rebuild crashed with
    "bad window path name": stale widget references from the old tree were
    placed() again, and because a rebuild that silently dropped the shapes,
    the history or the zoom would be worse than no feature at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        T.set_theme("dark")

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = self.app.ImageEditor(
            self.root, Image.new("RGB", (320, 240), (10, 200, 30)))
        self.editor.top.state("normal")
        for _ in range(10):
            self.root.update()
        self.addCleanup(self._teardown)

    def _teardown(self):
        T.set_theme("dark")
        for widget in (self.editor.top, self.root):
            try:
                widget.destroy()
            except tk.TclError:
                pass

    def _seed_document(self):
        editor = self.editor
        editor.shapes.append({"tag": "shape_1", "type": "rect",
                              "color": "#ff0000", "width": 3,
                              "coords": [10, 10, 120, 90]})
        editor.save_state()
        editor.set_zoom(0.75)
        editor.redraw_all()
        self.root.update()

    def test_toggling_rewrites_the_palette_and_repaints_the_chrome(self):
        self._seed_document()
        before = self.editor.header.cget("bg")
        applied = self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        self.assertEqual(applied, "light")
        self.assertEqual(T.get_theme(), "light")
        self.assertNotEqual(self.editor.header.cget("bg"), before)
        self.assertEqual(self.editor.header.cget("bg"), T.COLORS_LIGHT.chrome)

    def test_toggling_back_restores_the_dark_chrome(self):
        self._seed_document()
        self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        self.assertEqual(T.get_theme(), "dark")
        self.assertEqual(self.editor.header.cget("bg"), T.COLORS_DARK.chrome)

    def test_shapes_history_zoom_and_selection_survive_the_rebuild(self):
        self._seed_document()
        before = {
            "shapes": [(s["tag"], s["type"], list(s["coords"]))
                       for s in self.editor.shapes],
            "history": len(self.editor.history),
            "index": self.editor.history_index,
            "scale": self.editor.scale,
            "pixel": self.editor.pil_image.getpixel((50, 50)),
        }
        self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        after = {
            "shapes": [(s["tag"], s["type"], list(s["coords"]))
                       for s in self.editor.shapes],
            "history": len(self.editor.history),
            "index": self.editor.history_index,
            "scale": self.editor.scale,
            "pixel": self.editor.pil_image.getpixel((50, 50)),
        }
        self.assertEqual(before, after)

    def test_undo_still_works_on_the_rebuilt_window(self):
        self._seed_document()
        self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        index = self.editor.history_index
        self.editor.undo()
        self.assertLess(self.editor.history_index, index)
        self.editor.redo()
        self.assertEqual(self.editor.history_index, index)

    def test_the_choice_is_persisted_to_the_config(self):
        self._seed_document()
        with mock.patch.object(self.app, "save_config") as save:
            self.editor.toggle_theme()
        save.assert_called_once()
        self.assertEqual(save.call_args[0][0].get("theme"), "light")

    def test_the_theme_button_exists_in_the_header(self):
        self.assertTrue(hasattr(self.editor, "btn_theme"),
                        "the editor header must expose the theme switch")
        self.assertTrue(hasattr(self.editor, "toggle_theme"))

    def test_other_open_editors_are_re_tinted_too(self):
        other = self.app.ImageEditor(
            self.root, Image.new("RGB", (60, 40), (5, 5, 5)))
        other.top.state("normal")
        for _ in range(10):
            self.root.update()
        try:
            self._seed_document()
            dark_other = other.header.cget("bg")
            self.editor.toggle_theme()
            for _ in range(10):
                self.root.update()
            self.assertNotEqual(other.header.cget("bg"), dark_other,
                                "a second open window stayed in the old palette")
        finally:
            try:
                other.top.destroy()
            except tk.TclError:
                pass

    def test_no_stale_widget_reference_is_left_behind(self):
        """The first rebuild died on a placed() widget from the destroyed tree."""
        self._seed_document()
        self.editor.toggle_theme()
        for _ in range(10):
            self.root.update()
        # _overlay_shadow is recreated by the builders; it must be alive.
        shadow = getattr(self.editor, "_overlay_shadow", None)
        if shadow is not None:
            self.assertTrue(shadow.winfo_exists())


class BrushDotTests(unittest.TestCase):
    """A click with no drag must leave a dot, not nothing.

    Both brushes used to swallow it: the highlighter dropped any stroke with
    fewer than two points, and the pen asked Tk for a single-point line, which
    Tk draws as nothing at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = self.app.ImageEditor(
            self.root, Image.new("RGB", (200, 150), (30, 60, 90)))
        self.editor.top.state("normal")
        for _ in range(8):
            self.root.update()
        self.addCleanup(self._teardown)

    def _teardown(self):
        try:
            self.editor.top.destroy()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    class _Event:
        def __init__(self, x, y, state=0):
            self.x, self.y, self.state = x, y, state

    def _inside(self, x=100, y=75):
        """Canvas position of an image coordinate, so clicks land on the image.

        The canvas centres a small image, so a raw canvas coordinate can sit
        outside it - and a shape drawn there is legitimately invisible.
        """
        self.editor.redraw_all()
        self.root.update()
        return (x * self.editor.scale + self.editor.offset_x,
                y * self.editor.scale + self.editor.offset_y)

    def _click(self, tool, image_point=(100, 75)):
        editor = self.editor
        cx, cy = self._inside(*image_point)
        editor.tool_var.set(tool)
        editor.on_press(self._Event(int(cx), int(cy)))
        editor.on_release(self._Event(int(cx), int(cy)))
        for _ in range(4):
            self.root.update()

    def _items_for(self, tag):
        return [item for item in self.editor.canvas.find_all()
                if tag in self.editor.canvas.gettags(item)]

    def test_pen_click_creates_one_shape(self):
        self._click("pen")
        self.assertEqual(len(self.editor.shapes), 1)
        self.assertEqual(self.editor.shapes[0]["type"], "pen")

    def test_pen_click_is_visible_on_the_canvas(self):
        self._click("pen")
        tag = self.editor.shapes[0]["tag"]
        items = self._items_for(tag)
        self.assertTrue(items, "the dot produced no canvas item")
        self.assertEqual(self.editor.canvas.type(items[0]), "oval",
                         "a single click should be drawn as a dot")

    def test_pen_click_survives_a_redraw(self):
        self._click("pen")
        tag = self.editor.shapes[0]["tag"]
        self.editor.redraw_all()
        self.root.update()
        items = self._items_for(tag)
        self.assertTrue(items, "the dot vanished on redraw")
        self.assertEqual(self.editor.canvas.type(items[0]), "oval")

    def test_pen_click_is_exported(self):
        self._click("pen")
        shape = self.editor.shapes[0]
        rendered = self.editor.render_final_image()
        self.assertEqual(rendered.mode, "RGBA")
        # The shape stores image coordinates, so probe where it actually is.
        ix, iy = int(round(shape["coords"][0])), int(round(shape["coords"][1]))
        pixel = rendered.getpixel((ix, iy))
        self.assertNotEqual(pixel[:3], (30, 60, 90),
                            "the dot was not rendered into the export")

    def test_highlight_click_creates_one_shape(self):
        self._click("highlight")
        self.assertEqual(len(self.editor.shapes), 1,
                         "the highlighter discarded the click")
        shape = self.editor.shapes[0]
        self.assertEqual(shape["type"], "highlight")
        self.assertIn("orig_pil_img", shape,
                      "the highlighter dot has no painted layer")
        self.assertGreater(shape["orig_pil_img"].width, 0)
        self.assertGreater(shape["orig_pil_img"].height, 0)

    def test_highlight_click_is_visible_on_the_canvas(self):
        self._click("highlight")
        tag = self.editor.shapes[0]["tag"]
        self.assertTrue(self._items_for(tag),
                        "the highlighter dot produced no canvas item")

    def test_a_drag_still_draws_a_stroke(self):
        editor = self.editor
        x0, y0 = self._inside(20, 20)
        editor.tool_var.set("pen")
        editor.on_press(self._Event(int(x0), int(y0)))
        editor.on_drag(self._Event(int(x0) + 40, int(y0) + 30))
        editor.on_drag(self._Event(int(x0) + 70, int(y0) + 10))
        editor.on_release(self._Event(int(x0) + 70, int(y0) + 10))
        for _ in range(4):
            self.root.update()
        self.assertGreater(len(editor.shapes[0]["coords"]), 2,
                           "dragging must still record a multi-point stroke")
        tag = editor.shapes[0]["tag"]
        items = self._items_for(tag)
        self.assertTrue(any(editor.canvas.type(i) == "line" for i in items),
                        "a dragged stroke should be a line, not a dot")


class HistoryFloorTests(unittest.TestCase):
    """Undoing everything must return the document the editor opened.

    Trimming used to discard the oldest snapshot itself, so once a session
    passed the step cap the undo floor became an arbitrary mid-session state and
    the objects drawn before it looked deleted, with no way back.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = self.app.ImageEditor(
            self.root, Image.new("RGB", (120, 90), (10, 200, 30)))
        self.editor.top.state("normal")
        for _ in range(6):
            self.root.update()
        self.addCleanup(self._teardown)

    def _teardown(self):
        try:
            self.editor.top.destroy()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _add_shapes(self, count):
        for index in range(count):
            self.editor.shapes.append(
                {"type": "rect", "tag": self.editor.get_new_tag(),
                 "color": "#ff0000", "width": 2,
                 "coords": [index, index, 20 + index, 20 + index]})
            self.editor.save_state()

    def test_the_original_state_stays_at_the_bottom_of_the_stack(self):
        editor = self.editor
        editor.MAX_HISTORY = 5
        self._add_shapes(12)
        self.assertLessEqual(len(editor.history), editor.MAX_HISTORY,
                             "the step cap stopped being enforced")
        self.assertTrue(editor.history[0].get("baseline"),
                        "the baseline snapshot was trimmed away")

    def test_undoing_everything_returns_the_untouched_document(self):
        editor = self.editor
        editor.MAX_HISTORY = 5
        original = len(editor.shapes)
        self._add_shapes(12)
        while editor.history_index > 0:
            editor.undo()
        self.root.update()
        self.assertEqual(len(editor.shapes), original,
                         "undo stopped at a mid-session state instead of the "
                         "original document")

    def test_redo_still_reaches_the_latest_state(self):
        editor = self.editor
        editor.MAX_HISTORY = 5
        self._add_shapes(12)
        expected = len(editor.shapes)
        while editor.history_index > 0:
            editor.undo()
        while editor.history_index < len(editor.history) - 1:
            editor.redo()
        self.root.update()
        self.assertEqual(len(editor.shapes), expected)

    def test_the_memory_budget_also_spares_the_baseline(self):
        editor = self.editor
        editor.MAX_HISTORY = 50
        editor.MAX_HISTORY_BYTES = 1
        self._add_shapes(6)
        self.assertTrue(editor.history[0].get("baseline"))


class ToastLayoutTests(unittest.TestCase):
    """Every action on the capture toast must fit inside the card.

    The Pin button used to be placed from a running total that was never checked
    against the card width, so it hung off the right edge.
    """

    @classmethod
    def setUpClass(cls):
        import ui_capture
        cls.capture = ui_capture
        T.set_theme("dark")

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._teardown)

    def _teardown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _toast(self, on_pin):
        toast = self.capture.ResultToast(
            self.root, Image.new("RGB", (1095, 668), "#aaccee"),
            copied=True, on_open_editor=lambda: None, on_pin=on_pin)
        toast.show()
        for _ in range(12):
            self.root.update()
        self.addCleanup(toast.destroy)
        return toast

    def _layout(self, toast):
        canvas = toast.canvas
        rows = []
        for item in canvas.find_all():
            if canvas.type(item) != "window":
                continue
            widget = canvas.nametowidget(canvas.itemcget(item, "window"))
            x, y = canvas.coords(item)
            rows.append((y, x, widget.winfo_reqwidth()))
        return int(canvas.cget("width")), rows

    def test_pin_button_fits_inside_the_card(self):
        toast = self._toast(lambda image: None)
        width, rows = self._layout(toast)
        self.assertEqual(len(rows), 4, "expected close + three actions")
        for y, x, button_width in rows:
            self.assertLessEqual(x + button_width, width - 8,
                                 "a toast action overflows the card")

    def test_card_widens_to_hold_the_extra_action(self):
        without = self._toast(None)
        width_without, _ = self._layout(without)
        with_pin = self._toast(lambda image: None)
        width_with, _ = self._layout(with_pin)
        self.assertGreater(width_with, width_without,
                           "the card did not grow to fit the Pin button")
        self.assertGreaterEqual(width_without, self.capture.ResultToast.WIDTH)

    def test_actions_on_the_same_row_do_not_overlap(self):
        toast = self._toast(lambda image: None)
        _width, rows = self._layout(toast)
        by_row = {}
        for y, x, button_width in rows:
            by_row.setdefault(y, []).append((x, button_width))
        for y, buttons in by_row.items():
            buttons.sort()
            for i in range(len(buttons) - 1):
                self.assertLessEqual(buttons[i][0] + buttons[i][1],
                                     buttons[i + 1][0],
                                     "toast actions overlap on row %s" % y)

    def test_without_a_pin_handler_there_is_no_pin_button(self):
        toast = self._toast(None)
        _width, rows = self._layout(toast)
        self.assertEqual(len(rows), 3)


class UpdateWiringTests(unittest.TestCase):
    """The tray's "install update" path, without a network or a real exit.

    The parts that can go wrong here are the hand-offs: the right URL must be
    fetched, the swap must be given the downloaded file, and the app must only
    quit once the helper is actually running - quitting first would leave the
    user with no program at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._teardown)
        self.icon = mock.Mock()
        self.release = {
            "tag": "v9.9.9",
            "url": "https://example/tag",
            "assets": [{"name": "ScreenShotTool.exe",
                        "url": "https://example/app"}],
        }

    def _teardown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _run(self, downloader, applier, release=None):
        quit_calls = []
        with mock.patch.object(self.app.messagebox, "showerror") as error, \
                mock.patch.object(self.app.messagebox, "showinfo") as info:
            started = self.app._install_update(
                self.root, self.icon, release or self.release, "v9.9.9",
                lambda: quit_calls.append(True),
                downloader=downloader, applier=applier)
            for _ in range(8):
                self.root.update()
        return started, quit_calls, error, info

    def _recorder(self, result):
        calls = []

        def handler(*args, **kwargs):
            calls.append((args, kwargs))
            return result

        return calls, handler

    def test_successful_install_quits_so_the_helper_can_swap(self):
        download_calls, downloader = self._recorder("C:/tmp/new.exe")
        apply_calls, applier = self._recorder("C:/tmp/helper.bat")
        started, quit_calls, error, _info = self._run(downloader, applier)
        self.assertTrue(started)
        self.assertTrue(quit_calls, "the app must quit for the swap to happen")
        self.assertEqual(download_calls[0][0][0], "https://example/app",
                         "the packaged exe asset must be the one downloaded")
        self.assertEqual(apply_calls[0][0][0], "C:/tmp/new.exe")
        self.assertEqual(apply_calls[0][0][1], sys.executable)
        error.assert_not_called()

    def test_download_progress_is_announced(self):
        _calls, downloader = self._recorder("C:/tmp/new.exe")
        _a, applier = self._recorder("C:/tmp/helper.bat")
        self._run(downloader, applier)
        self.icon.notify.assert_called()

    def test_a_failed_download_keeps_the_current_build(self):
        _calls, downloader = self._recorder(None)
        apply_calls, applier = self._recorder("C:/tmp/helper.bat")
        started, quit_calls, error, _info = self._run(downloader, applier)
        self.assertTrue(started)
        self.assertFalse(quit_calls, "a failed download must not quit the app")
        self.assertFalse(apply_calls, "nothing was downloaded, so nothing to swap")
        error.assert_called()

    def test_a_failed_swap_keeps_the_current_build(self):
        _calls, downloader = self._recorder("C:/tmp/new.exe")
        _a, applier = self._recorder(None)
        _started, quit_calls, error, _info = self._run(downloader, applier)
        self.assertFalse(quit_calls,
                         "quitting without a working helper would lose the app")
        error.assert_called()

    def test_a_release_without_an_exe_is_refused(self):
        _calls, downloader = self._recorder("C:/tmp/new.exe")
        apply_calls, applier = self._recorder("C:/tmp/helper.bat")
        started, quit_calls, _error, info = self._run(
            downloader, applier,
            release={"tag": "v9.9.9", "url": "https://example/tag", "assets": []})
        self.assertFalse(started)
        self.assertFalse(quit_calls)
        self.assertFalse(apply_calls)
        info.assert_called()


if __name__ == "__main__":
    unittest.main()
