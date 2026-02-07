import ast
import unittest
from pathlib import Path


class TestMidiLearnSafeButtonUpdates(unittest.TestCase):
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

    def test_learn_button_text_uses_safe_setter(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_set_learn_button_text")
        self.assertIn("_set_button_text_safe", method_source)

    def test_safe_setter_handles_destroyed_qt_widgets(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_set_button_text_safe")
        self.assertIn("except RuntimeError", method_source)

    def test_prompt_text_foreground_exists_for_midi_learn(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_prompt_text_foreground")
        self.assertIn("QInputDialog.getText", method_source)

    def test_finish_capture_window_handles_slot_exceptions(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_finish_capture_window")
        self.assertIn("except Exception", method_source)


if __name__ == "__main__":
    unittest.main()
