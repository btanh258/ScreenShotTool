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
        with mock.patch.object(ui_updates, "fetch_latest_release",
                               return_value={"tag": "v9.9.9", "url": "", "notes": "", "name": ""}):
            worker = ui_updates.check_async("1.0.0", lambda rel, cur: received.append((rel, cur)))
            worker.join(timeout=5)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0]["tag"], "v9.9.9")
        self.assertEqual(received[0][1], "1.0.0")

    def test_raising_callback_does_not_escape_the_thread(self):
        # An exception here would otherwise surface as an unhandled thread error.
        with mock.patch.object(ui_updates, "fetch_latest_release", return_value=None):
            with self.assertLogs("ui_updates", level="ERROR") as captured:
                worker = ui_updates.check_async("1.0.0", lambda rel, cur: 1 / 0)
                worker.join(timeout=5)
        self.assertTrue(any("callback failed" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
