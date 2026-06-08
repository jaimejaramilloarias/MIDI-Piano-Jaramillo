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

    def test_display_menus_use_inline_comboboxes_for_selection(self) -> None:
        setup_source = self._class_method_source("ControlWindow", "_setup_display_menus")
        self.assertIn("chord_row1.addWidget(self.display_chord_combo)", setup_source)
        self.assertIn("scale_row.addWidget(self.display_scale_combo)", setup_source)
        self.assertNotIn("display_chord_popup_button", setup_source)
        self.assertNotIn("display_scale_popup_button", setup_source)

    def test_panel_selection_changes_activate_display_modes(self) -> None:
        connect_source = self._class_method_source("ControlWindow", "_connect_display_panel_signals")
        chord_handler = self._class_method_source("ControlWindow", "_handle_panel_chord_selection_changed")
        scale_handler = self._class_method_source("ControlWindow", "_handle_panel_scale_selection_changed")

        self.assertIn("_handle_panel_chord_selection_changed", connect_source)
        self.assertIn("_handle_panel_scale_selection_changed", connect_source)
        self.assertIn("_set_display_enabled_from_selection(\"chord\")", chord_handler)
        self.assertIn("_set_display_enabled_from_selection(\"scale\")", scale_handler)

    def test_visualization_panel_is_not_in_inline_console(self) -> None:
        panel_source = self._class_method_source("ControlWindow", "_build_display_panel")

        self.assertNotIn("display_panel_keyboard_labels", panel_source)
        self.assertNotIn("display_panel_capture_spin", panel_source)
        self.assertNotIn("display_panel_edit_chords", panel_source)
        self.assertNotIn("display_panel_midi_learn", panel_source)
        self.assertNotIn("display_panel_single_bg_button", panel_source)

    def test_midi_learn_input_uses_foreground_prompt(self) -> None:
        method_source = self._class_method_source("ControlWindow", "_complete_learning_with_notes")
        self.assertIn("self._prompt_text_foreground", method_source)


if __name__ == "__main__":
    unittest.main()
