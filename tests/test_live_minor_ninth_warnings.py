import ast
import unittest
from pathlib import Path


class TestLiveMinorNinthWarnings(unittest.TestCase):
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

    def test_piano_widget_can_paint_live_warning_notes(self) -> None:
        piano_source = self._class_source("PianoWidget")
        pressed_color_source = self._class_method_source("PianoWidget", "_pressed_color_for")

        self.assertIn("self.live_warning_notes", piano_source)
        self.assertIn("set_live_warning_notes", piano_source)
        self.assertIn("if note in self.live_warning_notes:", pressed_color_source)
        self.assertIn("return QColor(self.live_warning_color)", pressed_color_source)

    def test_live_midi_reuses_pregrabbed_minor_ninth_rule(self) -> None:
        helper_source = self._class_method_source("ControlWindow", "_update_live_minor_ninth_warnings")
        poll_source = self._class_method_source("ControlWindow", "poll_midi")
        refresh_source = self._class_method_source("ControlWindow", "_refresh_staff_for_current_notes")

        self.assertIn("self._find_minor_ninth_warnings", helper_source)
        self.assertIn("self.piano.set_live_warning_notes", helper_source)
        self.assertIn("self._update_live_minor_ninth_warnings(notas_para_acorde, chord_info)", poll_source)
        self.assertIn("self._update_live_minor_ninth_warnings(notes, chord_info)", refresh_source)

    def test_live_minor_ninth_warning_skips_major_third_minor_seventh_chords(self) -> None:
        find_source = self._class_method_source("ControlWindow", "_find_minor_ninth_warnings")

        self.assertIn("chord_info: Optional[Dict] = None", find_source)
        self.assertIn("if 4 in intervals and 10 in intervals:", find_source)
        self.assertIn("return set()", find_source)

    def test_minor_ninth_warning_repeats_across_successive_octaves(self) -> None:
        find_source = self._class_method_source("ControlWindow", "_find_minor_ninth_warnings")

        self.assertIn("distance = abs(notes[i] - notes[j])", find_source)
        self.assertIn("distance >= 13 and distance % 12 == 1", find_source)
        self.assertNotIn("abs(notes[i] - notes[j]) == 13", find_source)


if __name__ == "__main__":
    unittest.main()
