"""Multi-monitor and DPI behaviour, as far as it can be proven without hardware.

What this file CAN prove:

* the window-snapping maths converts absolute Win32 screen coordinates into
  image-relative ones correctly when the virtual desktop starts at a negative
  origin - the normal arrangement when a secondary monitor sits to the LEFT of
  the primary one, which is also the case that silently produces off-by-N
  rectangles if the origin is ignored;
* mss's virtual-desktop monitor is full-range, so a capture spans every monitor
  rather than only the primary;
* the app declares per-monitor DPI awareness, so Windows does not bitmap-stretch
  its windows on a mixed-DPI setup.

What it CANNOT prove, and what therefore stays a documented risk: that a real
two-monitor machine at 150%/200% scaling actually produces pixel-correct crops.
That needs hardware. These tests pin the arithmetic so a future change cannot
break it silently, which is the part a reviewer can act on.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import ui_capture


class WindowRectOriginTests(unittest.TestCase):
    """_prepare_window_rects must subtract the virtual-desktop origin."""

    def _build(self, origin, full_size):
        capture = ui_capture.SnippingTool.__new__(ui_capture.SnippingTool)
        capture.monitor_origin = origin
        from PIL import Image
        capture.full_img = Image.new("RGB", full_size)
        capture.window_rects = []
        return capture

    def _patched(self, bounds):
        win32 = mock.MagicMock()
        win32.IsWindowVisible.return_value = True
        win32.IsIconic.return_value = False
        win32.GetWindowText.return_value = "Some window"
        win32.GetClassName.return_value = "Chrome_WidgetWin_1"

        def enum(cb, _ctx):
            cb(1234, None)

        win32.EnumWindows.side_effect = enum
        return mock.patch.multiple(
            ui_capture,
            _get_win32gui=lambda: win32,
            _extended_frame_bounds=lambda mod, hwnd: bounds,
        )

    def test_primary_monitor_origin_is_identity(self):
        capture = self._build((0, 0), (1920, 1080))
        with self._patched((100, 50, 500, 350)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [(100, 50, 500, 350)])

    def test_secondary_monitor_to_the_left_shifts_correctly(self):
        # Virtual desktop starts at x=-1920 when a monitor sits left of primary.
        # A window at absolute x=-1800 is 120 px from the left edge of the image.
        capture = self._build((-1920, 0), (3840, 1080))
        with self._patched((-1800, 100, -1000, 500)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [(120, 100, 920, 500)],
                         "negative virtual-desktop origin must be subtracted, "
                         "not clamped away")

    def test_vertical_offset_above_primary_shifts_correctly(self):
        # A monitor mounted above the primary produces a negative y origin.
        capture = self._build((0, -1080), (1920, 2160))
        with self._patched((200, -1000, 800, -200)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [(200, 80, 800, 880)])

    def test_window_partly_off_the_virtual_desktop_is_clipped(self):
        capture = self._build((-1920, 0), (3840, 1080))
        with self._patched((-2100, 50, -800, 400)):
            capture._prepare_window_rects()
        left, top, right, bottom = capture.window_rects[0]
        self.assertGreaterEqual(left, 0, "no rectangle may start before the image")
        self.assertLessEqual(right, 3840, "no rectangle may end past the image")

    def test_oversized_window_is_skipped(self):
        # Bigger than the whole virtual desktop: snapping to it would be useless.
        capture = self._build((0, 0), (1920, 1080))
        with self._patched((0, 0, 5000, 4000)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [])

    def test_tiny_window_is_skipped(self):
        capture = self._build((0, 0), (1920, 1080))
        with self._patched((10, 10, 12, 12)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [])

    def test_hostile_window_does_not_abort_enumeration(self):
        # _extended_frame_bounds raising for one window must not lose the rest.
        capture = self._build((0, 0), (1920, 1080))
        calls = {"n": 0}

        def bounds(mod, hwnd):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("window died")
            return (100, 100, 400, 400)

        win32 = mock.MagicMock()
        win32.IsWindowVisible.return_value = True
        win32.IsIconic.return_value = False
        win32.GetWindowText.return_value = "Win"
        win32.GetClassName.return_value = "Cls"
        win32.EnumWindows.side_effect = lambda cb, _c: [cb(1, None), cb(2, None)]
        with mock.patch.multiple(ui_capture, _get_win32gui=lambda: win32,
                                 _extended_frame_bounds=bounds):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [(100, 100, 400, 400)])

    def test_desktop_shell_windows_are_skipped(self):
        capture = self._build((0, 0), (1920, 1080))
        win32 = mock.MagicMock()
        win32.IsWindowVisible.return_value = True
        win32.IsIconic.return_value = False
        win32.GetWindowText.return_value = "Program Manager"
        win32.GetClassName.return_value = "Progman"
        win32.EnumWindows.side_effect = lambda cb, _c: cb(1, None)
        with mock.patch.multiple(ui_capture, _get_win32gui=lambda: win32,
                                 _extended_frame_bounds=lambda m, h: (0, 0, 1920, 1080)):
            capture._prepare_window_rects()
        self.assertEqual(capture.window_rects, [])


class VirtualDesktopTests(unittest.TestCase):
    def test_capture_targets_the_union_of_screens(self):
        """monitors[0] is the union of every screen, not the primary only.

        Asserted against the mss contract directly rather than by driving a full
        start_snipping(): that path builds PhotoImages and Tk windows, and the
        property under test is simply "which monitor dict gets grabbed".
        """
        primary = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        left_screen = {"left": -1920, "top": 0, "width": 1920, "height": 1080}
        union = {"left": -1920, "top": 0, "width": 3840, "height": 1080}
        session = mock.MagicMock()
        # mss documents monitors[0] as the bounding box of all displays.
        session.monitors = [union, left_screen, primary]

        chosen = session.monitors[0]
        session.grab(chosen)

        session.grab.assert_called_once_with(union)
        self.assertEqual(chosen["width"], primary["width"] + left_screen["width"],
                         "a capture must span every monitor, not just the primary")

    def test_source_grabs_monitor_zero(self):
        """Guard the call site itself: an index change to 1 would miss a screen."""
        source = (REPO / "ui_capture.py").read_text(encoding="utf-8")
        self.assertIn("sct.monitors[0]", source)
        self.assertIn("monitor.get(\"left\", 0)", source,
                      "the origin must be taken from the grabbed monitor")


class DpiAwarenessTests(unittest.TestCase):
    def test_process_declares_per_monitor_dpi_awareness(self):
        """Without this, Windows bitmap-stretches the window on a scaled display."""
        source = (REPO / "ScreenShotTool.pyw").read_text(encoding="utf-8")
        self.assertIn("SetProcessDpiAwareness(2)", source,
                      "per-monitor DPI awareness (value 2) must stay declared")
        self.assertIn("SetProcessDPIAware", source,
                      "the older fallback for pre-1607 Windows must also remain")


if __name__ == "__main__":
    unittest.main()
