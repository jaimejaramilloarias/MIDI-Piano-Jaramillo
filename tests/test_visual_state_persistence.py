import ast
import unittest
from pathlib import Path


class TestVisualStatePersistence(unittest.TestCase):
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

    def test_control_window_has_single_event_filter_definition(self) -> None:
        count = 0
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "ControlWindow":
                count = sum(
                    1
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name == "eventFilter"
                )
        self.assertEqual(count, 1)

    def test_event_filter_saves_visual_state_and_updates_actions(self) -> None:
        method_source = self._class_method_source("ControlWindow", "eventFilter")

        self.assertIn("QEvent.Type.Move", method_source)
        self.assertIn("QEvent.Type.Resize", method_source)
        self.assertIn("self._schedule_visual_state_save()", method_source)

        self.assertIn("QEvent.Type.WindowStateChange", method_source)
        self.assertIn("QEvent.Type.Hide", method_source)
        self.assertIn("QEvent.Type.Show", method_source)
        self.assertIn("QTimer.singleShot(0, self._update_window_actions)", method_source)


if __name__ == "__main__":
    unittest.main()
