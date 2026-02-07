import ast
import unittest
from pathlib import Path


class TestMenuComboBehavior(unittest.TestCase):
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

    def test_menu_combo_enables_hover_feedback_and_closing(self) -> None:
        combo_source = self._class_source("MenuComboBox")
        self.assertIn("setMouseTracking(True)", combo_source)
        self.assertIn("WA_Hover", combo_source)
        self.assertIn("QListView::item:hover", combo_source)
        self.assertIn("activated.connect", combo_source)
        self.assertIn("QTimer.singleShot", combo_source)
        self.assertIn("menu.close", combo_source)

    def test_persistent_menu_tracks_combo_popup(self) -> None:
        menu_source = self._class_source("PersistentMenu")
        self.assertIn("_combo_popup_open", menu_source)
        self.assertIn("focusOutEvent", menu_source)
        self.assertIn("mousePressEvent", menu_source)


if __name__ == "__main__":
    unittest.main()
