import ast
import json
from pathlib import Path
import unittest


class SourceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.source = (cls.root / "main.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    @classmethod
    def function_source(cls, name: str) -> str:
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(cls.source, node) or ""
        raise AssertionError(f"No se encontro la funcion {name}")

    @classmethod
    def _class_source(cls, class_name: str) -> str:
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return ast.get_source_segment(cls.source, node) or ""
        raise AssertionError(f"No se encontro la clase {class_name}")

    @classmethod
    def class_method_source(cls, class_name: str, method_name: str) -> str:
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.get_source_segment(cls.source, item) or ""
        raise AssertionError(f"No se encontro {class_name}.{method_name}")


class TestDictionaryAndSimpleLiveLabels(SourceTestCase):
    def test_base_dictionary_reads_root_major_third_minor_seventh_as_dominant_seventh(self) -> None:
        dictionary = json.loads((self.root / "diccionario_acordes.json").read_text(encoding="utf-8"))
        entries = dictionary.get("chords", [])
        self.assertTrue(
            any(
                entry.get("nombre") == "7"
                and entry.get("obligatorias") == [0, 4, 10]
                and entry.get("opcionales") == []
                for entry in entries
            )
        )
        self.assertIn("{'nombre':'7', 'obligatorias':[0,4,10], 'opcionales':[]}", self.source)

    def test_live_chord_display_falls_back_to_note_or_interval(self) -> None:
        helper_source = self.function_source("live_note_or_interval_label")
        update_source = self.class_method_source("ChordDisplayWidget", "update_chord")
        widget_source = self._class_source("ChordDisplayWidget")
        self.assertIn("len(ordered) == 1", helper_source)
        self.assertIn("midi_to_name(ordered[0])", helper_source)
        self.assertIn("SIMPLE_INTERVAL_LABELS", helper_source)
        self.assertIn("self.main_label.setText(live_note_or_interval_label(notas))", update_source)
        self.assertIn("setWordWrap(True)", widget_source)
        self.assertIn("_format_alternative_chords(alternativos)", update_source)
        self.assertIn('+"\\n"+', self.source.replace(" ", ""))

    def test_dictionary_and_learning_actions_remain_in_menus(self) -> None:
        window_menu_source = self.class_method_source("ControlWindow", "_setup_window_menu")
        controls_menu_source = self.class_method_source("ControlWindow", "_setup_controls_menu")
        self.assertIn("Aprender nuevo cifrado", window_menu_source)
        self.assertIn("Ver cifrados aprendidos", window_menu_source)
        self.assertIn("Cargar diccionario", window_menu_source)
        self.assertIn("Exportar diccionario", window_menu_source)
        self.assertIn("Panel Aprender", controls_menu_source)
        self.assertIn("Midi learn: nuevo cifrado", controls_menu_source)
        self.assertIn("_show_controls_tab", self.source)

    def test_startup_keeps_single_window_visible(self) -> None:
        ensure_source = self.class_method_source("ControlWindow", "_ensure_startup_window_visible")
        main_source = self.function_source("main")
        init_source = self.class_method_source("ControlWindow", "__init__")
        self.assertIn("QTimer.singleShot(0, self._ensure_startup_window_visible)", init_source)
        self.assertIn("area.intersects(geometry)", ensure_source)
        self.assertIn("WINDOWS_DEFAULT_WIDTH", ensure_source)
        self.assertIn("self._bring_to_front(self.piano_window)", ensure_source)
        self.assertIn("app.setFont(ui_font(10 if IS_WINDOWS else 13))", main_source)
        self.assertIn("app.setQuitOnLastWindowClosed(False)", main_source)
        self.assertIn("app.piano_window = piano_window", main_source)
        self.assertIn("app.chord_window = chord_window", main_source)
        self.assertIn("app.staff_window = staff_window", main_source)
        self.assertNotIn("app.setQuitOnLastWindowClosed(True)", main_source)

    def test_midi_learn_opens_clear_non_modal_instruction_window(self) -> None:
        init_source = self.class_method_source("ControlWindow", "__init__")
        start_source = self.class_method_source("ControlWindow", "start_learning_mode")
        dialog_source = self.class_method_source("ControlWindow", "_show_midi_learn_start_dialog")
        reset_source = self.class_method_source("ControlWindow", "_reset_learning_state")
        self.assertIn("self.midi_learn_help_dialog", init_source)
        self.assertIn("self._show_midi_learn_start_dialog()", start_source)
        self.assertIn("Midi learn está activo", dialog_source)
        self.assertIn("Qt.WindowModality.NonModal", dialog_source)
        self.assertIn("Cancelar aprendizaje", dialog_source)
        self.assertIn("background-color: #f7f7f8", dialog_source)
        self.assertIn("color: #1d1d1f", dialog_source)
        self.assertIn("self._close_midi_learn_start_dialog()", reset_source)

    def test_popup_input_dialogs_force_readable_contrast(self) -> None:
        popup_source = self.function_source("_prepare_popup_dialog")
        self.assertIn("dialog.setStyleSheet", popup_source)
        self.assertIn("QInputDialog", popup_source)
        self.assertIn("QLabel", popup_source)
        self.assertIn("QLineEdit", popup_source)
        self.assertIn("QPushButton", popup_source)
        self.assertIn("color: #1d1d1f", popup_source)
        self.assertIn("background-color: #ffffff", popup_source)
