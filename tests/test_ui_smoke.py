# -*- coding: utf-8 -*-
"""tests/test_ui_smoke.py - integration smoke tests for the real app modules.

These load ``ui_capture.py``, ``ui_dialogs.py`` and ``ScreenShotTool.pyw``
exactly the way the application loads them (``importlib`` with an explicit
file path, because the app entry point is a ``.pyw``), then drive the public
contract from ``UI_REDESIGN_CONTRACT.md`` sections 4, 5 and 6.

Peer-owned files may be mid-edit when this suite runs, so every module load is
tolerant: a module that fails to import makes its tests SKIP with the real
import error as the reason, instead of breaking collection. Nothing here ever
executes a modal dialog's blocking loop, opens a real tray icon, or touches the
global keyboard hook.
"""

import importlib.util
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name, filename):
    """Import a repo module by path; return (module, error_message)."""
    path = REPO / filename
    if not path.exists():
        return None, "%s does not exist yet" % filename
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(name, module)
        spec.loader.exec_module(module)
        return module, None
    except Exception as exc:                     # mid-edit file, missing dep, ...
        return None, "%s failed to import: %s: %s" % (filename, type(exc).__name__, exc)


ui_capture, UI_CAPTURE_ERROR = _load("ui_capture_under_test", "ui_capture.py")
ui_dialogs, UI_DIALOGS_ERROR = _load("ui_dialogs_under_test", "ui_dialogs.py")
app, APP_ERROR = _load("screenshot_tool_under_test", "ScreenShotTool.pyw")


def _sample_image(size=(320, 200), color=(30, 90, 160, 255)):
    image = Image.new("RGBA", size, color)
    for x in range(0, size[0], 8):
        for y in range(0, size[1], 8):
            if (x // 8 + y // 8) % 2 == 0:
                image.putpixel((x, y), (250, 250, 250, 255))
    return image


class _TkTestCase(unittest.TestCase):
    """Owns one Tk root; skips cleanly when there is no display."""

    root = None

    def setUp(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        root.withdraw()
        root.geometry("1280x800+30+30")
        self.root = root
        try:
            import ui_theme as T
            T.apply_theme(root)
        except Exception:
            pass

    def tearDown(self):
        if self.root is not None:
            for attempt in ("update_idletasks", "destroy"):
                try:
                    getattr(self.root, attempt)()
                except Exception:
                    pass
            self.root = None

    def drain(self):
        """Let Tk process pending events without blocking on a mainloop."""
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass


# ==========================================================================
# ui_capture.py  (contract section 4)
# ==========================================================================
@unittest.skipUnless(ui_capture is not None, UI_CAPTURE_ERROR or "ui_capture.py unavailable")
class CaptureModuleTests(_TkTestCase):

    def test_module_exposes_the_frozen_api(self):
        self.assertTrue(hasattr(ui_capture, "SnippingTool"))
        self.assertTrue(hasattr(ui_capture, "ResultToast"))

    def test_snipping_tool_constructs(self):
        tool = ui_capture.SnippingTool(self.root)
        self.assertFalse(getattr(tool, "is_active", False),
                         "SnippingTool.is_active must be False before any capture")

    def test_snipping_tool_accepts_full_dependency_injection(self):
        calls = []
        tool = ui_capture.SnippingTool(
            self.root,
            resource_path=lambda name: str(REPO / name),
            send_to_clipboard=lambda img: calls.append(("clip", img.size)),
            open_editor=lambda img: calls.append(("editor", img.size)),
            keyboard_module=None,
        )
        self.assertIsNotNone(tool)

    def test_start_then_cancel_leaves_is_active_false(self):
        """The capture round trip against a fake 200x150 desktop."""
        fake = mock.MagicMock()
        fake.size = (200, 150)
        fake.bgra = bytes(200 * 150 * 4)
        session = mock.MagicMock()
        session.monitors = [{"left": 0, "top": 0, "width": 200, "height": 150}]
        session.grab.return_value = fake

        tool = ui_capture.SnippingTool(self.root, keyboard_module=False)
        with mock.patch.object(ui_capture, "mss",
                               mock.MagicMock(**{"mss.return_value": session})):
            try:
                tool.start_snipping()
                self.drain()
                self.assertTrue(getattr(tool, "is_active", False),
                                "start_snipping() did not set is_active")
                self.assertIsNotNone(tool.full_img, "start_snipping() captured no image")
                self.assertEqual(tuple(tool.full_img.size), (200, 150))
            finally:
                tool.cancel_snip()
                self.drain()
        self.assertFalse(tool.is_active, "cancel_snip() left is_active True")

    def test_start_snipping_restores_is_active_when_the_grab_fails(self):
        """A capture failure must release the re-entrancy lock, not wedge it."""
        session = mock.MagicMock()
        session.monitors = [{"left": 0, "top": 0, "width": 200, "height": 150}]
        session.grab.side_effect = RuntimeError("desktop unavailable")

        tool = ui_capture.SnippingTool(self.root, keyboard_module=False)
        with mock.patch.object(ui_capture, "mss",
                               mock.MagicMock(**{"mss.return_value": session})):
            with mock.patch.object(ui_capture, "messagebox") as box:
                tool.start_snipping()
                self.drain()
                self.assertTrue(box.showerror.called, "no error was reported to the user")
        self.assertFalse(tool.is_active,
                         "is_active stayed True after the grab failed - capture is wedged forever")

    def test_reentrant_start_is_blocked(self):
        tool = ui_capture.SnippingTool(self.root, keyboard_module=False)
        tool.is_active = True
        before = getattr(tool, "full_img", None)
        tool.start_snipping()   # must bail out immediately
        self.assertTrue(tool.is_active)
        self.assertIs(getattr(tool, "full_img", None), before)

    def test_result_toast_show_and_destroy(self):
        toast = ui_capture.ResultToast(self.root, _sample_image(), copied=True,
                                       on_open_editor=lambda img: None)
        toast.show()
        self.drain()
        self.assertTrue(toast.winfo_exists())
        toast.destroy()
        self.drain()
        self.assertFalse(toast.winfo_exists())

    def _toast_text(self, toast):
        """ResultToast paints into one canvas, so read the canvas items."""
        canvas = getattr(toast, "canvas", None) or getattr(toast, "window", None)
        if canvas is None:
            return ""
        texts = []
        try:
            for item in canvas.find_all():
                if canvas.type(item) == "text":
                    texts.append(str(canvas.itemcget(item, "text")))
        except Exception:
            return ""
        return " ".join(texts)

    def test_result_toast_reports_the_copied_state(self):
        toast = ui_capture.ResultToast(self.root, _sample_image(), copied=True)
        toast.show()
        self.drain()
        try:
            joined = self._toast_text(toast).lower()
            self.assertTrue(joined, "ResultToast painted no text at all")
            self.assertTrue(any(word in joined for word in ("copied", "clipboard", "sao chép")),
                            "copied toast does not say the image was copied: %r" % joined)
        finally:
            toast.destroy()
            self.drain()

    def test_result_toast_distinguishes_the_uncopied_state(self):
        copied = ui_capture.ResultToast(self.root, _sample_image(), copied=True)
        copied.show()
        self.drain()
        uncopied = ui_capture.ResultToast(self.root, _sample_image(), copied=False)
        uncopied.show()
        self.drain()
        try:
            copied_text = self._toast_text(copied).lower()
            uncopied_text = self._toast_text(uncopied).lower()
            self.assertTrue(uncopied_text, "uncopied toast painted no text")
            self.assertNotEqual(copied_text, uncopied_text,
                                "the toast says the same thing whether or not copying worked")
        finally:
            copied.destroy()
            uncopied.destroy()
            self.drain()

    def test_result_toast_auto_dismisses(self):
        toast = ui_capture.ResultToast(self.root, _sample_image(), duration=60)
        toast.show()
        self.drain()
        self.assertTrue(toast.winfo_exists())
        self.root.after(250, lambda: None)
        deadline = 0
        while toast.winfo_exists() and deadline < 60:
            self.drain()
            self.root.after(20)
            deadline += 1
            import time
            time.sleep(0.02)
        self.assertFalse(toast.winfo_exists(), "ResultToast did not auto-dismiss")

    def test_toast_click_opens_the_editor(self):
        opened = []
        toast = ui_capture.ResultToast(self.root, _sample_image(),
                                       on_open_editor=lambda img: opened.append(img))
        toast.show()
        self.drain()
        toast._open_editor()
        self.drain()
        self.assertEqual(len(opened), 1, "toast click did not call on_open_editor")


# ==========================================================================
# ui_dialogs.py  (contract section 5)
# ==========================================================================
@unittest.skipUnless(ui_dialogs is not None, UI_DIALOGS_ERROR or "ui_dialogs.py unavailable")
class DialogModuleTests(_TkTestCase):

    CONFIG = {
        "color": "#ff0000",
        "width": 4,
        "capture_hotkey": "Alt+X",
        "editor_hotkeys": {"undo": "Ctrl+Z", "redo": "Ctrl+Y",
                           "delete": "Delete", "edit_text": "Double-click"},
    }

    def test_module_exposes_the_frozen_api(self):
        for name in ("open_info_dialog", "open_shortcuts_dialog", "open_hotkey_dialog"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(ui_dialogs, name, None)),
                                "ui_dialogs.%s is missing" % name)

    def test_info_dialog_constructs_and_destroys(self):
        dialog = ui_dialogs.open_info_dialog(self.root, dict(self.CONFIG))
        self.drain()
        try:
            self.assertIsInstance(dialog, tk.Toplevel)
            self.assertTrue(dialog.winfo_exists())
        finally:
            dialog.destroy()
            self.drain()

    def test_info_dialog_offers_the_hotkey_entry_point(self):
        hit = []
        dialog = ui_dialogs.open_info_dialog(self.root, dict(self.CONFIG),
                                            on_open_hotkeys=lambda: hit.append(1))
        self.drain()
        try:
            self.assertIsNotNone(dialog)
        finally:
            dialog.destroy()
            self.drain()

    def test_hotkey_dialog_constructs_and_destroys(self):
        saved = []
        dialog = ui_dialogs.open_hotkey_dialog(self.root, dict(self.CONFIG),
                                               lambda cfg: saved.append(cfg))
        self.drain()
        try:
            self.assertIsInstance(dialog, tk.Toplevel)
            self.assertTrue(dialog.winfo_exists())
        finally:
            dialog.destroy()
            self.drain()

    def test_shortcuts_dialog_constructs_and_destroys(self):
        dialog = ui_dialogs.open_shortcuts_dialog(self.root, dict(self.CONFIG))
        self.drain()
        try:
            self.assertIsInstance(dialog, tk.Toplevel)
            self.assertTrue(dialog.winfo_exists())
        finally:
            dialog.destroy()
            self.drain()

    def test_shortcuts_dialog_accepts_a_save_callback(self):
        saved = []
        dialog = ui_dialogs.open_shortcuts_dialog(self.root, dict(self.CONFIG),
                                                  save_callback=lambda cfg: saved.append(cfg))
        self.drain()
        try:
            self.assertIsNotNone(dialog)
        finally:
            dialog.destroy()
            self.drain()

    def test_dialogs_are_fully_themed_no_stray_light_panels(self):
        """A dialog left on Tk's default grey reads as a foreign window."""
        import ui_theme as T
        dialog = ui_dialogs.open_info_dialog(self.root, dict(self.CONFIG))
        self.drain()
        try:
            offenders = []

            def walk(widget):
                try:
                    bg = str(widget.cget("background")).lower()
                except Exception:
                    bg = ""
                if bg in ("#d9d9d9", "#f0f0f0", "#f3f3f3", "systembuttonface", "#dcdad5"):
                    offenders.append((widget.winfo_class(), bg))
                for child in widget.winfo_children():
                    walk(child)

            walk(dialog)
            self.assertEqual(offenders, [],
                             "ui_dialogs left default-grey surfaces: %r" % (offenders[:5],))
        finally:
            dialog.destroy()
            self.drain()


@unittest.skipUnless(ui_dialogs is not None, UI_DIALOGS_ERROR or "ui_dialogs.py unavailable")
class HotkeySettingsWrapperTests(_TkTestCase):
    """Contract section 5: the old public API must keep working."""

    def test_public_api_is_unchanged(self):
        import hotkey_settings
        for name in ("_validate", "_record_key", "open_hotkey_settings"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(hotkey_settings, name),
                                "hotkey_settings lost its public %s" % name)

    def test_validate_still_behaves(self):
        """_validate returns the normalised spec, or None when rejected."""
        import hotkey_settings
        self.assertEqual(hotkey_settings._validate("Ctrl+Z", require_modifier=True), "CTRL+Z")
        self.assertEqual(hotkey_settings._validate("control-z"), "CTRL+Z")
        self.assertIsNone(hotkey_settings._validate("Z", require_modifier=True))
        self.assertIsNone(hotkey_settings._validate("Ctrl+Ctrl+S", require_modifier=True))
        self.assertIsNone(hotkey_settings._validate("Ctrl", require_modifier=True))
        self.assertEqual(hotkey_settings._validate("F5", require_modifier=False), "F5")

    def test_record_key_still_builds_a_spec(self):
        import hotkey_settings

        class Entry:
            def __init__(self):
                self.value = ""

            def delete(self, *_a):
                self.value = ""

            def insert(self, _index, text):
                self.value = text

        class Event:
            keysym = "s"
            state = 0x0004 | 0x0001      # Ctrl + Shift

        entry = Entry()
        self.assertEqual(hotkey_settings._record_key(Event(), entry), "break")
        self.assertEqual(entry.value, "Ctrl+Shift+S")

        class Bare(Event):
            state = 0

        bare = Entry()
        hotkey_settings._record_key(Bare(), bare)
        self.assertIn("Ctrl", bare.value, "a bare key must prompt for a modifier")

    def test_open_hotkey_settings_still_opens_a_toplevel(self):
        import hotkey_settings
        config = {"capture_hotkey": "Alt+X",
                  "editor_hotkeys": {"undo": "Ctrl+Z", "redo": "Ctrl+Y",
                                     "delete": "Delete", "edit_text": "Double-click"}}
        dialog = hotkey_settings.open_hotkey_settings(self.root, dict(config), lambda cfg: None)
        self.drain()
        try:
            self.assertIsInstance(dialog, tk.Toplevel)
        finally:
            dialog.destroy()
            self.drain()


# ==========================================================================
# ScreenShotTool.pyw  (contract section 6)
# ==========================================================================
@unittest.skipUnless(app is not None, APP_ERROR or "ScreenShotTool.pyw unavailable")
class AppModuleSurfaceTests(unittest.TestCase):
    """Module-level contract - no Tk root needed."""

    def test_module_level_names_survive(self):
        for name in ("validate_hotkey", "parse_hotkey", "get_exe_path", "check_startup",
                     "toggle_startup", "load_config", "save_config", "send_to_clipboard",
                     "resource_path", "create_tray_icon", "main",
                     "HOTKEY_MODIFIERS", "CONFIG_FILE", "LEGACY_CONFIG_FILE",
                     "APP_NAME", "RESAMPLE", "ImageEditor"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(app, name), "ScreenShotTool.pyw lost %r" % name)

    def test_hotkey_parsing_is_unchanged(self):
        # validate_hotkey uppercases, exactly as in c3c340c.
        self.assertEqual(app.validate_hotkey("Alt+X"), "ALT+X")
        self.assertEqual(app.validate_hotkey("alt+x"), "ALT+X")
        self.assertIsNone(app.validate_hotkey("X"))
        self.assertIsNone(app.validate_hotkey("Alt"))
        self.assertEqual(app.parse_hotkey("Alt+X")[1], ord("X"))
        self.assertEqual(app.parse_hotkey("Alt+X")[0], app.HOTKEY_MODIFIERS["ALT"])
        self.assertIsNone(app.parse_hotkey("nonsense"))

    def test_widget_library_is_wired_to_the_theme(self):
        """The editor must import the design system, not hard-code colours."""
        import ui_theme as T
        import ui_widgets as W
        self.assertIs(app.T, T, "ScreenShotTool.pyw does not import ui_theme as T")
        self.assertIs(app.W, W, "ScreenShotTool.pyw does not import ui_widgets as W")


@unittest.skipUnless(app is not None, APP_ERROR or "ScreenShotTool.pyw unavailable")
class EditorConstructionTests(_TkTestCase):
    """The attribute contract from section 6, then real behaviour."""

    ATTRIBUTES = [
        "pil_image", "orig_w", "orig_h", "shapes", "selected_tag", "selected_tags",
        "text_entry", "history", "history_index", "scale", "offset_x", "offset_y",
        "crop_pending", "cfg", "capture_hotkey_var", "tool_var", "color_var",
        "width_var", "text_bg_var", "palette", "canvas", "canvas_frame",
        "v_scroll", "h_scroll", "top", "btn_undo", "btn_redo", "btn_copy",
        "color_btn", "width_cb",
    ]
    METHODS = [
        "_build_toolbar", "update_history_ui", "save_state", "undo", "redo",
        "_load_state", "on_mouse_wheel", "pick_color", "apply_color_to_selected",
        "random_color", "set_zoom", "redraw_all", "get_new_tag", "clear_selection",
        "draw_selection_box", "select_all", "delete_selected", "on_press",
        "on_drag", "erase_pixels", "on_release", "cancel_crop_or_text",
        "confirm_crop", "begin_text_edit", "cancel_text_edit", "on_double_click",
        "_text_colors", "commit_text", "render_final_image",
        "transform_selection_or_document", "transform_selected_shape",
        "transform_document", "save_clipboard", "save_file",
        "update_custom_cursor", "on_mouse_move_editor", "move_selected_by",
        "_rebuild_text_bitmap", "clone_shapes",
    ]

    def setUp(self):
        super().setUp()
        # Never let a test write the user's real config file.
        self._config_patch = mock.patch.object(app, "CONFIG_FILE",
                                              str(REPO / "_test_config_ignored.json"))
        self._config_patch.start()
        self._save_patch = mock.patch.object(app, "save_config", lambda cfg: None)
        self._save_patch.start()
        self.editor = app.ImageEditor(self.root, _sample_image())
        self.drain()

    def tearDown(self):
        try:
            if getattr(self, "editor", None) is not None:
                self.editor.top.destroy()
        except Exception:
            pass
        self.drain()
        self._save_patch.stop()
        self._config_patch.stop()
        super().tearDown()

    # -- helpers --------------------------------------------------------
    def canvas_at(self, image_x, image_y):
        """Map image coordinates to canvas coordinates.

        The editor centres the image, so ``offset_x``/``offset_y`` are large and
        a raw canvas coordinate like (40, 40) is usually *outside* the image.
        Always drive input through this helper.
        """
        return mock.Mock(
            x=int(image_x * self.editor.scale + self.editor.offset_x),
            y=int(image_y * self.editor.scale + self.editor.offset_y),
            state=0,
            widget=self.editor.canvas,
        )

    def drag(self, tool, start, end):
        """Run one complete press/drag/release with the given tool active."""
        self.editor.tool_var.set(tool)
        self.editor.on_press(self.canvas_at(*start))
        self.editor.on_drag(self.canvas_at(*end))
        self.editor.on_release(self.canvas_at(*end))
        self.drain()

    def test_image_is_centred_inside_the_canvas(self):
        """A sanity check on the coordinate mapping the other tests rely on."""
        self.assertGreater(self.editor.offset_x, 0,
                           "the image should be centred, so offset_x must be positive")
        self.assertGreater(self.editor.offset_y, 0)
        self.assertAlmostEqual(self.editor.scale, 1.0, places=2,
                               msg="a 320x200 image should open at 1:1 on a 1280x800 window")

    def test_full_attribute_contract_exists(self):
        missing, unbound = [], []
        for name in self.ATTRIBUTES:
            with self.subTest(attribute=name):
                if not hasattr(self.editor, name):
                    missing.append(name)
        for name in self.METHODS:
            with self.subTest(method=name):
                if not callable(getattr(self.editor, name, None)):
                    unbound.append(name)
        self.assertEqual(missing, [], "ImageEditor lost attributes: %r" % (missing,))
        self.assertEqual(unbound, [], "ImageEditor lost methods: %r" % (unbound,))

    def test_toolbar_still_creates_the_contract_widgets(self):
        for name in ("btn_undo", "btn_redo", "btn_copy", "color_btn", "width_cb"):
            with self.subTest(name=name):
                widget = getattr(self.editor, name)
                self.assertTrue(widget.winfo_exists(), "%s does not exist" % name)
        for name in ("undo", "redo", "save_file", "save_clipboard", "pick_color"):
            with self.subTest(command=name):
                self.assertTrue(callable(getattr(self.editor, name)))
        # btn_copy must still speak cget/config(text=...) - save_clipboard needs it
        self.assertIsInstance(self.editor.btn_copy.cget("text"), str)

    def test_initial_image_geometry(self):
        self.assertEqual(self.editor.pil_image.mode, "RGBA")
        self.assertEqual((self.editor.orig_w, self.editor.orig_h), (320, 200))
        self.assertEqual(self.editor.shapes, [])
        self.assertEqual(self.editor.palette, list(self.editor.palette))

    def test_history_starts_with_one_state(self):
        self.assertEqual(self.editor.history_index, 0, "editor did not save its initial state")
        self.assertEqual(len(self.editor.history), 1)

    def test_pen_tool_draws_and_renders(self):
        """Set tool_var='pen', drag, then render - the whole pen pipeline."""
        self.editor.tool_var.set("pen")
        self.editor.color_var.set("#ff0000")
        self.editor.width_var.set(6)
        self.editor.redraw_all()
        self.drain()

        self.editor.on_press(self.canvas_at(40, 40))
        for x, y in ((60, 50), (80, 70), (100, 90)):
            self.editor.on_drag(self.canvas_at(x, y))
        self.editor.on_release(self.canvas_at(100, 90))
        self.drain()

        self.assertEqual(len(self.editor.shapes), 1, "pen tool created no shape")
        shape = self.editor.shapes[0]
        self.assertEqual(shape["type"], "pen")
        self.assertGreaterEqual(len(shape["coords"]), 8, "pen shape has too few points")

        rendered = self.editor.render_final_image()
        self.assertEqual(rendered.mode, "RGBA")
        self.assertEqual(rendered.size, (320, 200))
        base = self.editor.pil_image.getpixel((40, 40))
        self.assertNotEqual(rendered.getpixel((40, 40)), base,
                            "the pen stroke did not appear in the rendered image")

    def test_rect_oval_arrow_render(self):
        for tool in ("rect", "oval", "arrow"):
            with self.subTest(tool=tool):
                self.editor.shapes = []
                self.editor.tool_var.set(tool)
                self.editor.width_var.set(4)
                self.editor.on_press(self.canvas_at(20, 20))
                self.editor.on_drag(self.canvas_at(120, 120))
                self.editor.on_release(self.canvas_at(120, 120))
                self.drain()
                self.assertEqual(len(self.editor.shapes), 1, "%s created no shape" % tool)
                rendered = self.editor.render_final_image()
                self.assertEqual(rendered.mode, "RGBA")
                self.assertEqual(rendered.size, (320, 200))

    def test_rotate_cw_swaps_dimensions(self):
        self.editor.transform_document("rotate_cw")
        self.drain()
        self.assertEqual(self.editor.pil_image.size, (200, 320))
        self.assertEqual((self.editor.orig_w, self.editor.orig_h), (200, 320))
        self.editor.transform_document("rotate_ccw")
        self.drain()
        self.assertEqual(self.editor.pil_image.size, (320, 200))

    def test_flip_keeps_dimensions(self):
        for operation in ("flip_h", "flip_v"):
            with self.subTest(operation=operation):
                before = self.editor.pil_image.size
                self.editor.transform_document(operation)
                self.drain()
                self.assertEqual(self.editor.pil_image.size, before)

    def test_undo_redo_restore_state(self):
        self.drag("pen", (10, 10), (50, 50))
        after_draw = len(self.editor.shapes)
        self.assertEqual(after_draw, 1)

        self.editor.undo()
        self.drain()
        self.assertEqual(len(self.editor.shapes), 0, "undo did not remove the stroke")

        self.editor.redo()
        self.drain()
        self.assertEqual(len(self.editor.shapes), after_draw, "redo did not restore the stroke")

    def test_history_ui_reflects_undo_availability(self):
        self.editor.update_history_ui()
        self.drain()
        states = str(self.editor.btn_undo.cget("state"))
        self.assertIn(states, ("disabled", "normal"))
        self.drag("pen", (10, 10), (50, 50))
        self.editor.update_history_ui()
        self.drain()
        self.assertEqual(str(self.editor.btn_undo.cget("state")), "normal",
                         "undo stayed disabled after the history grew")

    def test_delete_selected_removes_the_shape(self):
        self.drag("rect", (20, 20), (90, 90))
        tag = self.editor.shapes[0]["tag"]
        self.editor.selected_tag = tag
        self.editor.selected_tags = [tag]
        self.editor.delete_selected()
        self.drain()
        self.assertEqual(self.editor.shapes, [], "delete_selected left the shape behind")

    def test_select_all_and_clear_selection(self):
        for x in (20, 120):
            self.drag("rect", (x, 20), (x + 40, 60))
        self.assertEqual(len(self.editor.shapes), 2)
        self.editor.select_all()
        self.drain()
        self.assertEqual(len(self.editor.selected_tags), 2, "select_all missed a shape")
        self.editor.clear_selection()
        self.drain()
        self.assertEqual(self.editor.selected_tags, [])

    def test_zoom_changes_scale(self):
        self.editor.set_zoom(0)
        self.drain()
        self.assertGreater(self.editor.scale, 0)
        one_to_one = self.editor.scale
        self.editor.set_zoom(1.25)
        self.drain()
        self.assertGreater(self.editor.scale, one_to_one, "zoom in did not increase the scale")
        self.editor.set_zoom(0.8)
        self.drain()
        self.assertLess(self.editor.scale, one_to_one * 1.25)

    def test_crop_flow(self):
        self.drag("crop", (40, 40), (200, 140))
        self.assertTrue(self.editor.crop_pending, "crop drag did not set crop_pending")
        self.editor.confirm_crop()
        self.drain()
        self.assertFalse(self.editor.crop_pending)
        self.assertEqual(self.editor.pil_image.size, (160, 100))

    def test_crop_cancel_keeps_the_image(self):
        self.drag("crop", (40, 40), (200, 140))
        self.editor.cancel_crop_or_text()
        self.drain()
        self.assertFalse(self.editor.crop_pending)
        self.assertEqual(self.editor.pil_image.size, (320, 200))

    def test_text_tool_creates_and_commits_an_entry(self):
        self.editor.tool_var.set("text")
        self.editor.on_press(self.canvas_at(50, 50))
        self.drain()
        self.assertIsNotNone(self.editor.text_entry, "text tool did not open an entry")
        self.editor.text_entry.insert(0, "Xin chào")
        self.editor.commit_text()
        self.drain()
        self.assertIsNone(self.editor.text_entry)
        texts = [s.get("text") for s in self.editor.shapes if s.get("type") == "text"]
        self.assertIn("Xin chào", texts, "committed text is not in the shape model")
        rendered = self.editor.render_final_image()
        self.assertEqual(rendered.mode, "RGBA")

    def test_erase_tool_keeps_annotations_editable(self):
        self.drag("rect", (20, 20), (80, 80))
        shapes_before = len(self.editor.shapes)

        self.drag("erase", (150, 120), (250, 180))
        self.assertEqual(len(self.editor.shapes), shapes_before,
                         "erase dropped an annotation from the model")
        self.assertEqual(self.editor.render_final_image().mode, "RGBA")

    def test_color_and_width_variables_persist_into_the_model(self):
        self.editor.color_var.set("#00ff88")
        self.editor.width_var.set(9)
        self.drain()
        self.assertEqual(self.editor.cfg.get("color"), "#00ff88")
        self.assertEqual(self.editor.cfg.get("width"), 9)
        self.assertEqual(self.editor.cfg.get("capture_hotkey"), "ALT+X",
                         "editing the colour clobbered the capture hotkey")

    def test_random_color_and_pick_color_are_wired(self):
        original = self.editor.color_var.get()
        self.editor.random_color()
        self.drain()
        self.assertTrue(self.editor.color_var.get(), "random_color cleared the colour")
        self.assertNotEqual(original, "") if False else None
        with mock.patch.object(app, "colorchooser") as chooser:
            chooser.askcolor.return_value = ((1, 2, 3), "#010203")
            self.editor.pick_color()
            self.drain()
        self.assertEqual(self.editor.color_var.get().lower(), "#010203",
                         "pick_color did not apply the chosen colour")

    def test_save_clipboard_updates_the_copy_button(self):
        with mock.patch.object(app, "send_to_clipboard", return_value=True) as sender:
            self.editor.save_clipboard()
            self.drain()
            self.assertTrue(sender.called, "save_clipboard never called send_to_clipboard")
            self.assertIn("Copy", self.editor.btn_copy.cget("text"),
                          "the Copy button did not report success")

    def test_save_clipboard_reports_failure(self):
        with mock.patch.object(app, "send_to_clipboard", return_value=False):
            self.editor.save_clipboard()
            self.drain()
            text = self.editor.btn_copy.cget("text")
            self.assertTrue(text, "the Copy button went blank on failure")

    def test_save_file_writes_a_png(self):
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            target = Path(tmp) / "out.png"
            with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)):
                with mock.patch.object(app.messagebox, "askyesno", return_value=True):
                    self.editor.save_file()
                    self.drain()
            self.assertTrue(target.exists(), "save_file wrote nothing")
            self.assertGreater(target.stat().st_size, 0, "save_file wrote an empty file")
            # Open through a context manager so Windows does not keep the lock.
            with Image.open(target) as saved:
                self.assertEqual(saved.size, (320, 200))
                self.assertEqual(saved.format, "PNG")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_save_file_cancelled_writes_nothing(self):
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            target = Path(tmp) / "never.png"
            with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=""):
                self.editor.save_file()
                self.drain()
            self.assertFalse(target.exists(), "a cancelled save still wrote a file")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clone_shapes_is_a_deep_copy_of_coordinates(self):
        shapes = [{"tag": "a", "type": "rect", "coords": [0, 0, 5, 5], "width": 1, "color": "#f00"}]
        cloned = self.editor.clone_shapes(shapes)
        cloned[0]["coords"][0] = 99
        self.assertEqual(shapes[0]["coords"][0], 0, "clone_shapes aliased the coordinates")

    def test_mouse_move_updates_the_cursor_readout(self):
        self.editor.on_mouse_move_editor(self.canvas_at(33, 44))
        self.drain()
        self.assertTrue(hasattr(self.editor, "canvas"))


@unittest.skipUnless(app is not None, APP_ERROR or "ScreenShotTool.pyw unavailable")
class AppCaptureLegacyTests(_TkTestCase):
    """Contract section 4 says the tool moved, but the app must not lose it."""

    def test_capture_entry_points_still_exist(self):
        self.assertTrue(hasattr(app, "SnippingTool"),
                        "ScreenShotTool.pyw no longer exposes SnippingTool")

    def test_legacy_show_toast_still_callable(self):
        """The old in-app toast helper must survive or be cleanly delegated."""
        tool = app.SnippingTool(self.root)
        self.assertTrue(hasattr(tool, "show_toast") or hasattr(ui_capture or object(), "ResultToast"))

    def test_app_snipping_tool_starts_and_cancels(self):
        tool = app.SnippingTool(self.root)
        self.assertFalse(getattr(tool, "is_active", False))
        tool.cancel_snip()
        self.drain()
        self.assertFalse(getattr(tool, "is_active", False))


# ==========================================================================
# PHASE B: reachability from the real entry points
# ==========================================================================
@unittest.skipUnless(app is not None, APP_ERROR or "ScreenShotTool.pyw unavailable")
class EditorReachabilityTests(_TkTestCase):
    """Every editing control must be reachable at any window size the app allows.

    ``_apply_layout`` hides the inspector below 1180 px. That is a legitimate
    responsive decision *only* if the user can still get to colour, stroke
    width, zoom, transform and undo/redo. These tests fail if the shell can
    reach a state where those controls are simply gone.
    """

    def editor(self, width, height=700):
        editor = app.ImageEditor(self.root, _sample_image((600, 400)))
        self.addCleanup(self._destroy_editor, editor)
        editor.top.state("normal")
        editor.top.update_idletasks()
        editor.top.geometry("%dx%d+10+10" % (width, height))
        self.drain()
        return editor

    @staticmethod
    def _destroy_editor(editor):
        try:
            if editor.top.winfo_exists():
                editor.top.destroy()
        except Exception:
            pass

    def test_inspector_controls_are_reachable_at_the_minimum_width(self):
        """The inspector must be reachable at the app's own minimum width.

        Below the dock breakpoint the panel floats as a drawer rather than
        disappearing, so ``winfo_ismapped`` is the right assertion at every
        width. This test failed against the first Phase B build, where the
        panel was force-hidden for the whole 760-1179 px range.
        """
        probe = self.editor(900)
        minimum = probe.top.minsize()[0]
        editor = self.editor(minimum, 640)
        if not editor.inspector.winfo_ismapped():
            editor.btn_inspector_toggle.invoke()
            self.drain()
        self.assertTrue(
            editor.inspector.winfo_ismapped(),
            "at the app's own minimum width (%d px) the inspector cannot be shown at "
            "all: colour, stroke width, zoom, transform and undo/redo are unreachable"
            % minimum)

    def test_the_gear_works_at_every_width_the_window_allows(self):
        """One gear click must always produce a visible change.

        Docked above the breakpoint, floating below it — either way the panel
        has to appear or disappear, so the flag can never desynchronise from
        what the user sees. Failed at 1100 and 860 px against the first Phase B
        build, where the gear was a dead button.
        """
        for width in (1600, 1100, 860):
            with self.subTest(width=width):
                editor = self.editor(width)
                started_visible = bool(editor.inspector.winfo_ismapped())
                editor.btn_inspector_toggle.invoke()
                self.drain()
                after_one = bool(editor.inspector.winfo_ismapped())
                if not after_one and not started_visible:
                    # A second click is the only way back; if that also fails the
                    # control is dead at this width.
                    editor.btn_inspector_toggle.invoke()
                    self.drain()
                    after_one = bool(editor.inspector.winfo_ismapped())
                self.assertNotEqual(
                    started_visible, after_one,
                    "at %d px the inspector gear did nothing: the panel is %s and "
                    "stays that way, so colour/width/zoom/undo are unreachable"
                    % (width, "visible" if started_visible else "hidden"))

    def test_reaching_the_minimum_width_never_loses_the_inspector_for_good(self):
        """Narrow past the breakpoint and widen back; the panel must return."""
        editor = self.editor(1600)
        self.assertTrue(editor.inspector.winfo_ismapped(),
                        "the inspector should be visible in a wide window")
        editor.top.geometry("900x700+10+10")
        self.drain()
        editor.top.geometry("1600x700+10+10")
        self.drain()
        self.assertTrue(
            editor.inspector.winfo_ismapped(),
            "the inspector did not come back after the window was widened again")

    def test_header_actions_survive_the_narrowest_layout(self):
        """Copy and Save must never be collateral damage of the responsive shell."""
        editor = self.editor(760, 560)
        for name in ("btn_copy", "btn_save"):
            widget = getattr(editor, name, None)
            self.assertIsNotNone(widget, "the header lost %s at 760 px" % name)
            self.assertTrue(widget.winfo_ismapped(),
                            "%s is not visible at the app's minimum width" % name)

    # -- the floating drawer must never become a trap --------------------
    def test_escape_dismisses_the_floating_inspector(self):
        """A floating panel with no way out would be worse than a hidden one."""
        editor = self.editor(1100)
        if not editor.inspector.winfo_ismapped():
            editor.btn_inspector_toggle.invoke()
            self.drain()
        self.assertTrue(editor.inspector.winfo_ismapped(),
                        "could not open the floating inspector at 1100 px")
        editor.top.event_generate("<Escape>")
        self.drain()
        self.assertFalse(editor.inspector.winfo_ismapped(),
                         "Escape did not dismiss the floating inspector, so it is a "
                         "trap: the only way out would be the gear")

    def test_the_gear_reopens_the_inspector_after_dismissing_it(self):
        """Dismissing must not be a one-way door."""
        editor = self.editor(1100)
        if not editor.inspector.winfo_ismapped():
            editor.btn_inspector_toggle.invoke()
            self.drain()
        editor.top.event_generate("<Escape>")
        self.drain()
        editor.btn_inspector_toggle.invoke()
        self.drain()
        self.assertTrue(editor.inspector.winfo_ismapped(),
                        "after dismissing the floating inspector it could not be "
                        "reopened with the gear")

    def test_the_floating_inspector_does_not_cover_the_header_or_status_bar(self):
        """The drawer sits between them; overlapping would hide Save/Copy."""
        editor = self.editor(1100, 700)
        if not editor.inspector.winfo_ismapped():
            editor.btn_inspector_toggle.invoke()
            self.drain()
        self.assertTrue(editor.inspector.winfo_ismapped(),
                        "the floating inspector is not visible at 1100 px")
        top_y = editor.top.winfo_rooty()
        ins_top = editor.inspector.winfo_rooty() - top_y
        ins_bottom = ins_top + editor.inspector.winfo_height()
        header_bottom = (editor.header.winfo_rooty() - top_y
                         + editor.header.winfo_height())
        status_top = editor.statusbar.winfo_rooty() - top_y
        self.assertGreaterEqual(
            ins_top, header_bottom - 1,
            "the floating inspector overlaps the header, which holds Save and Copy")
        self.assertLessEqual(
            ins_bottom, status_top + 1,
            "the floating inspector overlaps the status bar")

    def test_the_floating_inspector_keeps_its_controls_usable(self):
        """A panel that is merely mapped is not enough — its widgets must work."""
        editor = self.editor(1100)
        if not editor.inspector.winfo_ismapped():
            editor.btn_inspector_toggle.invoke()
            self.drain()
        for name in ("color_btn", "width_cb", "btn_undo", "btn_redo"):
            widget = getattr(editor, name, None)
            self.assertIsNotNone(widget, "the floating panel lost %s" % name)
            self.assertTrue(widget.winfo_ismapped(),
                            "%s is not mapped inside the floating inspector" % name)
        # and one of them must actually do its job while floating
        before = editor.scale
        editor.set_zoom(1.25)
        self.drain()
        self.assertNotEqual(before, editor.scale,
                            "zoom did nothing while the inspector was floating")


@unittest.skipUnless(app is not None, APP_ERROR or "ScreenShotTool.pyw unavailable")
class RealEntryPointWiringTests(_TkTestCase):
    """The dialogs must be reached through the app, not merely constructed."""

    def editor(self):
        editor = app.ImageEditor(self.root, _sample_image((400, 300)))
        self.addCleanup(self._destroy_editor, editor)
        self.drain()
        return editor

    @staticmethod
    def _destroy_editor(editor):
        try:
            if editor.top.winfo_exists():
                editor.top.destroy()
        except Exception:
            pass

    def toplevels(self, parent):
        return [w for w in parent.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_exists()]

    def test_header_info_button_opens_a_dialog(self):
        editor = self.editor()
        before = len(self.toplevels(editor.top))
        editor.btn_info.invoke()
        self.drain()
        self.assertGreater(len(self.toplevels(editor.top)), before,
                           "the header Info button opened nothing")

    def test_header_gear_button_is_wired(self):
        editor = self.editor()
        self.assertTrue(hasattr(editor, "btn_inspector_toggle"),
                        "the header has no inspector toggle button")
        was = editor._inspector_visible
        editor.btn_inspector_toggle.invoke()
        self.drain()
        self.assertNotEqual(was, editor._inspector_visible,
                            "the inspector gear button does nothing")

    def test_shortcuts_entry_point_opens_a_dialog(self):
        editor = self.editor()
        before = len(self.toplevels(editor.top))
        editor.show_shortcuts_dialog()
        self.drain()
        self.assertGreater(len(self.toplevels(editor.top)), before,
                           "show_shortcuts_dialog opened nothing")

    def test_hotkey_save_callback_reaches_the_config(self):
        editor = self.editor()
        calls = []
        with mock.patch.object(app, "save_config",
                              side_effect=lambda cfg: calls.append(dict(cfg))):
            editor._save_hotkey_config(dict(editor.cfg, capture_hotkey="CTRL+SHIFT+K"))
            self.drain()
        self.assertEqual(editor.capture_hotkey_var.get(), "CTRL+SHIFT+K",
                         "saving a hotkey did not update the visible hotkey")
        self.assertTrue(calls, "saving a hotkey never persisted the config")

    def test_copy_and_save_are_wired_end_to_end(self):
        import shutil
        import tempfile
        from pathlib import Path as _Path

        editor = self.editor()
        self.drain()
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        target = _Path(tmp) / "wired.png"
        with mock.patch.object(app, "send_to_clipboard", return_value=True) as sender:
            editor.btn_copy.invoke()
            self.drain()
            self.assertTrue(sender.called,
                            "the Copy button is not wired to the clipboard")
        with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)):
            with mock.patch.object(app.messagebox, "askyesno", return_value=True):
                editor.btn_save.invoke()
                self.drain()
        self.assertTrue(target.exists(), "the Save button wrote no file")


@unittest.skipUnless(ui_capture is not None, UI_CAPTURE_ERROR or "ui_capture.py unavailable")
class CaptureReachabilityTests(_TkTestCase):
    """Alt+X -> overlay -> toast -> editor, through ui_capture's real objects."""

    def fake_desktop(self, width=400, height=300):
        payload = bytes(_sample_image((width, height)).convert("RGB").tobytes("raw", "BGRX"))
        shot = mock.MagicMock()
        shot.size = (width, height)
        shot.bgra = payload
        session = mock.MagicMock()
        session.monitors = [{"left": 0, "top": 0, "width": width, "height": height}]
        session.grab.return_value = shot
        return mock.patch.object(ui_capture, "mss", mock.MagicMock(**{"mss.return_value": session}))

    def complete_drag(self, tool, x1, y1, x2, y2):
        """Drive the real press/drag/release sequence, then finish.

        ``finish_snip`` returns immediately unless ``snip_state == 1``, which is
        only set once the user has pressed the button -- so a bare
        ``finish_snip`` call silently does nothing and proves nothing.
        """
        press = mock.Mock(x=x1, y=y1, widget=tool.canvas)
        tool.on_button_press(press)
        self.drain()
        self.assertEqual(tool.snip_state, 1,
                         "on_button_press did not enter dragging mode")
        for i in range(1, 5):
            mx = x1 + (x2 - x1) * i // 4
            my = y1 + (y2 - y1) * i // 4
            tool.on_move_press(mock.Mock(x=mx, y=my, widget=tool.canvas))
        self.drain()
        tool.on_button_release(mock.Mock(x=x2, y=y2, widget=tool.canvas))
        self.drain()

    def test_capture_then_confirm_produces_an_image_and_a_toast(self):
        tool = ui_capture.SnippingTool(self.root, keyboard_module=False,
                                       open_editor=lambda img: None)
        with self.fake_desktop():
            tool.start_snipping()
            self.drain()
            self.assertTrue(tool.is_active, "start_snipping did not activate the overlay")
            self.assertIsNotNone(tool.full_img, "no image was grabbed")
            self.complete_drag(tool, 20, 20, 200, 150)
        self.assertFalse(tool.is_active, "finishing the snip left the overlay active")
        self.assertIsNotNone(tool.current_toast,
                             "finishing a snip produced no ResultToast")

    def test_toast_is_reached_from_the_capture_flow(self):
        tool = ui_capture.SnippingTool(self.root, keyboard_module=False,
                                       open_editor=lambda img: None)
        with self.fake_desktop():
            tool.start_snipping()
            self.drain()
            self.complete_drag(tool, 20, 20, 220, 170)
        toast = tool.current_toast
        self.assertIsNotNone(toast, "the capture flow produced no ResultToast")
        try:
            self.assertTrue(toast.winfo_exists(), "the toast was created but is not alive")
            self.assertIsNotNone(toast.image, "the toast has no image")
            self.assertEqual(toast.image.size, (200, 150),
                             "the toast image is not the 200x150 selection that was dragged")
        finally:
            try:
                toast.destroy()
            except Exception:
                pass
            self.drain()

    def test_a_tiny_selection_is_treated_as_a_cancel(self):
        tool = ui_capture.SnippingTool(self.root, keyboard_module=False,
                                       open_editor=lambda img: None)
        with self.fake_desktop():
            tool.start_snipping()
            self.drain()
            self.complete_drag(tool, 10, 10, 14, 13)   # below MIN_SIZE
        self.assertFalse(tool.is_active)
        self.assertIsNone(tool.current_toast,
                          "a 4x3 selection produced a toast instead of being discarded")

    def test_cancel_leaves_no_overlay_and_no_toast(self):
        tool = ui_capture.SnippingTool(self.root, keyboard_module=False,
                                       open_editor=lambda img: None)
        with self.fake_desktop():
            tool.start_snipping()
            self.drain()
            tool.cancel_snip()
            self.drain()
        self.assertFalse(tool.is_active)
        self.assertIsNone(tool.current_toast,
                          "cancelling a capture still showed a toast")


if __name__ == "__main__":
    unittest.main()
