import ast
import unittest
from pathlib import Path


class TestWindowDragDetach(unittest.TestCase):
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

    def test_piano_window_can_remove_drag_support(self) -> None:
        remove_source = self._class_method_source("PianoWindow", "_remove_drag_support")
        self.assertIn("removeEventFilter", remove_source)

    def test_set_view_mode_detaches_keyboard_drag_filter_from_child_windows(self) -> None:
        set_view_mode_source = self._class_method_source("ControlWindow", "set_view_mode")
        self.assertIn("self.piano_window._remove_drag_support(self.staff_window.widget)", set_view_mode_source)
        self.assertIn(
            "self.piano_window._remove_drag_support(self.chord_window.display_widget)",
            set_view_mode_source,
        )


if __name__ == "__main__":
    unittest.main()

