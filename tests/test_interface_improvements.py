import ast
import unittest
from pathlib import Path


class TestInterfaceImprovements(unittest.TestCase):
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

    def test_compact_status_includes_credit_and_visual_save_state(self) -> None:
        status_source = self._class_method_source("ControlWindow", "_current_display_status_text")
        schedule_source = self._class_method_source("ControlWindow", "_schedule_visual_state_save")
        persist_source = self._class_method_source("ControlWindow", "_persist_visual_state")

        self.assertIn("Midi Piano Jaramillo", status_source)
        self.assertIn("self._visual_save_state = \"Guardando...\"", schedule_source)
        self.assertIn("self._visual_save_state = \"Guardado\"", persist_source)

    def test_primary_controls_are_grouped_in_tabs(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")

        self.assertIn("self.primary_controls_tabs = QTabWidget()", init_source)
        self.assertIn("self.primary_controls_tabs.addTab(midi_tab, \"MIDI\")", init_source)
        self.assertIn("self.primary_controls_tabs.addTab(keyboard_tab, \"Teclado\")", init_source)
        self.assertIn("self.primary_controls_tabs.addTab(appearance_tab, \"Apariencia\")", init_source)
        self.assertIn("self.primary_controls_tabs.addTab(learn_tab, \"Aprender\")", init_source)

    def test_single_window_uses_ipad_shell_with_legacy_instrument_widgets(self) -> None:
        display_panel_source = self._class_method_source("ControlWindow", "_build_display_panel")
        workspace_source = self._class_method_source("ControlWindow", "_build_ipad_workspace")
        play_source = self._class_method_source("ControlWindow", "_build_ipad_play_page")
        navigation_source = self._class_method_source(
            "ControlWindow", "_build_single_window_navigation_rail"
        )
        set_view_mode_source = self._class_method_source("ControlWindow", "set_view_mode")

        self.assertIn("panel.setObjectName(\"DisplayPanel\")", display_panel_source)
        self.assertIn("panel = ResponsiveWidthWidget()", display_panel_source)
        self.assertIn("class ControlWindow(ResponsiveWidthWidget):", self.source)
        self.assertIn("self.display_panel_eyebrow = QLabel(\"INSPECTOR\")", display_panel_source)
        self.assertIn("self.display_panel_title = QLabel(\"Acordes\")", display_panel_source)
        self.assertIn("self.display_panel_section_stack = QStackedWidget(panel)", display_panel_source)
        self.assertIn("self.display_panel_section_buttons = []", display_panel_source)
        self.assertIn("self.display_panel_chord_combo = QComboBox(panel)", display_panel_source)
        self.assertIn("self.display_panel_scale_combo = QComboBox(panel)", display_panel_source)
        self.assertIn("self.display_panel_scale_root_combo = QComboBox()", display_panel_source)
        self.assertIn("chord_primary_row = QGridLayout()", display_panel_source)
        self.assertIn("scale_primary_row = QGridLayout()", display_panel_source)
        self.assertIn("QLabel(\"Tipo de acorde\")", display_panel_source)
        self.assertIn("self.display_panel_chord_checkbox.hide()", display_panel_source)
        self.assertIn("self.display_panel_scale_checkbox.hide()", display_panel_source)
        self.assertIn("study_scroll = QScrollArea(panel)", display_panel_source)
        self.assertIn("_build_scale_role_palette", display_panel_source)
        self.assertNotIn("display_panel_transpose_spin", display_panel_source)
        self.assertIn("self.display_panel_status_strip.hide()", display_panel_source)
        self.assertIn("self.ipad_workspace_stack = QStackedWidget(workspace)", workspace_source)
        self.assertIn("\"dictionary\": self._build_ipad_dictionary_page()", workspace_source)
        self.assertIn("\"settings\": self._build_ipad_settings_page()", workspace_source)
        self.assertIn("\"credits\": self._build_ipad_credits_page()", workspace_source)
        self.assertIn("self._build_visual_card(left)", play_source)
        self.assertIn("self._ipad_instrument_stack", workspace_source)
        self.assertIn("NavigationRailButton", navigation_source)
        self.assertIn("self.display_panel_widget", set_view_mode_source)
        self.assertIn("self._build_ipad_workspace", set_view_mode_source)

    def test_single_window_styles_have_modern_font_and_contrast(self) -> None:
        style_source = self._class_method_source("ControlWindow", "_apply_single_view_styles")

        self.assertIn("UI_FONT_STACK", style_source)
        self.assertIn("QTabBar::tab", style_source)
        self.assertIn("QCheckBox::indicator", style_source)
        self.assertIn("background: #f6f6f7", style_source)
        self.assertIn("QPushButton#GlassSegmentButton", style_source)
        self.assertIn("QWidget#PanelPage", style_source)
        self.assertIn("qlineargradient", style_source)
        self.assertIn("background-color: rgba(240, 154, 0, 70)", style_source)
        self.assertIn("selection-background-color: #f09a00", style_source)
        self.assertIn("selection-color: #1d1d1f", style_source)
        self.assertIn("menu_panel_style", style_source)
        self.assertIn("QLabel, QCheckBox { color: #1d1d1f", style_source)
        self.assertIn("widget.setStyleSheet(menu_panel_style)", style_source)
        self.assertIn("QToolButton::menu-indicator { image: none", style_source)

    def test_windows_visual_parity_uses_platform_fonts_and_scaling(self) -> None:
        main_source = self.source
        piano_source = self._class_source("PianoWidget")
        staff_source = self._class_source("StaffWidget")
        chord_source = self._class_source("ChordDisplayWidget")
        ensure_source = self._class_method_source("ControlWindow", "_ensure_startup_window_visible")
        main_fn_source = ""
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                main_fn_source = ast.get_source_segment(self.source, node) or ""
                break

        self.assertIn("UI_FONT_FAMILY = \"Segoe UI\" if IS_WINDOWS else \"Avenir Next\"", main_source)
        self.assertIn("app.setFont(ui_font(10 if IS_WINDOWS else 13))", main_fn_source)
        self.assertIn("WINDOWS_SCALE_CIRCLE_SCALE", piano_source)
        self.assertIn("\"color_black\": QColor(Qt.GlobalColor.black)", piano_source)
        self.assertIn("WINDOWS_STAFF_GLYPH_SCALE", staff_source)
        self.assertIn("chord_scale = 0.72 if IS_WINDOWS else 1.0", chord_source)
        self.assertIn("def resizeEvent(self, event):", chord_source)
        self.assertIn("_apply_responsive_fonts", chord_source)
        self.assertIn("_fit_font_size", chord_source)
        self.assertIn("WINDOWS_DEFAULT_WIDTH", ensure_source)
        self.assertIn("too_large", ensure_source)

    def test_black_key_interval_labels_have_independent_smaller_scale(self) -> None:
        paint_source = self._class_method_source("PianoWidget", "paintEvent")
        size_source = self._class_method_source("PianoWidget", "_interval_label_font_size")

        self.assertIn("_interval_label_font_size(key_width, key_height, False)", paint_source)
        self.assertIn("_interval_label_font_size(black_width, black_height, True)", paint_source)
        self.assertIn("black_key_scale = 0.78 if is_black_key else 1.0", size_source)
        self.assertIn("0.60 if is_black_key else 0.68", size_source)
        self.assertIn("0.18 if is_black_key else 0.21", size_source)

    def test_controls_menu_does_not_embed_full_control_window(self) -> None:
        controls_source = self._class_method_source("ControlWindow", "_setup_controls_menu")

        self.assertNotIn("setDefaultWidget(self)", controls_source)
        self.assertNotIn("panel_action", controls_source)

    def test_scale_role_palette_uses_renamed_circular_categories(self) -> None:
        init_source = self._class_method_source("ControlWindow", "__init__")
        palette_source = self._class_method_source("ControlWindow", "_build_scale_role_palette")
        sync_source = self._class_method_source("ControlWindow", "_sync_scale_palette_buttons")

        self.assertIn("\"root\": \"Fundamental\"", init_source)
        self.assertIn("\"stable\": \"Estructural\"", init_source)
        self.assertIn("\"tension\": \"Tensión disponible\"", init_source)
        self.assertIn("\"critical\": \"Nota evitada\"", init_source)
        self.assertIn("button.setObjectName(\"ScaleRoleCircle\")", palette_source)
        self.assertIn("button.setFixedSize(24, 24)", palette_source)
        self.assertIn("layout = QGridLayout()", palette_source)
        self.assertIn("layout.addWidget(item, index // 2, index % 2)", palette_source)
        self.assertIn("border-radius: 12px", sync_source)

    def test_window_rearrange_presentation_and_shortcuts_exist(self) -> None:
        control_source = self._class_source("ControlWindow")
        window_menu_source = self._class_method_source("ControlWindow", "_setup_window_menu")
        view_menu_source = self._class_method_source("ControlWindow", "_setup_view_menu")

        self.assertIn("Reacomodar ventanas", window_menu_source)
        self.assertIn("Modo presentación", view_menu_source)
        self.assertIn("def rearrange_windows", control_source)
        self.assertIn("def _open_shortcuts_dialog", control_source)
        self.assertIn("QShortcut", self.source)
        self.assertIn("_sync_shortcut_action_labels", control_source)

    def test_keyboard_range_changes_have_specific_status(self) -> None:
        range_source = self._class_method_source("ControlWindow", "range_changed")
        helper_source = self._class_method_source("ControlWindow", "_update_display_overlays_with_keyboard_status")
        announce_source = self._class_method_source("ControlWindow", "_announce_keyboard_range")

        self.assertIn("_update_display_overlays_with_keyboard_status", range_source)
        self.assertIn("show_status=False", helper_source)
        self.assertIn("Teclado:", announce_source)

    def test_piano_widget_has_note_release_fade(self) -> None:
        piano_source = self._class_source("PianoWidget")
        paint_source = self._class_method_source("PianoWidget", "paintEvent")

        self.assertIn("self.base_color = QColor(240, 154, 0)", piano_source)
        self.assertIn("return QColor(self.base_color)", piano_source)
        self.assertIn("recent_released_notes", piano_source)
        self.assertIn("_advance_note_fades", piano_source)
        self.assertIn("_released_fade_color_for", piano_source)
        self.assertIn("_released_fade_color_for(n, False)", paint_source)
        self.assertIn("_released_fade_color_for(n, True)", paint_source)
        self.assertIn("key_rect.adjusted(1.0, 1.0, -1.0, -1.0)", paint_source)


if __name__ == "__main__":
    unittest.main()
