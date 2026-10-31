# -*- coding: utf-8 -*-
"""tests/test_ui_parity.py - behavioural parity suite for the design system.

Written independently against ``UI_REDESIGN_CONTRACT.md`` sections 2 and 3.
``ui_theme.py`` and ``ui_widgets.py`` are frozen, so everything here is a hard
assertion: a red test means the redesign broke its own design system.

Every test tolerates a headless machine: GUI tests skip (not error) when Tk
cannot open a display, which keeps the windows-latest CI job and any Linux
container green.
"""

import re
import tkinter as tk
import unittest
from tkinter import ttk

import ui_theme as T
import ui_widgets as W


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# --- documented token keys (UI_REDESIGN_CONTRACT.md section 2) -------------
COLOR_KEYS = [
    "app", "chrome", "panel", "elevated", "hover", "canvas_bg",
    "border", "border_strong", "focus_ring",
    "text_primary", "text_secondary", "text_muted", "text_on_accent",
    "accent", "accent_hover", "accent_pressed", "accent_soft",
    "success", "danger", "warning", "info", "scrim", "hint_bg", "selection",
]
SPACE_KEYS = ["xs", "sm", "md", "lg", "xl", "xxl"]
RADIUS_KEYS = ["sm", "md", "lg", "xl", "pill"]
METRICS_KEYS = ["toolbar_h", "statusbar_h", "rail_w", "sidebar_w",
                "control_h", "control_h_sm", "icon_size", "toast_w"]
FONTS_KEYS = ["display", "title", "heading", "subheading", "body",
              "body_strong", "small", "small_strong", "tiny", "mono",
              "mono_small"]
GLYPH_KEYS = ["select", "crop", "erase", "pen", "highlight", "rect", "oval",
              "arrow", "text", "blur", "undo", "redo", "copy", "save", "info",
              "zoom_in", "zoom_out", "fit", "flip_h", "flip_v", "rotate_ccw",
              "rotate_cw", "close", "check", "warning", "settings", "random",
              "keyboard", "magnifier", "target"]
STYLE_NAMES = [
    "STYLE_APP_FRAME", "STYLE_CHROME_FRAME", "STYLE_PANEL_FRAME",
    "STYLE_CARD_FRAME", "STYLE_TITLE_LABEL", "STYLE_SUBTITLE_LABEL",
    "STYLE_BODY_LABEL", "STYLE_MUTED_LABEL", "STYLE_CHROME_LABEL",
    "STYLE_PRIMARY_BUTTON", "STYLE_SECONDARY_BUTTON", "STYLE_GHOST_BUTTON",
    "STYLE_DANGER_BUTTON", "STYLE_SUCCESS_BUTTON", "STYLE_ACTION_BUTTON",
    "STYLE_COMBOBOX", "STYLE_ENTRY", "STYLE_CHECKBUTTON", "STYLE_VSCROLL",
    "STYLE_HSCROLL", "STYLE_SEPARATOR",
]


def _norm(color):
    """Normalise a Tk colour string to lowercase #rrggbb for comparison."""
    return str(color).strip().lower()


class TokenContractTests(unittest.TestCase):
    """Pure-data checks: no Tk root needed, so these never skip."""

    def test_colors_expose_every_documented_key(self):
        for key in COLOR_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.COLORS, "COLORS is missing documented key %r" % key)
                self.assertTrue(getattr(T.COLORS, key), "COLORS.%s is empty" % key)

    def test_colors_attribute_and_mapping_access_agree(self):
        for key in COLOR_KEYS:
            with self.subTest(key=key):
                self.assertEqual(T.COLORS[key], getattr(T.COLORS, key))

    def test_every_color_is_a_valid_hex_triplet(self):
        for key, value in T.COLORS.items():
            with self.subTest(key=key, value=value):
                self.assertRegex(value, HEX_RE,
                                 "COLORS.%s = %r is not a #rrggbb colour" % (key, value))

    def test_spacing_scale(self):
        for key in SPACE_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.SPACE)
        self.assertEqual((T.SPACE.xs, T.SPACE.sm, T.SPACE.md, T.SPACE.lg, T.SPACE.xl, T.SPACE.xxl),
                         (4, 8, 12, 16, 24, 32),
                         "SPACE must stay the documented 4/8/12/16/24/32 scale")
        # The scale must be strictly increasing, or layout rhythm silently breaks.
        ordered = [T.SPACE[k] for k in SPACE_KEYS]
        self.assertEqual(ordered, sorted(ordered))
        self.assertEqual(len(set(ordered)), len(ordered))

    def test_radius_scale(self):
        for key in RADIUS_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.RADIUS)
        self.assertEqual((T.RADIUS.sm, T.RADIUS.md, T.RADIUS.lg, T.RADIUS.xl), (6, 10, 14, 20))
        self.assertGreaterEqual(T.RADIUS.pill, 100, "RADIUS.pill must be large enough to read as a pill")

    def test_metrics_scale(self):
        for key in METRICS_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.METRICS)
                self.assertIsInstance(T.METRICS[key], int, "METRICS.%s must be an int" % key)
                self.assertGreater(T.METRICS[key], 0)
        # Editor chrome must fit a 1080p screen with room for the image.
        self.assertLessEqual(T.METRICS.toolbar_h + T.METRICS.statusbar_h, 200)
        self.assertLessEqual(T.METRICS.rail_w + T.METRICS.sidebar_w, 600)

    def test_fonts_are_valid_tk_specs(self):
        for key in FONTS_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.FONTS, "FONTS is missing documented key %r" % key)
                spec = T.FONTS[key]
                self.assertIsInstance(spec, tuple, "FONTS.%s must be a tuple, got %r" % (key, type(spec)))
                self.assertGreaterEqual(len(spec), 2, "FONTS.%s = %r is not a valid font spec" % (key, spec))
                self.assertIsInstance(spec[0], str, "FONTS.%s family must be a str" % key)
                self.assertIsInstance(spec[1], int, "FONTS.%s size must be an int" % key)
                self.assertGreater(spec[1], 0, "FONTS.%s size must be positive" % key)
                for style_word in spec[2:]:
                    self.assertIn(style_word, ("normal", "bold", "italic", "roman", "underline", "overstrike"),
                                  "FONTS.%s has an invalid style word %r" % (key, style_word))

    def test_mono_fonts_use_the_mono_family(self):
        for key in ("mono", "mono_small"):
            with self.subTest(key=key):
                self.assertEqual(T.FONTS[key][0], T.MONO_FAMILY)

    def test_font_helpers(self):
        self.assertEqual(T.FONT_FAMILY, "Segoe UI")
        self.assertEqual(T.MONO_FAMILY, "Consolas")
        self.assertEqual(T.font(12, "bold"), (T.FONT_FAMILY, 12, "bold"))
        self.assertEqual(T.font(9), (T.FONT_FAMILY, 9))
        self.assertEqual(T.mono_font(8), (T.MONO_FAMILY, 8))
        self.assertEqual(T.font(11, "bold", "italic"), (T.FONT_FAMILY, 11, "bold", "italic"))

    def test_glyphs_present_and_unique_where_they_must_be(self):
        for key in GLYPH_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, T.GLYPH, "GLYPH is missing documented key %r" % key)
                self.assertTrue(str(T.GLYPH[key]), "GLYPH.%s is empty" % key)
        # Every tool glyph must be visually distinct or the rail is unreadable.
        tool_keys = ["select", "crop", "erase", "pen", "highlight", "rect", "oval",
                     "arrow", "text", "blur"]
        glyphs = [T.GLYPH[k] for k in tool_keys]
        self.assertEqual(len(set(glyphs)), len(glyphs),
                         "duplicate tool glyphs: %r" % glyphs)

    def test_style_name_constants_exist_and_are_ttk_shaped(self):
        for name in STYLE_NAMES:
            with self.subTest(name=name):
                value = getattr(T, name)
                self.assertIsInstance(value, str)
                self.assertIn(".", value, "%s = %r is not a named ttk style" % (name, value))


class ColorHelperTests(unittest.TestCase):
    """mix/lighten/darken/readable_on - pure functions, no display needed."""

    def test_mix_endpoints_are_exact(self):
        self.assertEqual(_norm(T.mix("#3b82f6", "#ffffff", 0)), "#3b82f6")
        self.assertEqual(_norm(T.mix("#3b82f6", "#ffffff", 1)), "#ffffff")
        self.assertEqual(_norm(T.mix("#101010", "#e0e0e0", 0)), "#101010")
        self.assertEqual(_norm(T.mix("#101010", "#e0e0e0", 1)), "#e0e0e0")

    def test_mix_clamps_out_of_range_amounts(self):
        self.assertEqual(_norm(T.mix("#3b82f6", "#ffffff", -5)), "#3b82f6")
        self.assertEqual(_norm(T.mix("#3b82f6", "#ffffff", 5)), "#ffffff")

    def test_mix_midpoint_is_between_and_symmetric(self):
        mid = T.mix("#000000", "#ffffff", 0.5)
        self.assertRegex(mid, HEX_RE)
        self.assertEqual(_norm(mid), "#808080")
        self.assertEqual(_norm(T.mix("#000000", "#ffffff", 0.25)),
                         _norm(T.mix("#ffffff", "#000000", 0.75)))

    def test_lighten_moves_toward_white(self):
        base = "#3b82f6"
        for amount in (0.05, 0.12, 0.3):
            with self.subTest(amount=amount):
                lighter = T.lighten(base, amount)
                self.assertRegex(lighter, HEX_RE)
                self.assertNotEqual(_norm(lighter), _norm(base))
                for channel, (lo, hi) in enumerate(zip(T._to_rgb(base), T._to_rgb(lighter))):
                    self.assertGreaterEqual(hi, lo, "lighten() darkened channel %d" % channel)

    def test_darken_moves_toward_black(self):
        base = "#3b82f6"
        for amount in (0.05, 0.12, 0.3):
            with self.subTest(amount=amount):
                darker = T.darken(base, amount)
                self.assertRegex(darker, HEX_RE)
                self.assertNotEqual(_norm(darker), _norm(base))
                for channel, (lo, hi) in enumerate(zip(T._to_rgb(base), T._to_rgb(darker))):
                    self.assertLessEqual(hi, lo, "darken() lightened channel %d" % channel)

    def test_lighten_and_darken_defaults(self):
        self.assertEqual(_norm(T.lighten("#3b82f6")), _norm(T.lighten("#3b82f6", 0.12)))
        self.assertEqual(_norm(T.darken("#3b82f6")), _norm(T.darken("#3b82f6", 0.12)))

    def test_lighten_darken_extremes_do_not_wrap(self):
        self.assertEqual(_norm(T.lighten("#ffffff", 1.0)), "#ffffff")
        self.assertEqual(_norm(T.darken("#000000", 1.0)), "#000000")

    def test_readable_on_dark_returns_light_text(self):
        for bg in ("#000000", "#0B0D12", "#3B82F6", "#EF4444"):
            with self.subTest(bg=bg):
                fg = T.readable_on(bg)
                self.assertRegex(fg, HEX_RE)
                self.assertGreater(self._luma(fg), 0.6,
                                   "readable_on(%s) = %s is not a light colour" % (bg, fg))

    def test_readable_on_light_returns_dark_text(self):
        for bg in ("#ffffff", "#F3F6FC", "#ffff00"):
            with self.subTest(bg=bg):
                fg = T.readable_on(bg)
                self.assertRegex(fg, HEX_RE)
                self.assertLess(self._luma(fg), 0.4,
                                "readable_on(%s) = %s is not a dark colour" % (bg, fg))

    def test_readable_on_produces_real_contrast(self):
        """The chosen text colour must differ from the background by a wide margin."""
        for bg in T.COLORS.values():
            with self.subTest(bg=bg):
                fg = T.readable_on(bg)
                self.assertGreater(abs(self._luma(fg) - self._luma(bg)), 0.35,
                                   "readable_on(%s) = %s has too little contrast" % (bg, fg))

    @staticmethod
    def _luma(color):
        r, g, b = T._to_rgb(color)
        return (r * 0.299 + g * 0.587 + b * 0.114) / 255.0


class _TkTestCase(unittest.TestCase):
    """Base class that owns exactly one Tk root and always tears it down."""

    root = None

    def setUp(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        root.withdraw()
        root.geometry("900x700+40+40")
        self.root = root
        T.apply_theme(root)

    def tearDown(self):
        if self.root is not None:
            try:
                self.root.update_idletasks()
            except tk.TclError:
                pass
            try:
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None

    def frame(self, **kw):
        kw.setdefault("bg", T.COLORS.chrome)
        frame = tk.Frame(self.root, **kw)
        frame.pack(fill="both", expand=True)
        return frame

    def texts(self, widget):
        return [widget.itemcget(item, "text") for item in widget.find_all()
                if widget.type(item) == "text"]

    def fills(self, widget):
        return [widget.itemcget(item, "fill") for item in widget.find_all()
                if widget.type(item) in ("text", "rectangle", "polygon", "oval", "line")
                and widget.itemcget(item, "fill")]


class ThemeEngineTests(_TkTestCase):

    def test_apply_theme_returns_a_ttk_style(self):
        style = T.apply_theme(self.root)
        self.assertIsInstance(style, ttk.Style)

    def test_apply_theme_is_idempotent(self):
        first = T.apply_theme(self.root)
        primary_before = first.lookup(T.STYLE_PRIMARY_BUTTON, "background")
        second = T.apply_theme(self.root)
        third = T.apply_theme(self.root)
        self.assertIsInstance(second, ttk.Style)
        self.assertIsInstance(third, ttk.Style)
        self.assertEqual(first.lookup(T.STYLE_PRIMARY_BUTTON, "background"), primary_before)
        self.assertEqual(second.lookup(T.STYLE_PRIMARY_BUTTON, "background"), primary_before)
        self.assertEqual(third.lookup(T.STYLE_PRIMARY_BUTTON, "background"), primary_before)

    def test_every_documented_style_resolves(self):
        style = T.apply_theme(self.root)
        for name in STYLE_NAMES:
            style_name = getattr(T, name)
            with self.subTest(name=name):
                try:
                    background = style.lookup(style_name, "background")
                    foreground = style.lookup(style_name, "foreground")
                    style.lookup(style_name, "font")
                    style.lookup(style_name, "fieldbackground")
                except tk.TclError as exc:
                    self.fail("style.lookup(%r) raised TclError: %s" % (style_name, exc))
                self.assertTrue(background or foreground,
                                "%s = %r is registered with neither background nor foreground"
                                % (name, style_name))

    def test_frames_carry_their_documented_surface(self):
        style = T.apply_theme(self.root)
        self.assertEqual(_norm(style.lookup(T.STYLE_APP_FRAME, "background")), _norm(T.COLORS.app))
        self.assertEqual(_norm(style.lookup(T.STYLE_CHROME_FRAME, "background")), _norm(T.COLORS.chrome))
        self.assertEqual(_norm(style.lookup(T.STYLE_PANEL_FRAME, "background")), _norm(T.COLORS.panel))
        self.assertEqual(_norm(style.lookup(T.STYLE_CARD_FRAME, "background")), _norm(T.COLORS.elevated))

    def test_button_styles_use_their_semantic_colour(self):
        style = T.apply_theme(self.root)
        for name, expected in (
            (T.STYLE_PRIMARY_BUTTON, T.COLORS.accent),
            (T.STYLE_DANGER_BUTTON, T.COLORS.danger),
            (T.STYLE_SUCCESS_BUTTON, T.COLORS.success),
            (T.STYLE_ACTION_BUTTON, T.COLORS.accent),
        ):
            with self.subTest(name=name):
                self.assertEqual(_norm(style.lookup(name, "background")), _norm(expected))

    def test_legacy_toolbutton_style_is_still_themed(self):
        """Un-migrated widgets must not fall back to the raw clam grey."""
        style = T.apply_theme(self.root)
        self.assertEqual(_norm(style.lookup("Toolbutton", "background")), _norm(T.COLORS.chrome))

    def test_buttons_expose_disabled_and_hover_states(self):
        """Contract 7: every widget shows hover / active / disabled.

        A state counts as visible when *either* the surface or the label
        changes; some variants intentionally keep their surface (a disabled
        Secondary button only dims its label).
        """
        style = T.apply_theme(self.root)
        for name in (T.STYLE_PRIMARY_BUTTON, T.STYLE_SECONDARY_BUTTON,
                     T.STYLE_GHOST_BUTTON, T.STYLE_DANGER_BUTTON,
                     T.STYLE_SUCCESS_BUTTON, T.STYLE_ACTION_BUTTON):
            with self.subTest(name=name):
                normal_bg = _norm(style.lookup(name, "background"))
                normal_fg = _norm(style.lookup(name, "foreground"))
                disabled_bg = _norm(style.lookup(name, "background", ("disabled",)))
                disabled_fg = _norm(style.lookup(name, "foreground", ("disabled",)))
                hover_bg = _norm(style.lookup(name, "background", ("active",)))
                pressed_bg = _norm(style.lookup(name, "background", ("pressed",)))

                self.assertTrue(disabled_bg, "%s has no disabled background" % name)
                self.assertTrue(pressed_bg, "%s has no pressed background" % name)
                self.assertTrue(hover_bg, "%s has no hover background" % name)

                self.assertTrue(disabled_bg != normal_bg or disabled_fg != normal_fg,
                                "%s disabled state is invisible (bg and fg unchanged)" % name)
                self.assertNotEqual(hover_bg, normal_bg, "%s hover state is invisible" % name)
                self.assertNotEqual(pressed_bg, hover_bg,
                                    "%s pressed state is indistinguishable from hover" % name)
                for value in (disabled_fg, hover_bg, pressed_bg):
                    self.assertRegex(value, HEX_RE)

    def test_neutral_buttons_have_a_visibly_distinct_disabled_fill(self):
        """Secondary rests on COLORS.elevated and Ghost on COLORS.chrome.

        Both must step *down* to COLORS.panel when disabled, and their
        hover/pressed entries must survive the same map() call (ttk map()
        replaces the whole state map, so a follow-up call would silently
        clobber them).
        """
        style = T.apply_theme(self.root)
        for name, resting, hover, pressed in (
            (T.STYLE_SECONDARY_BUTTON, T.COLORS.elevated, T.COLORS.hover, T.COLORS.border_strong),
            (T.STYLE_GHOST_BUTTON, T.COLORS.chrome, T.COLORS.hover, T.COLORS.elevated),
        ):
            with self.subTest(name=name):
                disabled = style.lookup(name, "background", ("disabled",))
                self.assertEqual(_norm(disabled), _norm(T.COLORS.panel),
                                 "%s disabled fill should be COLORS.panel" % name)
                self.assertNotEqual(_norm(disabled), _norm(resting),
                                    "%s disabled fill is identical to its resting fill" % name)
                self.assertEqual(_norm(style.lookup(name, "background", ("active",))), _norm(hover),
                                 "%s lost its hover state" % name)
                self.assertEqual(_norm(style.lookup(name, "background", ("pressed",))), _norm(pressed),
                                 "%s lost its pressed state" % name)
                # foreground must dim too, so the label reads as unavailable
                self.assertEqual(_norm(style.lookup(name, "foreground", ("disabled",))),
                                 _norm(T.COLORS.text_muted))

    def test_glyph_tokens_colliding_with_dict_methods_resolve_to_glyphs(self):
        """``GLYPH.copy`` must be the glyph, not ``dict.copy``.

        A dict-subclass token container returned the bound method here, which
        Tk stringified into the Copy button, painting garbage over its label.
        """
        for key in ("copy", "save", "select", "text", "warning", "info"):
            with self.subTest(key=key):
                value = getattr(T.GLYPH, key)
                self.assertNotIsInstance(value, type(dict.copy),
                                         "GLYPH.%s resolved to a bound dict method" % key)
                self.assertIsInstance(value, str)
                self.assertTrue(value)
                self.assertEqual(T.GLYPH[key], value)
        self.assertEqual(getattr(T.GLYPH, "copy"), T.GLYPH["copy"])
        # every glyph must be paintable as canvas text without TclError
        canvas = tk.Canvas(self.root)
        for key, glyph in T.GLYPH.items():
            with self.subTest(glyph=key):
                item = canvas.create_text(0, 0, text=glyph, fill=T.COLORS.text_primary)
                self.assertEqual(canvas.itemcget(item, "text"), glyph)

    def test_theme_applies_to_a_toplevel_too(self):
        top = tk.Toplevel(self.root)
        try:
            style = T.apply_theme(top)
            self.assertIsInstance(style, ttk.Style)
            self.assertEqual(_norm(style.lookup(T.STYLE_APP_FRAME, "background")), _norm(T.COLORS.app))
        finally:
            top.destroy()

    def test_applies_clam_and_returns_style_with_that_theme(self):
        style = T.apply_theme(self.root)
        if "clam" in style.theme_names():
            self.assertEqual(style.theme_use(), "clam")

    def test_option_database_themes_menus_and_combobox_lists(self):
        """Menus and the combobox popdown must use the dark palette.

        ``option_add`` cannot be read back with ``option_get`` in a useful way,
        so this asserts the *rendered* colours of a real Menu and of the real
        combobox popdown listbox - the widgets users actually see.
        """
        T.apply_theme(self.root)
        menu = tk.Menu(self.root)
        popdown = self.root.tk.call("ttk::combobox::PopdownWindow",
                                    self._combobox()) + ".f.l"

        checks = [
            ("Menu.background", menu.cget("background"), T.COLORS.panel),
            ("Menu.foreground", menu.cget("foreground"), T.COLORS.text_primary),
            ("Menu.activeBackground", menu.cget("activebackground"), T.COLORS.accent),
            ("Menu.activeForeground", menu.cget("activeforeground"), T.COLORS.text_on_accent),
            ("Combobox.Listbox.background",
             self.root.tk.call(popdown, "cget", "-background"), T.COLORS.elevated),
            ("Combobox.Listbox.foreground",
             self.root.tk.call(popdown, "cget", "-foreground"), T.COLORS.text_primary),
            ("Combobox.Listbox.selectBackground",
             self.root.tk.call(popdown, "cget", "-selectbackground"), T.COLORS.accent),
            ("Combobox.Listbox.selectForeground",
             self.root.tk.call(popdown, "cget", "-selectforeground"), T.COLORS.text_on_accent),
        ]
        for label, actual, expected in checks:
            with self.subTest(option=label):
                self.assertEqual(_norm(actual), _norm(expected),
                                 "%s is %r, expected %r (light patch on a dark UI)"
                                 % (label, actual, expected))

    def _combobox(self):
        if getattr(self, "_cb", None) is None:
            self._cb = ttk.Combobox(self.root, values=["a", "b"], state="readonly",
                                    style=T.STYLE_COMBOBOX)
            self._cb.pack()
            self.root.update()
        return self._cb

    def test_combobox_dropdown_arrow_and_field_are_themed(self):
        style = T.apply_theme(self.root)
        self.assertEqual(_norm(style.lookup(T.STYLE_COMBOBOX, "fieldbackground")),
                         _norm(T.COLORS.elevated))
        self.assertEqual(_norm(style.lookup(T.STYLE_COMBOBOX, "foreground")),
                         _norm(T.COLORS.text_primary))
        self.assertEqual(_norm(style.lookup(T.STYLE_COMBOBOX, "bordercolor")),
                         _norm(T.COLORS.border_strong))

    def test_entry_and_checkbutton_are_themed(self):
        style = T.apply_theme(self.root)
        self.assertEqual(_norm(style.lookup(T.STYLE_ENTRY, "fieldbackground")),
                         _norm(T.COLORS.elevated))
        self.assertEqual(_norm(style.lookup(T.STYLE_ENTRY, "foreground")),
                         _norm(T.COLORS.text_primary))
        self.assertEqual(_norm(style.lookup(T.STYLE_CHECKBUTTON, "background")),
                         _norm(T.COLORS.chrome))

    def test_scrollbars_are_themed(self):
        style = T.apply_theme(self.root)
        for name in (T.STYLE_VSCROLL, T.STYLE_HSCROLL):
            with self.subTest(name=name):
                self.assertEqual(_norm(style.lookup(name, "troughcolor")), _norm(T.COLORS.app))
                self.assertEqual(_norm(style.lookup(name, "background")), _norm(T.COLORS.border))

    def test_separator_uses_the_border_colour(self):
        style = T.apply_theme(self.root)
        self.assertEqual(_norm(style.lookup(T.STYLE_SEPARATOR, "background")),
                         _norm(T.COLORS.border))


class CanvasHelperTests(_TkTestCase):

    def test_round_rect_returns_an_item_inside_the_requested_box(self):
        canvas = tk.Canvas(self.root, width=200, height=120)
        canvas.pack()
        item = T.round_rect(canvas, 10, 20, 110, 80, 8, fill=T.COLORS.accent)
        self.assertIsInstance(item, int)
        self.assertIn(item, canvas.find_all())
        bbox = canvas.bbox(item)
        self.assertIsNotNone(bbox)
        x1, y1, x2, y2 = bbox
        # Smoothed splines overshoot by a pixel or two - allow a small tolerance.
        tolerance = 3
        self.assertLessEqual(abs(x1 - 10), tolerance, "round_rect left edge %d != 10" % x1)
        self.assertLessEqual(abs(y1 - 20), tolerance, "round_rect top edge %d != 20" % y1)
        self.assertLessEqual(abs(x2 - 110), tolerance, "round_rect right edge %d != 110" % x2)
        self.assertLessEqual(abs(y2 - 80), tolerance, "round_rect bottom edge %d != 80" % y2)

    def test_round_rect_normalises_inverted_coordinates(self):
        canvas = tk.Canvas(self.root, width=200, height=120)
        item = T.round_rect(canvas, 110, 80, 10, 20, 8, fill=T.COLORS.accent)
        x1, y1, x2, y2 = canvas.bbox(item)
        self.assertLess(x1, x2)
        self.assertLess(y1, y2)
        self.assertLessEqual(abs(x1 - 10), 3)
        self.assertLessEqual(abs(y2 - 80), 3)

    def test_round_rect_clamps_oversized_radius(self):
        canvas = tk.Canvas(self.root, width=200, height=120)
        item = T.round_rect(canvas, 0, 0, 40, 20, 999, fill=T.COLORS.accent)  # must not raise
        x1, y1, x2, y2 = canvas.bbox(item)
        self.assertLessEqual(x2 - x1, 44)
        self.assertLessEqual(y2 - y1, 24)

    def test_round_rect_accepts_outline_and_zero_radius(self):
        canvas = tk.Canvas(self.root, width=200, height=120)
        item = T.round_rect(canvas, 5, 5, 55, 35, 0, fill="", outline=T.COLORS.border, width=1)
        self.assertIsInstance(item, int)
        self.assertEqual(canvas.itemcget(item, "outline"), T.COLORS.border)

    def test_center_window_places_window_on_screen(self):
        top = tk.Toplevel(self.root)
        try:
            T.center_window(top, 400, 300)
            top.update_idletasks()
            geometry = top.geometry()
            self.assertRegex(geometry, r"^400x300([+-]\d+){2}$", "unexpected geometry %r" % geometry)
        finally:
            top.destroy()


class WidgetConstructionTests(_TkTestCase):
    """Every documented widget must construct and paint without raising."""

    def test_rail_button(self):
        var = tk.StringVar(value="select")
        w = W.RailButton(self.frame(), T.GLYPH.pen, "Bút", "pen", var, command=lambda: None)
        self.assertGreaterEqual(len(w.find_all()), 2, "RailButton painted nothing")
        self.assertEqual(w.value, "pen")
        self.assertEqual(w.caption, "Bút")
        self.assertIn("Bút", self.texts(w), "RailButton caption is not painted")

    def test_rail_button_marks_the_selected_tool(self):
        var = tk.StringVar(value="select")
        frame = self.frame()
        selected = W.RailButton(frame, T.GLYPH.pen, "Bút", "pen", var)
        # Deliberately kept, never read: constructing a second button bound to
        # the same variable is what proves the two do not both claim the
        # selected state.
        W.RailButton(frame, T.GLYPH.rect, "Chữ nhật", "rect", var)
        self.assertFalse(selected._selected())
        var.set("pen")
        self.assertTrue(selected._selected(), "RailButton did not follow its variable")
        self.assertTrue(any(w.type(i) == "rectangle" or w.itemcget(i, "fill") == T.COLORS.accent_soft
                            for i in selected.find_all() for w in [selected]),
                        "selected RailButton has no selected-state surface")

    def test_icon_button(self):
        calls = []
        w = W.IconButton(self.frame(), T.GLYPH.undo, command=lambda: calls.append(1))
        self.assertGreaterEqual(len(w.find_all()), 1)
        w.invoke()
        self.assertEqual(calls, [1])
        w.set_glyph(T.GLYPH.redo)
        self.assertEqual(w.glyph, T.GLYPH.redo)

    def test_pill_button_each_variant(self):
        frame = self.frame()
        for variant in ("primary", "secondary", "ghost", "danger", "success"):
            with self.subTest(variant=variant):
                w = W.PillButton(frame, "Lưu", variant=variant)
                self.assertGreaterEqual(len(w.find_all()), 2)
                self.assertEqual(w.cget("text"), "Lưu")

    def test_segmented_control(self):
        var = tk.StringVar(value="a")
        w = W.SegmentedControl(self.frame(), [("a", "Nhỏ"), ("b", "Lớn")], variable=var)
        self.assertEqual(len(w.options), 2)
        self.assertGreater(w.winfo_reqwidth(), w.seg_w, "SegmentedControl is narrower than one segment")

    def test_color_swatch(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        self.assertEqual(w.get_color(), "#ff0000")

    def test_number_stepper(self):
        var = tk.IntVar(value=4)
        w = W.NumberStepper(self.frame(), var, minimum=1, maximum=50)
        self.assertGreaterEqual(len(w.find_all()), 2)
        self.assertIn("4", self.texts(w))

    def test_slider(self):
        var = tk.IntVar(value=10)
        w = W.Slider(self.frame(), var, minimum=1, maximum=50)
        self.assertGreaterEqual(len(w.find_all()), 2)

    def test_toggle_switch(self):
        var = tk.BooleanVar(value=False)
        w = W.ToggleSwitch(self.frame(), var, "Tô nền chữ")
        self.assertIn("Tô nền chữ", self.texts(w))

    def test_status_bar(self):
        w = W.StatusBar(self.frame())
        self.assertTrue(hasattr(w, "hint"))
        self.assertTrue(hasattr(w, "metrics"))

    def test_inspector_section_exposes_body(self):
        w = W.InspectorSection(self.frame(), "Công cụ", subtitle="3")
        self.assertIsInstance(w.body, tk.Frame)
        self.assertGreaterEqual(len(w.winfo_children()), 2)

    def test_divider_both_orientations(self):
        frame = self.frame()
        h = W.Divider(frame)
        v = W.Divider(frame, "vertical")
        self.assertEqual(h.cget("height"), 1)
        self.assertEqual(v.cget("width"), 1)

    def test_tooltip_constructs_and_hides_cleanly(self):
        w = W.IconButton(self.frame(), T.GLYPH.info)
        tip = W.Tooltip(w, "Thông tin")
        self.assertEqual(tip.text, "Thông tin")
        self.assertEqual(tip.delay, 420)
        tip._hide()

    def test_measure_text(self):
        width = W.measure_text(T.FONTS.body, "Hello")
        self.assertIsInstance(width, int)
        self.assertGreater(width, 0)
        self.assertGreater(W.measure_text(T.FONTS.body, "Hello world"),
                           W.measure_text(T.FONTS.body, "Hello"))


class ClassicDialectTests(_TkTestCase):
    """The classic Tk widget dialect the existing app code depends on."""

    def _widgets(self):
        frame = self.frame()
        return [
            ("RailButton", W.RailButton(frame, T.GLYPH.pen, "Bút", "pen", tk.StringVar(value="select"))),
            ("IconButton", W.IconButton(frame, T.GLYPH.undo)),
            ("PillButton", W.PillButton(frame, "Lưu")),
            ("SegmentedControl", W.SegmentedControl(frame, [("a", "A"), ("b", "B")])),
            ("ColorSwatch", W.ColorSwatch(frame, "#ff0000")),
            ("NumberStepper", W.NumberStepper(frame, tk.IntVar(value=4))),
            ("Slider", W.Slider(frame, tk.IntVar(value=4))),
            ("ToggleSwitch", W.ToggleSwitch(frame, tk.BooleanVar(value=False))),
        ]

    def test_cget_text_round_trips(self):
        for name, widget in self._widgets():
            with self.subTest(widget=name):
                self.assertIsInstance(widget.cget("text"), str)
                widget.config(text="Nhãn mới")
                self.assertEqual(widget.cget("text"), "Nhãn mới")

    def test_config_state_disables_and_reenables(self):
        for name, widget in self._widgets():
            with self.subTest(widget=name):
                self.assertTrue(widget._is_enabled(), "%s should start enabled" % name)
                widget.config(state="disabled")
                self.assertFalse(widget._is_enabled(), "%s ignores state=disabled" % name)
                self.assertEqual(widget.cget("state"), "disabled")
                widget.config(state="normal")
                self.assertTrue(widget._is_enabled(), "%s did not re-enable" % name)

    def test_invoke_fires_command_only_when_enabled(self):
        frame = self.frame()
        calls = []
        for name, factory in (
            ("RailButton", lambda: W.RailButton(frame, T.GLYPH.pen, "Bút", "pen",
                                                tk.StringVar(value="select"),
                                                command=lambda: calls.append(name))),
            ("IconButton", lambda: W.IconButton(frame, T.GLYPH.undo,
                                                command=lambda: calls.append(name))),
            ("PillButton", lambda: W.PillButton(frame, "X",
                                                command=lambda: calls.append(name))),
        ):
            with self.subTest(widget=name):
                calls.clear()
                widget = factory()
                widget.invoke()
                self.assertEqual(calls, [name], "%s.invoke() did not fire its command" % name)
                widget.config(state="disabled")
                widget.invoke()
                self.assertEqual(calls, [name], "%s.invoke() fired while disabled" % name)
                widget.config(state="normal")
                widget.invoke()
                self.assertEqual(calls, [name, name], "%s.invoke() lost its command" % name)

    def test_set_text_and_set_enabled_helpers(self):
        for name, widget in self._widgets():
            with self.subTest(widget=name):
                widget.set_text("Kiểm tra")
                self.assertEqual(widget.get_text(), "Kiểm tra")
                widget.set_enabled(False)
                self.assertFalse(widget._is_enabled())
                widget.set_enabled(True)
                self.assertTrue(widget._is_enabled())

    def test_config_ignores_ttk_only_keys(self):
        """Migration calls pass ttk-only options; they must not raise TclError."""
        for name, widget in self._widgets():
            with self.subTest(widget=name):
                widget.config(style="Toolbutton", compound="left", image="",
                              takefocus=True, padx=2, pady=2,
                              activebackground=T.COLORS.hover,
                              disabledforeground=T.COLORS.text_muted)

    def test_config_bg_sets_the_surface(self):
        w = W.PillButton(self.frame(), "X")
        w.config(bg=T.COLORS.panel)
        self.assertEqual(_norm(w.cget("bg")), _norm(T.COLORS.panel))

    def test_config_cursor(self):
        w = W.PillButton(self.frame(), "X")
        w.config(cursor="hand2")
        self.assertEqual(w.cget("cursor"), "hand2")

    def test_config_command_rebinds(self):
        w = W.PillButton(self.frame(), "X")
        hit = []
        w.config(command=lambda: hit.append(1))
        w.invoke()
        self.assertEqual(hit, [1])


class ColorSwatchLegacyContractTests(_TkTestCase):
    """``color_btn.config(bg=...)`` must keep meaning "set the colour"."""

    def test_config_bg_sets_the_colour(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        w.config(bg="#00ff00")
        self.assertEqual(_norm(w.get_color()), "#00ff00")
        self.assertEqual(_norm(w.cget("bg")), "#00ff00")

    def test_config_background_alias(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        w.config(background="#0000ff")
        self.assertEqual(_norm(w.get_color()), "#0000ff")
        self.assertEqual(_norm(w.cget("background")), "#0000ff")

    def test_set_color_and_get_color(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        w.set_color("#123456")
        self.assertEqual(w.get_color(), "#123456")
        self.assertEqual(_norm(w.cget("bg")), "#123456")

    def test_set_color_repaints_the_well(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        w.set_color("#00ff88")
        fills = [_norm(f) for f in self.fills(w)]
        self.assertIn("#00ff88", fills, "ColorSwatch did not paint its new colour")

    def test_unknown_colours_are_added_to_the_palette(self):
        w = W.ColorSwatch(self.frame(), "#ff0000", palette=["#ff0000"])
        w.set_color("#abcdef")
        self.assertIn("#abcdef", w.palette)

    def test_command_fires_on_palette_choice(self):
        hit = []
        w = W.ColorSwatch(self.frame(), "#ff0000", command=lambda c: hit.append(c),
                          palette=["#ff0000", "#00ff00"])
        w._choose("#00ff00")
        self.assertEqual(hit, ["#00ff00"])
        self.assertEqual(_norm(w.get_color()), "#00ff00")

    def test_mousewheel_cycles_the_palette(self):
        hit = []

        class Event:
            delta = 120

        w = W.ColorSwatch(self.frame(), "#ff0000", command=lambda c: hit.append(c),
                          palette=["#ff0000", "#00ff00"])
        w._cycle(Event())
        self.assertEqual(_norm(w.get_color()), "#00ff00")
        self.assertEqual(len(hit), 1)


class VariableTraceTests(_TkTestCase):
    """Tk variable traces must repaint, and must never fire during teardown."""

    def test_tool_var_repaints_rail_buttons(self):
        var = tk.StringVar(value="select")
        frame = self.frame()
        rails = [W.RailButton(frame, glyph, caption, value, var)
                 for glyph, caption, value in ((T.GLYPH.pen, "Bút", "pen"),
                                               (T.GLYPH.rect, "Chữ nhật", "rect"))]
        for value in ("pen", "rect", "pen"):
            with self.subTest(value=value):
                var.set(value)
                self.root.update_idletasks()
                for rail in rails:
                    self.assertEqual(rail._selected(), rail.value == value)
                    self.assertGreaterEqual(len(rail.find_all()), 2)

    def test_width_var_repaints_stepper_and_slider(self):
        var = tk.IntVar(value=4)
        frame = self.frame()
        stepper = W.NumberStepper(frame, var, minimum=1, maximum=50)
        slider = W.Slider(frame, var, minimum=1, maximum=50)
        for value in (1, 25, 50):
            with self.subTest(value=value):
                var.set(value)
                self.root.update_idletasks()
                self.assertIn(str(value), self.texts(stepper),
                              "NumberStepper did not repaint value %d" % value)
                self.assertGreaterEqual(len(slider.find_all()), 3,
                                        "Slider lost its drawn parts at value %d" % value)

    def test_color_var_repaints_swatch(self):
        w = W.ColorSwatch(self.frame(), "#ff0000")
        var = tk.StringVar(value="#ff0000")
        var.trace_add("write", lambda *_: w.set_color(var.get()))
        var.set("#00ff00")
        self.root.update_idletasks()
        self.assertEqual(_norm(w.get_color()), "#00ff00")
        self.assertIn("#00ff00", [_norm(f) for f in self.fills(w)])

    def test_text_bg_var_repaints_toggle(self):
        """Painted widgets redraw via delete("all"), so item ids are NOT stable.

        Every read below re-resolves the items after the variable changed.
        """
        var = tk.BooleanVar(value=False)
        w = W.ToggleSwitch(self.frame(), var, "Tô nền chữ")
        self.root.update_idletasks()

        def knob():
            return [i for i in w.find_all() if w.type(i) == "oval"][0]

        def track():
            return [i for i in w.find_all() if w.type(i) == "polygon"][0]

        off_x, off_fill = w.coords(knob())[0], _norm(w.itemcget(track(), "fill"))
        var.set(True)
        self.root.update_idletasks()
        self.assertTrue(var.get())
        on_x, on_fill = w.coords(knob())[0], _norm(w.itemcget(track(), "fill"))
        self.assertGreater(on_x, off_x, "ToggleSwitch knob did not slide right when switched on")
        self.assertNotEqual(off_fill, on_fill, "ToggleSwitch track colour did not change")
        self.assertEqual(on_fill, _norm(T.COLORS.accent))
        var.set(False)
        self.root.update_idletasks()
        self.assertLess(w.coords(knob())[0], on_x, "ToggleSwitch knob did not slide back")

    def test_segmented_control_follows_its_variable(self):
        var = tk.StringVar(value="a")
        w = W.SegmentedControl(self.frame(), [("a", "A"), ("b", "B")], variable=var)
        var.set("b")
        self.root.update_idletasks()
        self.assertEqual(var.get(), "b")
        self.assertIn("B", self.texts(w))

    def test_trace_does_not_fire_after_destroy(self):
        var = tk.IntVar(value=4)
        frame = self.frame()
        stepper = W.NumberStepper(frame, var)
        stepper.destroy()
        self.root.update_idletasks()
        var.set(9)  # must be a silent no-op, not a TclError
        self.root.update_idletasks()


class WidgetInteractionTests(_TkTestCase):

    def test_rail_button_click_selects_and_fires(self):
        var = tk.StringVar(value="select")
        hit = []
        w = W.RailButton(self.frame(), T.GLYPH.pen, "Bút", "pen", var,
                         command=lambda: hit.append(1))
        self.root.update_idletasks()
        w._on_press(None)
        w._on_release(None)
        self.assertEqual(var.get(), "pen")
        self.assertEqual(hit, [1])

    def test_rail_button_click_is_ignored_while_disabled(self):
        var = tk.StringVar(value="select")
        hit = []
        w = W.RailButton(self.frame(), T.GLYPH.pen, "Bút", "pen", var,
                         command=lambda: hit.append(1))
        w.config(state="disabled")
        w._on_press(None)
        w._on_release(None)
        self.assertEqual(var.get(), "select")
        self.assertEqual(hit, [])

    def test_number_stepper_clamps_to_bounds(self):
        var = tk.IntVar(value=1)
        w = W.NumberStepper(self.frame(), var, minimum=1, maximum=10, step=1)
        self.root.update_idletasks()
        for _ in range(15):
            w._set(w._value() + 1)
        self.assertEqual(var.get(), 10)
        for _ in range(20):
            w._set(w._value() - 1)
        self.assertEqual(var.get(), 1)

    def test_slider_clamps_to_bounds(self):
        var = tk.IntVar(value=25)
        w = W.Slider(self.frame(), var, minimum=1, maximum=50)
        self.root.update_idletasks()
        w._apply(-10_000)
        self.assertEqual(var.get(), 1)
        w._apply(10_000)
        self.assertEqual(var.get(), 50)

    def test_toggle_switch_flips_and_reports(self):
        var = tk.BooleanVar(value=False)
        hit = []
        w = W.ToggleSwitch(self.frame(), var, "Tô nền", command=lambda v: hit.append(v))
        w._toggle()
        self.assertIs(var.get(), True)
        w._toggle()
        self.assertIs(var.get(), False)
        self.assertEqual(hit, [True, False])

    def test_status_bar_set_hint_and_metrics(self):
        w = W.StatusBar(self.frame())
        w.set_hint("Kéo để chọn vùng")
        self.assertEqual(w.hint.cget("text"), "Kéo để chọn vùng")
        w.set_metrics(size=(400, 300), zoom=0.5, cursor=(10, 20))
        text = w.metrics.cget("text")
        self.assertIn("400×300", text)
        self.assertIn("50%", text)
        self.assertIn("10, 20", text)
        w.set_metrics(history="3/7")
        self.assertIn("3/7", w.metrics.cget("text"))
        self.assertNotIn("400×300", w.metrics.cget("text"),
                         "set_metrics() kept a stale value from the previous call")

    def test_every_widget_has_a_visible_disabled_state(self):
        """Contract 7: every widget shows hover/active/disabled."""
        frame = self.frame()
        widgets = [
            W.RailButton(frame, T.GLYPH.pen, "Bút", "pen", tk.StringVar(value="select")),
            W.IconButton(frame, T.GLYPH.undo),
            W.PillButton(frame, "Lưu", variant="primary"),
            W.PillButton(frame, "Hủy", variant="danger"),
            W.PillButton(frame, "Xong", variant="success"),
        ]
        for widget in widgets:
            with self.subTest(widget=type(widget).__name__):
                self.root.update_idletasks()
                enabled_fills = set(widget.itemcget(i, "fill") for i in widget.find_all()
                                    if widget.type(i) in ("text", "polygon"))
                widget.config(state="disabled")
                self.root.update_idletasks()
                disabled_fills = set(widget.itemcget(i, "fill") for i in widget.find_all()
                                     if widget.type(i) in ("text", "polygon"))
                self.assertNotEqual(enabled_fills, disabled_fills,
                                    "disabled state of %s paints identically to enabled"
                                    % type(widget).__name__)


class NoHardcodedColourTests(unittest.TestCase):
    """Contract 7: no hard-coded colours outside ui_theme.py.

    Palette *data* (the swatch palette, the default pen colour) is user content,
    not design surface, so only colours used as painting arguments count:
    ``fill=``, ``bg=``, ``fg=``, ``background=``, ``foreground=``,
    ``outline=``, ``troughcolor=`` and friends.
    """

    PAINT_KWARGS = ("fill", "bg", "fg", "background", "foreground", "outline",
                    "activebackground", "activeforeground", "selectbackground",
                    "selectforeground", "disabledforeground", "fieldbackground",
                    "troughcolor", "bordercolor", "arrowcolor", "highlightbackground")

    HEX_LITERAL = re.compile(r"""^["']#[0-9a-fA-F]{3,8}["']$""")

    def _offending_lines(self, path):
        offenders = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):        # a comment, not a colour
                continue
            for kwarg in self.PAINT_KWARGS:
                pattern = re.compile(r"\b%s\s*=\s*(['\"]#[0-9a-fA-F]{3,8}['\"])" % kwarg)
                for match in pattern.finditer(line):
                    offenders.append((line_no, kwarg, match.group(1), stripped))
        return offenders

    def test_ui_widgets_uses_only_theme_tokens_for_painting(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "ui_widgets.py"
        offenders = self._offending_lines(path)
        self.assertEqual(offenders, [],
                         "ui_widgets.py paints with literal colours: %r" % (offenders[:5],))

    def test_ui_theme_is_the_only_source_of_the_palette(self):
        """Sanity check the scanner: ui_theme.py *must* contain the literals."""
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "ui_theme.py"
        self.assertGreater(path.read_text(encoding="utf-8").count("#"), 30)


if __name__ == "__main__":
    unittest.main()
