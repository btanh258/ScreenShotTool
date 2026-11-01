"""Regression tests for the three faults reported after v1.2.0.

1. The tray menu crashed on open, which is why every menu item appeared dead.
2. "Gioi thieu" did nothing: it called a method the capture tool does not have.
3. "Kiem tra cap nhat" blamed the network for a 404, which is what GitHub
   returns for a private repository.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_updates


def _app():
    spec = importlib.util.spec_from_file_location(
        "sst_app_regressions", ROOT / "ScreenShotTool.pyw")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TrayMenuCallbackTests(unittest.TestCase):
    """pystray rejects actions taking more than two arguments.

    It measures co_argcount, and a default parameter still counts, so the
    original `lambda icon, menu_item, p=path:` was a 3-argument callable and
    pystray raised ValueError while building the menu. The failure happened on
    every menu open and took the whole tray down, not just that one entry.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_every_recent_entry_is_an_acceptable_pystray_action(self):
        import pystray

        class FakeHistory:
            def entries(self):
                return ["C:/tmp/a.png", "C:/tmp/b.png"]

        items = self.app._recent_menu_items(FakeHistory(), mock.Mock())
        for item in items:
            if item is pystray.Menu.SEPARATOR:
                continue
            # MenuItem.__init__ already ran _assert_action, so reaching here
            # without ValueError is most of the proof; assert the shape too.
            action = getattr(item, "_action", None)
            self.assertTrue(callable(action))

    def test_no_menu_action_needs_more_than_three_parameters(self):
        """A third parameter is only safe if it has no default.

        pystray accepts at most two, so anything else must be a partial or a
        wrapper it treats as opaque (no __code__ attribute).
        """
        import pystray

        class FakeHistory:
            def entries(self):
                return ["C:/tmp/a.png"]

        items = self.app._recent_menu_items(FakeHistory(), mock.Mock())
        for item in items:
            if item is pystray.Menu.SEPARATOR:
                continue
            action = getattr(item, "_action", None)
            code = getattr(action, "__code__", None)
            if code is None:
                continue  # partial/wrapper: pystray passes it through
            self.assertLessEqual(
                code.co_argcount, 2,
                "%s would be rejected by pystray's _assert_action" % item)

    def test_selecting_a_history_entry_schedules_the_open(self):
        root = mock.Mock()
        self.app._open_history_entry(root, "C:/tmp/a.png")
        root.after.assert_called_once()
        args = root.after.call_args[0]
        self.assertEqual(args[0], 0)
        self.assertEqual(args[1], self.app.open_image_file)
        self.assertEqual(args[2], "C:/tmp/a.png")

    def test_the_open_helper_ignores_the_pystray_arguments(self):
        """pystray calls actions as (icon, menu_item)."""
        root = mock.Mock()
        self.app._open_history_entry(root, "C:/tmp/x.png", "icon", "item")
        root.after.assert_called_once()


class InfoDialogWiringTests(unittest.TestCase):
    """The About item must reach a function, whatever object it is called on."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_the_capture_tool_is_not_expected_to_own_the_about_method(self):
        """Documents why the old tray callback failed."""
        self.assertFalse(hasattr(self.app.SnippingTool, "show_function_info"),
                         "if this ever becomes true, the tray wiring changed")

    def test_the_module_level_dialog_helper_exists(self):
        self.assertTrue(callable(self.app.show_info_dialog))

    def test_the_tray_about_item_calls_the_helper(self):
        source = (ROOT / "ScreenShotTool.pyw").read_text(encoding="utf-8")
        self.assertIn("root.after(0, show_info_dialog, root)", source)
        # The old wiring called a method the capture tool does not define. Match
        # the call form only, so the docstring that explains the bug is allowed
        # to name it.
        self.assertNotIn("app.show_function_info)", source,
                         "the tray must not call a method the tool lacks")

    def test_the_dialog_helper_signs_a_hotkey_callback(self):
        """The dialog calls back with a config dict; the callback must accept it."""
        with mock.patch.object(self.app, "root_window_for_tk",
                               return_value=mock.Mock()), \
                mock.patch.object(self.app, "load_config", return_value={}), \
                mock.patch.object(self.app.ui_dialogs, "open_info_dialog") as dialog:
            self.app.show_info_dialog()
        dialog.assert_called_once()
        kwargs = dialog.call_args.kwargs
        self.assertIn("on_open_hotkeys", kwargs)
        self.assertTrue(callable(kwargs["on_open_hotkeys"]))


class UpdateReasonTests(unittest.TestCase):
    """A 404 must not be reported as a network problem."""

    def _fetch_with(self, side_effect):
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               side_effect=side_effect):
            return ui_updates.fetch_latest_release_detailed()

    def test_404_reports_not_found(self):
        import urllib.error
        error = urllib.error.HTTPError(
            ui_updates.RELEASES_API, 404, "Not Found", None, None)
        release, reason = self._fetch_with(error)
        self.assertIsNone(release)
        self.assertEqual(reason, "not-found",
                         "a private repo returns 404; blaming the network is wrong")

    def test_a_real_connection_failure_reports_offline(self):
        import urllib.error
        error = urllib.error.URLError("no route to host")
        release, reason = self._fetch_with(error)
        self.assertIsNone(release)
        self.assertEqual(reason, "offline")

    def test_rate_limiting_is_its_own_reason(self):
        import urllib.error
        error = urllib.error.HTTPError(
            ui_updates.RELEASES_API, 403, "rate limited", None, None)
        _, reason = self._fetch_with(error)
        self.assertEqual(reason, "rate-limited")

    def test_a_successful_fetch_reports_ok(self):
        payload = b'{"tag_name": "v9.9.9", "html_url": "u", "body": "b", "name": "n"}'
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = payload
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               return_value=response):
            release, reason = ui_updates.fetch_latest_release_detailed()
        self.assertEqual(reason, "ok")
        self.assertEqual(release["tag"], "v9.9.9")

    def test_the_plain_fetch_still_returns_only_the_release(self):
        import urllib.error
        error = urllib.error.HTTPError(
            ui_updates.RELEASES_API, 404, "Not Found", None, None)
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               side_effect=error):
            self.assertIsNone(ui_updates.fetch_latest_release())

    def test_check_async_passes_the_reason_to_a_three_argument_callback(self):
        seen = []
        with mock.patch.object(ui_updates, "fetch_latest_release_detailed",
                               return_value=(None, "not-found")):
            worker = ui_updates.check_async(
                "1.0", lambda release, current, reason: seen.append(
                    (release, current, reason)))
            worker.join(timeout=5)
        self.assertEqual(seen, [(None, "1.0", "not-found")])

    def test_check_async_still_honours_a_two_argument_callback(self):
        seen = []
        with mock.patch.object(ui_updates, "fetch_latest_release_detailed",
                               return_value=(None, "offline")):
            worker = ui_updates.check_async(
                "1.0", lambda release, current: seen.append((release, current)))
            worker.join(timeout=5)
        self.assertEqual(seen, [(None, "1.0")])


class UpdateMessageTests(unittest.TestCase):
    """The dialog text must match the reason."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_not_found_does_not_tell_the_user_to_check_the_network(self):
        text = self.app._update_failure_message("not-found")
        self.assertIn("riêng tư", text)
        self.assertNotIn("kết nối mạng", text)

    def test_offline_does_mention_the_network(self):
        self.assertIn("kết nối mạng", self.app._update_failure_message("offline"))

    def test_every_reason_produces_a_distinct_message(self):
        reasons = ["not-found", "rate-limited", "offline", "error"]
        messages = {self.app._update_failure_message(r) for r in reasons}
        self.assertEqual(len(messages), len(reasons))


if __name__ == "__main__":
    unittest.main()
