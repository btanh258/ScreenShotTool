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


if __name__ == "__main__":
    unittest.main()
