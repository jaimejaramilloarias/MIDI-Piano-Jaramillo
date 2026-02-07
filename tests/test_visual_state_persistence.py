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

    def test_visual_state_tracking_is_enabled_after_startup_defaults(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")

        self.assertIn("self._visual_state_tracking_enabled = False", init_source)
        defaults_index = init_source.find("self._apply_startup_defaults()")
        enable_index = init_source.find("self._visual_state_tracking_enabled = True")

        self.assertNotEqual(defaults_index, -1)
        self.assertNotEqual(enable_index, -1)
        self.assertGreater(enable_index, defaults_index)

    def test_visual_state_save_methods_guard_during_startup(self) -> None:
        schedule_source = self._class_method_source("ControlWindow", "_schedule_visual_state_save")
        persist_source = self._class_method_source("ControlWindow", "_persist_visual_state")

        self.assertIn("if not self._visual_state_tracking_enabled or self._is_closing:", schedule_source)
        self.assertIn("if not force and (not self._visual_state_tracking_enabled or self._is_closing):", persist_source)

    def test_persist_on_close_forces_save(self) -> None:
        install_source = self._class_method_source("ControlWindow", "_install_visual_state_tracking")
        close_source = self._class_method_source("ControlWindow", "_persist_preferences_on_close")

        self.assertIn("app.aboutToQuit.connect(self._persist_preferences_on_close)", install_source)
        self.assertIn("self._is_closing = True", close_source)
        self.assertIn("self._persist_visual_state(force=True)", close_source)


    def test_default_appearance_can_be_saved_from_controls_menu(self) -> None:
        controls_source = self._class_method_source("ControlWindow", "_setup_controls_menu")

        self.assertIn("Guardar apariencia actual como predeterminada", controls_source)
        self.assertIn("save_default_appearance", controls_source)

    def test_default_appearance_button_saves_full_preferences_payload(self) -> None:
        save_source = self._class_method_source("ControlWindow", "save_default_appearance")

        self.assertIn("self._write_preferences(True)", save_source)

    def test_default_appearance_is_loaded_during_startup(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")

        self.assertIn("self.load_preferences()", init_source)


    def test_default_appearance_uses_existing_widget_apis(self) -> None:
        appearance_source = self._class_method_source("ControlWindow", "_apply_appearance_payload")

        self.assertIn("self.piano.base_color = QColor(*rgba)", appearance_source)
        self.assertIn("self.piano.update()", appearance_source)
        self.assertIn("set_chord_color", appearance_source)
        self.assertNotIn("set_base_color", appearance_source)
        self.assertNotIn("set_text_color", appearance_source)

    def test_save_preferences_button_is_removed(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")

        self.assertNotIn('QPushButton("Guardar preferencias")', init_source)
        self.assertNotIn("self.save_button", init_source)



    def test_compatibility_aliases_exist_for_appearance_setters(self) -> None:
        piano_source = self._class_method_source("PianoWidget", "set_base_color")
        chord_window_source = self._class_method_source("ChordWindow", "set_text_color")

        self.assertIn("self.base_color = QColor(color)", piano_source)
        self.assertIn("self.set_chord_color(color)", chord_window_source)

if __name__ == "__main__":
    unittest.main()
