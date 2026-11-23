"""Tests for the update checker.

The whole point of this module is that a network problem never reaches the user
as an error, so most of these tests are about failures resolving quietly.
"""
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import ui_updates


class VersionParsingTests(unittest.TestCase):
    def test_parses_plain_and_prefixed(self):
        self.assertEqual(ui_updates.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(ui_updates.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(ui_updates.parse_version("V1.2.3"), (1, 2, 3))

    def test_pads_short_versions(self):
        self.assertEqual(ui_updates.parse_version("1.2"), (1, 2, 0))
        self.assertEqual(ui_updates.parse_version("1"), (1, 0, 0))

    def test_ignores_suffixes(self):
        self.assertEqual(ui_updates.parse_version("1.2.3-beta"), (1, 2, 3))

    def test_rejects_nonsense(self):
        for value in (None, "", "v", "abc", "1.x.3", 12):
            self.assertIsNone(ui_updates.parse_version(value))


class NewerComparisonTests(unittest.TestCase):
    def test_higher_minor_and_patch_are_newer(self):
        self.assertTrue(ui_updates.is_newer("1.1.0", "1.0.0"))
        self.assertTrue(ui_updates.is_newer("1.0.1", "1.0.0"))
        self.assertTrue(ui_updates.is_newer("v2.0.0", "1.9.9"))

    def test_same_version_is_not_newer(self):
        self.assertFalse(ui_updates.is_newer("1.1.0", "1.1.0"))
        self.assertFalse(ui_updates.is_newer("v1.1.0", "1.1.0"))

    def test_older_is_not_newer(self):
        self.assertFalse(ui_updates.is_newer("1.0.0", "1.1.0"))

    def test_unparseable_never_claims_an_update(self):
        # Erring toward "up to date" is the safe direction: the alternative is
        # telling the user to download something that does not exist.
        self.assertFalse(ui_updates.is_newer("garbage", "1.0.0"))
        self.assertFalse(ui_updates.is_newer("2.0.0", "garbage"))

    def test_numeric_not_lexicographic(self):
        # The classic bug: "1.10.0" must beat "1.9.0".
        self.assertTrue(ui_updates.is_newer("1.10.0", "1.9.0"))


class FetchTests(unittest.TestCase):
    def _response(self, payload):
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        return response

    def test_returns_release_fields(self):
        payload = {"tag_name": "v1.2.0", "html_url": "https://example/rel",
                   "body": "notes", "name": "v1.2.0"}
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               return_value=self._response(payload)):
            release = ui_updates.fetch_latest_release()
        self.assertEqual(release["tag"], "v1.2.0")
        self.assertEqual(release["url"], "https://example/rel")

    def test_offline_returns_none(self):
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("offline")):
            self.assertIsNone(ui_updates.fetch_latest_release())

    def test_http_error_returns_none(self):
        error = urllib.error.HTTPError("url", 403, "rate limited", {}, None)
        with mock.patch.object(ui_updates.urllib.request, "urlopen", side_effect=error):
            self.assertIsNone(ui_updates.fetch_latest_release())

    def test_malformed_json_returns_none(self):
        response = mock.MagicMock()
        response.read.return_value = b"<html>not json</html>"
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        with mock.patch.object(ui_updates.urllib.request, "urlopen", return_value=response):
            self.assertIsNone(ui_updates.fetch_latest_release())

    def test_unexpected_payload_shape_returns_none(self):
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               return_value=self._response(["not", "a", "dict"])):
            self.assertIsNone(ui_updates.fetch_latest_release())

    def test_missing_fields_become_empty_strings(self):
        with mock.patch.object(ui_updates.urllib.request, "urlopen",
                               return_value=self._response({})):
            release = ui_updates.fetch_latest_release()
        self.assertEqual(release["tag"], "")
        self.assertEqual(release["url"], "")


class AsyncTests(unittest.TestCase):
    def test_callback_receives_the_result(self):
        received = []
        with mock.patch.object(ui_updates, "fetch_latest_release_detailed",
                               return_value=({"tag": "v9.9.9", "url": "",
                                              "notes": "", "name": ""}, "ok")):
            worker = ui_updates.check_async("1.0.0", lambda rel, cur: received.append((rel, cur)))
            worker.join(timeout=5)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0]["tag"], "v9.9.9")
        self.assertEqual(received[0][1], "1.0.0")

    def test_a_two_argument_callback_still_works(self):
        """check_async passes a reason as a third argument when accepted."""
        received = []
        with mock.patch.object(ui_updates, "fetch_latest_release_detailed",
                               return_value=(None, "offline")):
            worker = ui_updates.check_async(
                "1.0.0", lambda rel, cur, reason: received.append((rel, cur, reason)))
            worker.join(timeout=5)
        self.assertEqual(received, [(None, "1.0.0", "offline")])

    def test_raising_callback_does_not_escape_the_thread(self):
        # An exception here would otherwise surface as an unhandled thread error.
        with mock.patch.object(ui_updates, "fetch_latest_release_detailed",
                               return_value=(None, "offline")):
            with self.assertLogs("ui_updates", level="ERROR") as captured:
                worker = ui_updates.check_async("1.0.0", lambda rel, cur: 1 / 0)
                worker.join(timeout=5)
        self.assertTrue(any("callback failed" in line for line in captured.output))


class UpdateInstallTests(unittest.TestCase):
    """Downloading and swapping the new build in place.

    The swap cannot happen from inside the running program on Windows, so the
    module writes a helper script. These tests pin the parts that are easy to
    get wrong: picking the right asset, never leaving a truncated download that
    a later run would install, and refusing to "apply" a payload that is absent.
    """

    def _release(self, *assets):
        return {"tag": "v9.9.9", "url": "https://example/tag",
                "assets": list(assets)}

    def test_picks_the_packaged_exe(self):
        release = self._release(
            {"name": "SHA256SUMS.txt", "url": "https://example/sums"},
            {"name": "ScreenShotTool.exe", "url": "https://example/app"},
        )
        self.assertEqual(ui_updates.pick_update_asset(release),
                         "https://example/app")

    def test_falls_back_to_any_exe(self):
        release = self._release({"name": "Other.EXE", "url": "https://example/o"})
        self.assertEqual(ui_updates.pick_update_asset(release),
                         "https://example/o")

    def test_no_assets_means_no_in_app_install(self):
        self.assertIsNone(ui_updates.pick_update_asset(self._release()))
        self.assertIsNone(ui_updates.pick_update_asset({}))
        self.assertIsNone(ui_updates.pick_update_asset(None))

    def test_asset_without_a_url_is_ignored(self):
        release = self._release({"name": "ScreenShotTool.exe", "url": ""})
        self.assertIsNone(ui_updates.pick_update_asset(release))

    def test_release_payload_carries_the_assets(self):
        payload = {
            "tag_name": "v2.0.0",
            "html_url": "https://example/tag",
            "assets": [
                {"name": "ScreenShotTool.exe",
                 "browser_download_url": "https://example/app", "size": 123},
                "not a dict",
            ],
        }
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=response):
            release, reason = ui_updates.fetch_latest_release_detailed()
        self.assertEqual(reason, "ok")
        self.assertEqual(release["assets"],
                         [{"name": "ScreenShotTool.exe",
                           "url": "https://example/app", "size": 123}])
        self.assertEqual(ui_updates.pick_update_asset(release),
                         "https://example/app")

    def test_download_writes_the_whole_payload(self):
        import tempfile
        source = Path(tempfile.mkdtemp()) / "payload.bin"
        body = b"release-binary" * 5000
        source.write_bytes(body)
        target = source.parent / "downloaded.exe"
        result = ui_updates.download_asset(source.as_uri(), target)
        self.assertEqual(result, str(target))
        self.assertEqual(target.read_bytes(), body)
        # The temporary sibling must not survive a successful download.
        self.assertFalse(Path(str(target) + ".part").exists())

    def test_truncated_download_is_rejected(self):
        # Server báo 1000 bytes nhưng chỉ gửi 100: file cụt phải bị hủy,
        # không được đổi tên thành exe để swap vào.
        import tempfile
        body = b"x" * 100
        response = mock.MagicMock()
        response.headers.get.return_value = "1000"
        response.read.side_effect = [body, b""]
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.exe"
            with mock.patch("urllib.request.urlopen", return_value=response):
                result = ui_updates.download_asset("https://example/app.exe", target)
            self.assertIsNone(result)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())

    def test_download_accepts_a_path_object(self):
        import tempfile
        source = Path(tempfile.mkdtemp()) / "payload.bin"
        source.write_bytes(b"abc")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.exe"
            self.assertEqual(ui_updates.download_asset(source.as_uri(), target),
                             str(target))
            self.assertEqual(target.read_bytes(), b"abc")

    def test_failed_download_leaves_nothing_behind(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "missing.exe"
            result = ui_updates.download_asset(
                (Path(folder) / "does-not-exist.bin").as_uri(), target)
            self.assertIsNone(result)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())

    def test_download_reports_progress(self):
        import tempfile
        source = Path(tempfile.mkdtemp()) / "payload.bin"
        source.write_bytes(b"x" * 4096)
        seen = []
        with tempfile.TemporaryDirectory() as folder:
            ui_updates.download_asset(source.as_uri(),
                                      Path(folder) / "out.bin",
                                      chunk_size=1024,
                                      progress=lambda done, total: seen.append(done))
        self.assertTrue(seen)
        self.assertEqual(seen[-1], 4096)

    def test_apply_update_refuses_a_missing_payload(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(ui_updates.apply_update(
                Path(folder) / "nope.exe", Path(folder) / "current.exe"))

    def test_apply_update_returns_a_launched_helper(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        new = folder / "new.exe"
        old = folder / "old.exe"
        new.write_bytes(b"NEW")
        old.write_bytes(b"OLD")
        with mock.patch("subprocess.Popen") as popen:
            helper = ui_updates.apply_update(new, old, relaunch=False)
        self.assertIsNotNone(helper)
        self.assertTrue(Path(helper).is_file())
        script = Path(helper).read_text(encoding="utf-8")
        self.assertIn(str(old), script)
        self.assertIn(str(new), script)
        popen.assert_called_once()

    def test_the_helper_restarts_the_binary_and_cleans_up(self):
        template = ui_updates._UPDATE_SCRIPT
        self.assertIn('start "" "%OLD%"', template)
        self.assertIn("goto retry", template)
        self.assertIn('del "%~f0"', template)
        # An unbounded retry would spin forever if a virus scanner held the file.
        self.assertIn("GEQ", template)

    def test_can_self_update_tracks_the_frozen_flag(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertTrue(ui_updates.can_self_update())
        self.assertFalse(ui_updates.can_self_update())


class OnedirUpdateTests(unittest.TestCase):
    def _release(self):
        return {"tag": "v1.4.2", "assets": [
            {"name": "ScreenShotTool.exe",
             "url": "https://example/ScreenShotTool.exe", "size": 1},
            {"name": "ScreenShotTool-1.4.2.zip",
             "url": "https://example/ScreenShotTool-1.4.2.zip", "size": 2},
        ]}

    def test_onefile_is_detected_by_the_missing_internal_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            exe = str(Path(folder) / "ScreenShotTool.exe")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", exe):
                self.assertTrue(ui_updates.is_onefile_build())
                (Path(folder) / "_internal").mkdir()
                self.assertFalse(ui_updates.is_onefile_build())
        self.assertFalse(ui_updates.is_onefile_build())

    def test_asset_choice_follows_the_build_type(self):
        release = self._release()
        with mock.patch.object(ui_updates, "is_onefile_build",
                               return_value=True):
            self.assertEqual(ui_updates.pick_update_asset(release),
                             "https://example/ScreenShotTool.exe")
        with mock.patch.object(ui_updates, "is_onefile_build",
                               return_value=False):
            self.assertEqual(ui_updates.pick_update_asset(release),
                             "https://example/ScreenShotTool-1.4.2.zip")
        self.assertEqual(ui_updates.pick_update_zip(release),
                         "https://example/ScreenShotTool-1.4.2.zip")
        self.assertIsNone(ui_updates.pick_update_zip({"assets": []}))

    def test_onefile_falls_back_to_the_zip_when_there_is_no_exe(self):
        release = {"tag": "v9.9.9", "assets": [
            {"name": "ScreenShotTool-9.9.9.zip",
             "url": "https://example/app.zip", "size": 2}]}
        with mock.patch.object(ui_updates, "is_onefile_build",
                               return_value=True):
            self.assertEqual(ui_updates.pick_update_asset(release),
                             "https://example/app.zip")

    def _make_zip(self, folder):
        import zipfile
        source = Path(folder) / "app.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("ScreenShotTool/ScreenShotTool.exe", b"EXE")
        return source

    def test_dir_update_stages_the_zip_and_swaps_the_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            local_appdata = Path(folder) / "Local"
            local_appdata.mkdir()
            current_exe = Path(folder) / "Downloads" / "ScreenShotTool.exe"
            current_exe.parent.mkdir()
            current_exe.write_bytes(b"OLD")
            zip_path = self._make_zip(folder)
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(ui_updates, "is_onefile_build",
                                      return_value=True), \
                    mock.patch.dict("os.environ",
                                    {"LOCALAPPDATA": str(local_appdata)}), \
                    mock.patch("subprocess.Popen") as popen:
                helper = ui_updates.apply_update(zip_path, current_exe,
                                                 relaunch=False)
            self.assertIsNotNone(helper)
            popen.assert_called_once()
            script = Path(helper).read_text(encoding="utf-8")
            target = str(local_appdata / "ScreenShotTool")
            self.assertIn(target, script)
            self.assertIn('move /y "%TARGET%" "%TARGET%.old"', script)
            self.assertIn("rem no relaunch", script)
            staged = Path(tempfile.gettempdir()) / "ScreenShotTool-update" \
                / "ScreenShotTool" / "ScreenShotTool.exe"
            self.assertTrue(staged.is_file())

    def test_dir_helper_script_renames_swaps_and_relaunches(self):
        template = ui_updates._UPDATE_DIR_SCRIPT
        self.assertIn('move /y "%TARGET%" "%TARGET%.old"', template)
        self.assertIn('start "" "%TARGET%\\%EXE%"', template)
        self.assertIn('del "%~f0"', template)
        # An unbounded retry would spin forever if a virus scanner held the folder.
        self.assertIn("GEQ", template)

    def test_dir_update_on_an_onedir_build_replaces_its_own_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            app_dir = Path(folder) / "ScreenShotTool"
            app_dir.mkdir()
            current_exe = app_dir / "ScreenShotTool.exe"
            current_exe.write_bytes(b"OLD")
            zip_path = self._make_zip(folder)
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(ui_updates, "is_onefile_build",
                                      return_value=False), \
                    mock.patch("subprocess.Popen"):
                helper = ui_updates.apply_update(zip_path, current_exe,
                                                 relaunch=False)
            self.assertIsNotNone(helper)
            script = Path(helper).read_text(encoding="utf-8")
            self.assertIn(str(app_dir), script)

    def test_bad_zip_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "app.zip"
            bad.write_bytes(b"not a zip")
            self.assertIsNone(ui_updates.apply_update(
                bad, Path(folder) / "ScreenShotTool.exe"))

    def test_cleanup_removes_the_old_folder_after_a_swap(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            app_dir = Path(folder) / "ScreenShotTool"
            old_dir = Path(folder) / "ScreenShotTool.old"
            old_dir.mkdir()
            (old_dir / "junk.txt").write_text("old")
            exe = str(app_dir / "ScreenShotTool.exe")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", exe):
                ui_updates.cleanup_old_app_dir()
            self.assertFalse(old_dir.exists())
        # Running from source never touches anything.
        ui_updates.cleanup_old_app_dir()


if __name__ == "__main__":
    unittest.main()
