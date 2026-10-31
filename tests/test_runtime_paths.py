"""Tests for the pieces the UI tests never reach.

Two gaps motivated this file:

* the tray/main path was only ever exercised by launching the app by hand, so a
  regression there would ship unnoticed;
* the error branches (clipboard locked, unreadable config, missing icon) only run
  when something goes wrong, which is exactly when nobody is watching.

Nothing here starts a real tray icon or grabs the real screen: the Win32 and
pystray calls are replaced at the boundary, and the assertions are about our
own logic deciding what to do.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import importlib.util

spec = importlib.util.spec_from_file_location("app", REPO / "ScreenShotTool.pyw")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

from PIL import Image


class HotkeyParsingTests(unittest.TestCase):
    """validate_hotkey/parse_hotkey are the gate in front of RegisterHotKey."""

    def test_normalises_case_and_separators(self):
        self.assertEqual(app.validate_hotkey("alt+x"), "ALT+X")
        self.assertEqual(app.validate_hotkey("Alt-x"), "ALT+X")
        self.assertEqual(app.validate_hotkey("  ctrl + shift + s "), "CTRL+SHIFT+S")

    def test_aliases_are_folded(self):
        self.assertEqual(app.validate_hotkey("Control+Z"), "CTRL+Z")
        self.assertEqual(app.validate_hotkey("Escape"), None)  # modifier-less

    def test_rejects_bare_modifier_and_bare_key(self):
        # A single modifier or a lone letter would swallow ordinary typing.
        self.assertIsNone(app.validate_hotkey("ALT"))
        self.assertIsNone(app.validate_hotkey("X"))
        self.assertIsNone(app.validate_hotkey(""))

    def test_rejects_duplicate_modifiers(self):
        self.assertIsNone(app.validate_hotkey("ALT+ALT+X"))

    def test_rejects_unknown_key_names(self):
        self.assertIsNone(app.validate_hotkey("ALT+NONSENSE"))

    def test_rejects_non_strings(self):
        for value in (None, 5, [], {}):
            self.assertIsNone(app.validate_hotkey(value))

    def test_parse_produces_win32_masks(self):
        modifiers, vk = app.parse_hotkey("ALT+X")
        self.assertEqual(modifiers, app.HOTKEY_MODIFIERS["ALT"])
        self.assertEqual(vk, ord("X"))

    def test_parse_combines_modifiers(self):
        modifiers, vk = app.parse_hotkey("CTRL+SHIFT+S")
        self.assertEqual(modifiers,
                         app.HOTKEY_MODIFIERS["CTRL"] | app.HOTKEY_MODIFIERS["SHIFT"])
        self.assertEqual(vk, ord("S"))

    def test_parse_named_keys(self):
        self.assertEqual(app.parse_hotkey("ALT+DELETE")[1], 0x2E)
        self.assertEqual(app.parse_hotkey("ALT+ESC")[1], 0x1B)
        self.assertEqual(app.parse_hotkey("ALT+SPACE")[1], 0x20)
        self.assertEqual(app.parse_hotkey("ALT+ENTER")[1], 0x0D)

    def test_parse_function_keys(self):
        self.assertEqual(app.parse_hotkey("CTRL+F1")[1], 0x70)
        self.assertEqual(app.parse_hotkey("CTRL+F12")[1], 0x7B)

    def test_parse_tooltip_label_round_trip(self):
        # The warning shown to the user is built from the same numbers.
        label = app._hotkey_label(app.HOTKEY_MODIFIERS["ALT"], ord("X"))
        self.assertEqual(label, "Alt+X")
        label = app._hotkey_label(
            app.HOTKEY_MODIFIERS["CTRL"] | app.HOTKEY_MODIFIERS["SHIFT"], 0x70)
        self.assertEqual(label, "Ctrl+Shift+F1")


class VersionTests(unittest.TestCase):
    def test_version_is_a_three_part_string(self):
        parts = app.APP_VERSION.split(".")
        self.assertEqual(len(parts), 3, "APP_VERSION must be MAJOR.MINOR.PATCH")
        for part in parts:
            self.assertTrue(part.isdigit(), "non-numeric version part: %r" % part)


class ConfigLocationTests(unittest.TestCase):
    """The config must land somewhere writable, and old locations must be read."""

    def test_prefers_appdata_when_no_portable_config_exists(self):
        with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\someone\AppData\Roaming"}):
            with mock.patch.object(app.os.path, "exists", return_value=False):
                self.assertEqual(app._config_dir(),
                                 os.path.join(r"C:\Users\someone\AppData\Roaming", app.APP_NAME))

    def test_portable_config_beside_the_exe_wins(self):
        with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\someone\AppData\Roaming"}):
            with mock.patch.object(app.os.path, "exists", return_value=True):
                self.assertEqual(app._config_dir(), app.APP_DIR)

    def test_falls_back_to_app_dir_without_appdata(self):
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(app.os.path, "exists", return_value=False):
                self.assertEqual(app._config_dir(), app.APP_DIR)


class LoadConfigErrorPathTests(unittest.TestCase):
    """load_config must survive anything the file can contain."""

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tempdir, "cfg.json")
        self.patches = [
            mock.patch.object(app, "CONFIG_FILE", self.path),
            mock.patch.object(app, "LEGACY_CONFIG_FILE", self.path + ".none"),
            mock.patch.object(app, "LEGACY_CONFIG_FILE_APP_DIR", self.path + ".none2"),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rmdir(self.tempdir)

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_missing_file_yields_defaults(self):
        config = app.load_config()
        self.assertEqual(config["color"], "#ff0000")
        self.assertEqual(config["width"], 4)

    def test_truncated_json_yields_defaults(self):
        self.write('{"color": "#123456", "widt')
        self.assertEqual(app.load_config()["color"], "#ff0000")

    def test_non_json_garbage_yields_defaults(self):
        self.write("not json at all")
        self.assertEqual(app.load_config()["color"], "#ff0000")

    def test_wrong_types_fall_back_field_by_field(self):
        self.write(json.dumps({"color": 123, "width": "wide", "capture_hotkey": 5,
                               "editor_hotkeys": "nope"}))
        config = app.load_config()
        self.assertEqual(config["color"], "#ff0000")
        self.assertEqual(config["width"], 4)
        self.assertEqual(config["capture_hotkey"], "Alt+X")
        self.assertIsInstance(config["editor_hotkeys"], dict)

    def test_width_is_clamped(self):
        self.write(json.dumps({"width": 9999}))
        self.assertEqual(app.load_config()["width"], 50)
        self.write(json.dumps({"width": -5}))
        self.assertEqual(app.load_config()["width"], 1)

    def test_invalid_hotkey_falls_back(self):
        self.write(json.dumps({"capture_hotkey": "ALT"}))
        self.assertEqual(app.load_config()["capture_hotkey"], "Alt+X")

    def test_empty_object_yields_defaults(self):
        self.write("{}")
        self.assertEqual(app.load_config()["color"], "#ff0000")


class SaveConfigTests(unittest.TestCase):
    """save_config must be atomic and must report failure instead of hiding it."""

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tempdir, "nested", "cfg.json")
        self.patch = mock.patch.object(app, "CONFIG_FILE", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for root, dirs, files in os.walk(self.tempdir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tempdir)

    def test_creates_missing_directory_and_writes(self):
        app.save_config({"color": "#abcdef", "width": 3})
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["color"], "#abcdef")

    def test_leaves_no_temp_file_behind(self):
        app.save_config({"color": "#abcdef", "width": 3})
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_failed_write_is_logged_not_raised(self):
        # An unwritable target must not crash the app or kill the UI thread.
        with mock.patch.object(app.os, "replace", side_effect=PermissionError("denied")):
            with self.assertLogs(level="WARNING") as captured:
                app.save_config({"color": "#abcdef", "width": 3})
        self.assertTrue(any("Could not save config" in line for line in captured.output))

    def test_failed_write_cleans_up_its_temp_file(self):
        with mock.patch.object(app.os, "replace", side_effect=PermissionError("denied")):
            app.save_config({"color": "#abcdef", "width": 3})
        self.assertFalse(os.path.exists(self.path + ".tmp"),
                         "a failed save must not leave a stale .tmp behind")


class StartupRegistryTests(unittest.TestCase):
    """check_startup must never raise into the tray menu."""

    def test_missing_registry_value_reads_as_not_enabled(self):
        with mock.patch.object(app.winreg, "OpenKey", side_effect=FileNotFoundError):
            self.assertFalse(app.check_startup())

    def test_wrong_path_reads_as_not_enabled(self):
        key = mock.MagicMock()
        with mock.patch.object(app.winreg, "OpenKey", return_value=key), \
                mock.patch.object(app.winreg, "QueryValueEx", return_value=(r'"C:\other.exe"', 1)), \
                mock.patch.object(app.winreg, "CloseKey"):
            self.assertFalse(app.check_startup())

    def test_matching_path_reads_as_enabled(self):
        key = mock.MagicMock()
        with mock.patch.object(app.winreg, "OpenKey", return_value=key), \
                mock.patch.object(app.winreg, "QueryValueEx",
                                  return_value=('"%s"' % app.get_exe_path(), 1)), \
                mock.patch.object(app.winreg, "CloseKey"):
            self.assertTrue(app.check_startup())


class ResourcePathTests(unittest.TestCase):
    def test_returns_a_path_that_exists_after_freeze(self):
        with mock.patch.object(sys, "_MEIPASS", tempfile.gettempdir(), create=True):
            self.assertEqual(app.resource_path("icon.ico"),
                             os.path.join(tempfile.gettempdir(), "icon.ico"))

    def test_falls_back_to_the_module_directory(self):
        self.assertEqual(app.resource_path("icon.ico"),
                         os.path.join(app.APP_DIR, "icon.ico"))


class ClipboardFailureTests(unittest.TestCase):
    """A locked clipboard must be reported, not swallowed silently."""

    def test_lock_contention_is_retried_then_reported(self):
        image = Image.new("RGB", (8, 8), "red")
        with mock.patch.object(app.win32clipboard, "OpenClipboard",
                               side_effect=Exception("clipboard busy")):
            with mock.patch.object(app.time, "sleep", return_value=None):
                with self.assertLogs(level="WARNING") as captured:
                    result = app.send_to_clipboard(image)
        self.assertFalse(result, "a clipboard failure must report False")
        self.assertTrue(any("Clipboard" in line for line in captured.output))

    def test_successful_publish_returns_true(self):
        image = Image.new("RGB", (8, 8), "red")
        with mock.patch.object(app.win32clipboard, "OpenClipboard", return_value=None), \
                mock.patch.object(app.win32clipboard, "EmptyClipboard", return_value=None), \
                mock.patch.object(app.win32clipboard, "SetClipboardData", return_value=None), \
                mock.patch.object(app.win32clipboard, "CloseClipboard", return_value=None):
            self.assertTrue(app.send_to_clipboard(image))


class TrayIconFallbackTests(unittest.TestCase):
    """create_tray_icon must survive a missing .ico file."""

    def test_missing_icon_falls_back_to_a_drawn_image(self):
        with mock.patch.object(app, "resource_path",
                               return_value=os.path.join(app.APP_DIR, "does_not_exist.ico")):
            image = app.create_tray_icon()
        self.assertEqual(image.size, (64, 64))

    def test_present_icon_is_loaded(self):
        icon_path = os.path.join(app.APP_DIR, "icon_ScreenShotTool.ico")
        if not os.path.exists(icon_path):
            self.skipTest("no icon file in the repo")
        image = app.create_tray_icon()
        self.assertGreater(image.size[0], 0)


class HotkeyWarningTests(unittest.TestCase):
    """The user must learn that their hotkey did not take - once, not per tick."""

    def setUp(self):
        app._warned_hotkeys.clear()
        self.addCleanup(app._warned_hotkeys.clear)

    def test_warns_only_once_per_combination(self):
        icon = mock.MagicMock()
        with mock.patch.object(app, "_tray_icon_ref", icon):
            app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["ALT"], ord("X"))
            app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["ALT"], ord("X"))
        self.assertEqual(icon.notify.call_count, 1,
                         "the listener loops every 100 ms; it must not nag")

    def test_different_combinations_each_warn(self):
        icon = mock.MagicMock()
        with mock.patch.object(app, "_tray_icon_ref", icon):
            app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["ALT"], ord("X"))
            app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["CTRL"], ord("X"))
        self.assertEqual(icon.notify.call_count, 2)

    def test_survives_a_tray_that_cannot_notify(self):
        icon = mock.MagicMock()
        icon.notify.side_effect = Exception("no shell")
        with mock.patch.object(app, "_tray_icon_ref", icon):
            with self.assertLogs(level="WARNING") as captured:
                app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["ALT"], ord("X"))
        self.assertTrue(any("unavailable" in line for line in captured.output))

    def test_survives_having_no_tray_icon_yet(self):
        # The listener starts before the icon exists.
        with mock.patch.object(app, "_tray_icon_ref", None):
            with self.assertLogs(level="WARNING"):
                app._warn_hotkey_unavailable(app.HOTKEY_MODIFIERS["ALT"], ord("X"))


if __name__ == "__main__":
    unittest.main()
