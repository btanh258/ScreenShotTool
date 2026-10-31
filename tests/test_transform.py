import importlib.util
import unittest
import tempfile
import json
from pathlib import Path
from PIL import Image
from hotkey_settings import _record_key, _validate


MODULE_PATH = Path(__file__).parents[1] / "ScreenShotTool.pyw"
spec = importlib.util.spec_from_file_location("screenshot_tool", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TransformTests(unittest.TestCase):
    def editor(self):
        editor = module.ImageEditor.__new__(module.ImageEditor)
        editor.pil_image = Image.new("RGBA", (3, 2), (10, 20, 30, 255))
        editor.orig_w, editor.orig_h = editor.pil_image.size
        editor.shapes = []
        editor.selected_tag = None
        editor.text_entry = None
        editor.render_final_image = lambda: editor.pil_image.copy()
        editor.clear_selection = lambda: None
        editor.redraw_all = lambda: None
        editor.save_state = lambda: None
        return editor

    def test_malformed_config_falls_back_to_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            handle.write("{not-json")
            path = handle.name
        old_primary, old_legacy = module.CONFIG_FILE, module.LEGACY_CONFIG_FILE
        try:
            module.CONFIG_FILE = path
            module.LEGACY_CONFIG_FILE = path + ".missing"
            config = module.load_config()
            self.assertEqual(config["color"], "#ff0000")
            self.assertEqual(config["width"], 4)
            self.assertEqual(config["capture_hotkey"], "Alt+X")
        finally:
            module.CONFIG_FILE, module.LEGACY_CONFIG_FILE = old_primary, old_legacy
            Path(path).unlink(missing_ok=True)

    def test_rotate_swaps_dimensions_and_preserves_alpha(self):
        editor = self.editor()
        editor.transform_document("rotate_cw")
        self.assertEqual(editor.pil_image.size, (2, 3))
        self.assertEqual(editor.pil_image.mode, "RGBA")

    def test_erase_pixels_preserves_annotation_model(self):
        editor = self.editor()
        editor.shapes = [{'tag': 'a', 'type': 'rect', 'coords': [0, 0, 2, 2], 'width': 1, 'color': '#f00'}]
        editor.erase_pixels((0, 0, 1, 1))
        self.assertEqual(len(editor.shapes), 1)
        self.assertEqual(editor.pil_image.mode, 'RGBA')
        self.assertEqual(editor.pil_image.getpixel((0, 0))[3], 0)

    def test_move_selected_group_updates_all_coordinates(self):
        editor = self.editor()
        editor.selected_tags = ['a', 'b']
        editor.selected_tag = 'a'
        editor.draw_selection_box = lambda: None
        editor.redraw_all = lambda: None
        editor.shapes = [
            {'tag': 'a', 'type': 'rect', 'coords': [1, 2, 3, 4], 'width': 1, 'color': '#f00'},
            {'tag': 'b', 'type': 'oval', 'coords': [5, 6, 7, 8], 'width': 1, 'color': '#0f0'},
        ]
        editor.move_selected_by(2, -1)
        self.assertEqual(editor.shapes[0]['coords'], [3, 1, 5, 3])
        self.assertEqual(editor.shapes[1]['coords'], [7, 5, 9, 7])

    def test_document_transform_keeps_annotations_selectable(self):
        editor = self.editor()
        shape = {"tag": "shape_1", "type": "arrow", "coords": [0, 0, 2, 1], "width": 1, "color": "#f00"}
        editor.shapes = [shape]
        editor.transform_document("rotate_cw")
        self.assertEqual(editor.pil_image.size, (2, 3))
        self.assertEqual(shape["coords"], [2, 0, 1, 2])

    def test_selected_shape_flip_maps_points(self):
        editor = self.editor()
        editor.selected_tag = "shape_1"
        shape = {"tag": "shape_1", "type": "arrow", "coords": [10, 20, 30, 40], "width": 3, "color": "#f00"}
        editor.shapes = [shape]
        editor.transform_selection_or_document("flip_h")
        self.assertEqual(shape["coords"], [30.0, 20.0, 10.0, 40.0])

    def test_hotkey_settings_accepts_delete_and_modifiers(self):
        self.assertEqual(_validate('Delete', require_modifier=False), 'DELETE')
        self.assertIsNone(_validate('Delete'))
        self.assertEqual(_validate('Ctrl+Z'), 'CTRL+Z')

    def test_hotkey_listener_records_key_combination(self):
        class Entry:
            def __init__(self): self.value = ''
            def delete(self, start, end): self.value = ''
            def insert(self, index, value): self.value = value
        class Event:
            state = 0x0004 | 0x0001
            keysym = 's'
        entry = Entry()
        _record_key(Event(), entry)
        self.assertEqual(entry.value, 'Ctrl+Shift+S')

    def test_text_colors_normalize_for_preview_and_export(self):
        editor = self.editor()
        editor.top = type("Top", (), {"winfo_rgb": lambda self, color: (0x1212, 0x3434, 0x5656)})()
        fg, bg = editor._text_colors("#123456", True)
        self.assertEqual(bg, "#123456")
        self.assertEqual(fg, "#ffffff")

    def test_hotkey_parser_accepts_and_rejects_values(self):
        self.assertEqual(module.parse_hotkey("Ctrl+Shift+S"), (6, 83))
        self.assertIsNone(module.validate_hotkey("Alt"))
        self.assertIsNone(module.validate_hotkey("Ctrl+Ctrl+S"))

    def test_oval_renders_to_rgba_image(self):
        editor = self.editor()
        editor.shapes = [{"tag": "shape_1", "type": "oval", "coords": [0, 0, 2, 1], "width": 1, "color": "#ff0000"}]
        result = editor.render_final_image()
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, (3, 2))
        self.assertTrue(any(result.getpixel((x, y))[0] > 0 for x in range(result.width) for y in range(result.height)))

    def test_text_becomes_transformable_bitmap(self):
        editor = self.editor()
        editor.top = type("Top", (), {"winfo_rgb": lambda self, color: (0, 0, 0)})()
        editor.selected_tag = "text_1"
        shape = {"tag": "text_1", "type": "text", "coords": [10, 10], "width": 4, "color": "#000000", "text": "Hi", "bg_enabled": False}
        editor.shapes = [shape]
        editor.transform_selection_or_document("rotate_cw")
        self.assertEqual(shape["type"], "bitmap")
        self.assertGreater(shape["orig_pil_img"].width, 0)


if __name__ == "__main__":
    unittest.main()
