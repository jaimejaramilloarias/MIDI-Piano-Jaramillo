import ast
import unittest
from pathlib import Path


class TestSingleWindowKeyboardNavigation(unittest.TestCase):
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

    def test_double_click_toggles_single_window_fullscreen(self) -> None:
        piano_widget_source = self._class_source("PianoWidget")
        piano_window_source = self._class_source("PianoWindow")
        control_init_source = self._class_method_source("ControlWindow", "__init__")
        toggle_source = self._class_method_source(
            "ControlWindow", "_toggle_single_fullscreen_from_double_click"
        )

        self.assertIn("mouseDoubleClickEvent", piano_widget_source)
        self.assertIn("mouseDoubleClickEvent", piano_window_source)
        self.assertIn("self.piano.on_double_click", control_init_source)
        self.assertIn("self.piano_window.on_double_click", control_init_source)
        self.assertIn('if self.view_mode != "single":', toggle_source)
        self.assertIn("self.single_fullscreen_action.setChecked", toggle_source)

    def test_single_window_has_bottom_keyboard_navigation_panel(self) -> None:
        build_source = self._class_method_source("ControlWindow", "_build_keyboard_navigation_panel")
        set_view_mode_source = self._class_method_source("ControlWindow", "set_view_mode")
        piano_window_source = self._class_method_source("PianoWindow", "show_combined_view")

        self.assertIn("single_octave_down_button", build_source)
        self.assertIn("single_octaves_minus_button", build_source)
        self.assertIn("single_octaves_button", build_source)
        self.assertIn("single_octaves_plus_button", build_source)
        self.assertIn("single_octave_up_button", build_source)
        self.assertIn("keyboard_nav_panel", set_view_mode_source)
        self.assertIn("layout.addWidget(keyboard_nav_panel)", piano_window_source)
        self.assertIn("self.piano.setMinimumHeight(220)", piano_window_source)
        self.assertIn("self._apply_frameless(False)", piano_window_source)
        self.assertNotIn("self.resize(1280, 900)", piano_window_source)

    def test_startup_ignores_saved_separate_view_mode(self) -> None:
        appearance_source = self._class_method_source("ControlWindow", "_apply_appearance_payload")
        preferences_source = self._class_method_source("ControlWindow", "load_preferences")

        self.assertIn("self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)", appearance_source)
        self.assertNotIn("self.set_view_mode(str(saved_view_mode), persist=False)", appearance_source)
        self.assertIn("self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)", preferences_source)
        self.assertNotIn("self.set_view_mode(str(saved_view_mode), persist=False)", preferences_source)

    def test_keyboard_navigation_uses_a0_then_c2_sequence_and_plus_minus(self) -> None:
        starts_source = self._class_method_source("ControlWindow", "_single_window_start_notes")
        change_source = self._class_method_source("ControlWindow", "_change_visible_octaves")
        shift_source = self._class_method_source("ControlWindow", "_shift_visible_keyboard_octave")
        connect_source = self._class_method_source("ControlWindow", "_connect_keyboard_navigation_signals")
        range_source = self._class_method_source("ControlWindow", "range_changed")

        self.assertIn("[MIN_NOTE] + [midi_of_C(octave) for octave in range(2, 8)]", starts_source)
        self.assertIn("current + int(delta)", change_source)
        self.assertIn("max(1, min(7", change_source)
        self.assertIn("_coerce_start_for_visible_octaves", change_source)
        self.assertIn("_change_visible_octaves(-1)", connect_source)
        self.assertIn("_change_visible_octaves(1)", connect_source)
        self.assertIn("_single_window_start_notes(int(self.octaves_spin.value()))", shift_source)
        self.assertIn("fit_window: bool = False", range_source)
        self.assertIn("self.range_changed()", shift_source)
        self.assertIn("self.range_changed()", change_source)
        self.assertNotIn("fit_window=True", shift_source)
        self.assertNotIn("fit_window=True", change_source)

    def test_single_window_resizes_only_from_manual_paths(self) -> None:
        piano_source = self._class_method_source("PianoWidget", "mouseMoveEvent")
        combined_source = self._class_method_source("PianoWindow", "show_combined_view")
        fit_source = self._class_method_source("ControlWindow", "_fit_keyboard_window_to_available_width")
        rearrange_source = self._class_method_source("ControlWindow", "rearrange_windows")

        self.assertIn("if self._resizing", piano_source)
        self.assertIn("self.window().resize(new_width, new_height)", piano_source)
        self.assertNotIn("resize(1280, 900)", combined_source)
        self.assertIn('if self.view_mode == "single":', fit_source)
        self.assertIn('if self.view_mode == "single":\n            return', fit_source)
        single_branch = rearrange_source.split('if self.view_mode == "single":', 1)[1].split("else:", 1)[0]
        self.assertNotIn("setGeometry", single_branch)


if __name__ == "__main__":
    unittest.main()
