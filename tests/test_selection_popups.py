import ast
import unittest
from pathlib import Path


class TestSelectionPopups(unittest.TestCase):
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

    def test_display_menus_use_popup_buttons_for_selection(self) -> None:
        setup_source = self._class_method_source("ControlWindow", "_setup_display_menus")
        self.assertIn("display_chord_popup_button", setup_source)
        self.assertIn("display_scale_popup_button", setup_source)

    def test_popup_helpers_exist(self) -> None:
        run_popup_source = self._class_method_source("ControlWindow", "_run_selection_popup")
        self.assertIn("QDialog", run_popup_source)
        self.assertIn("QListWidget", run_popup_source)
        self.assertIn("WindowStaysOnTopHint", run_popup_source)

    def test_midi_learn_input_uses_foreground_prompt(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_complete_learning_with_notes")
        self.assertIn("self._prompt_text_foreground", method_source)


if __name__ == "__main__":
    unittest.main()

