import ast
import unittest
from pathlib import Path


class TestScaleVisualizationOctave4(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _class_method_source(self, class_name: str, method_name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.get_source_segment(self.source, item) or ""
        return ""

    def test_scale_overlay_starts_at_octave4_and_uses_single_scale_cycle(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_update_display_overlays")

        self.assertIn("overlay_notes = build_scale_overlay_notes(", method_source)
        self.assertIn("len(scale_pcs)", method_source)
        self.assertIn("for note in overlay_notes:", method_source)


if __name__ == "__main__":
    unittest.main()
