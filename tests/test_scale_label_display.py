import ast
import unittest
from pathlib import Path


class TestScaleLabelDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _class_source(self, name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return ast.get_source_segment(self.source, node) or ""
        return ""

    def _class_method_source(self, class_name: str, method_name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.get_source_segment(self.source, item) or ""
        return ""

    def test_piano_widget_draws_selected_scale_label(self) -> None:
        piano_source = self._class_source("PianoWidget")
        paint_source = self._class_method_source("PianoWidget", "paintEvent")
        draw_source = self._class_method_source("PianoWidget", "_draw_display_scale_label")

        self.assertIn("self.display_scale_label = \"\"", piano_source)
        self.assertIn("set_display_scale_label", piano_source)
        self.assertIn("_draw_display_scale_label(painter)", paint_source)
        self.assertIn("QFont(\"Avenir Next\")", draw_source)
        self.assertIn("max(15, min(26", draw_source)
        self.assertIn("drawRoundedRect", draw_source)
        self.assertIn("elidedText", draw_source)

    def test_display_overlay_updates_selection_label_for_chords_and_scales(self) -> None:
        overlay_source = self._class_method_source("ControlWindow", "_update_display_overlays")

        self.assertIn("display_label_parts: List[str] = []", overlay_source)
        self.assertIn("self.piano.set_display_scale_label(\"\")", overlay_source)
        self.assertIn("root_label = str(self.display_root_combo.currentText() or \"\").strip()", overlay_source)
        self.assertIn("chord_name = str(self.display_chord_combo.currentText() or \"\").strip()", overlay_source)
        self.assertIn("display_label_parts.append(f\"{root_label} {chord_name}\".strip())", overlay_source)
        self.assertIn("scale_name = str(self.display_scale_combo.currentText() or \"\").strip()", overlay_source)
        self.assertIn("display_label_parts.append(f\"{root_label} {scale_name}\".strip())", overlay_source)
        self.assertIn("self.piano.set_display_scale_label(\"  ·  \".join(display_label_parts))", overlay_source)

    def test_preloaded_chord_overlay_uses_green_root_and_strong_blue_notes(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")
        overlay_source = self._class_method_source("ControlWindow", "_update_display_overlays")

        self.assertIn("self.display_chord_color = QColor(0, 122, 255, 190)", init_source)
        self.assertIn("self.display_chord_root_color = QColor(52, 199, 89, 190)", init_source)
        self.assertIn("elif note % 12 == root_pc:", overlay_source)
        self.assertIn("chord_overlays[note] = QColor(self.display_chord_root_color)", overlay_source)


if __name__ == "__main__":
    unittest.main()
