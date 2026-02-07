import ast
import unittest
from pathlib import Path


class TestNoQMessageBox(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_qmessagebox_is_not_imported_or_used(self) -> None:
        self.assertNotIn("QMessageBox", self.source)

    def test_non_modal_feedback_helpers_exist(self) -> None:
        method_names = set()
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "ControlWindow":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_names.add(item.name)
        self.assertIn("_show_status_message", method_names)
        self.assertIn("_confirm_action", method_names)


if __name__ == "__main__":
    unittest.main()

