import ast
import unittest
from pathlib import Path


class TestContextualIntervalLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls._interval_label_fn = cls._load_interval_label_function()

    @classmethod
    def _load_interval_label_function(cls):
        labels_source = ""
        function_source = ""
        for node in cls.tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "INTERVAL_LABELS":
                        labels_source = ast.get_source_segment(cls.source, node) or ""
            if isinstance(node, ast.FunctionDef) and node.name == "interval_label_for_context":
                function_source = ast.get_source_segment(cls.source, node) or ""
        namespace = {}
        exec("from typing import Optional, Set\n" + labels_source + "\n" + function_source, namespace)
        return namespace["interval_label_for_context"]

    def interval_label_for_context(self, interval, present_intervals, chord_name=""):
        return self.__class__._interval_label_fn(interval, present_intervals, chord_name)

    def test_second_labels_follow_chord_context(self) -> None:
        self.assertEqual(self.interval_label_for_context(1, {0, 1, 4, 7}, "7(b9)"), "9m")
        self.assertEqual(self.interval_label_for_context(2, {0, 2, 7}, "sus2"), "sus2")
        self.assertEqual(self.interval_label_for_context(2, {0, 2, 4, 7}, "add2"), "9M")
        self.assertEqual(self.interval_label_for_context(2, {0, 2, 5, 7}, "13sus4"), "9M")

    def test_minor_third_becomes_sharp_nine_when_major_third_is_present(self) -> None:
        self.assertEqual(self.interval_label_for_context(3, {0, 3, 7}, "m"), "3m")
        self.assertEqual(self.interval_label_for_context(3, {0, 3, 4, 10}, "7(#9)"), "9+")

    def test_perfect_fourth_becomes_eleventh_when_chord_symbol_shows_eleventh(self) -> None:
        self.assertEqual(self.interval_label_for_context(5, {0, 5, 7}, "sus4"), "4j")
        self.assertEqual(self.interval_label_for_context(5, {0, 3, 5, 7, 10}, "m11"), "11j")
        self.assertEqual(self.interval_label_for_context(5, {0, 2, 5, 7, 10, 9}, "13sus4"), "4j")

    def test_tritone_prefers_chord_spelling_then_structure(self) -> None:
        self.assertEqual(self.interval_label_for_context(6, {0, 3, 6, 10}, "m7(b5)"), "5b")
        self.assertEqual(self.interval_label_for_context(6, {0, 4, 6, 10}, "9(#11)"), "11+")
        self.assertEqual(self.interval_label_for_context(6, {0, 4, 6, 10}, "7(b5)"), "5b")

    def test_augmented_fifth_becomes_flat_thirteen_when_fifth_is_present(self) -> None:
        self.assertEqual(self.interval_label_for_context(8, {0, 4, 8}, "+"), "5+")
        self.assertEqual(self.interval_label_for_context(8, {0, 4, 7, 8, 10}, "7(b13)"), "13m")
        self.assertEqual(self.interval_label_for_context(8, {0, 4, 6, 8, 10}, "7(b5)b13"), "13m")

    def test_major_sixth_and_diminished_seventh_are_not_collapsed(self) -> None:
        self.assertEqual(self.interval_label_for_context(9, {0, 4, 7, 9}, "6"), "6")
        self.assertEqual(self.interval_label_for_context(9, {0, 3, 6, 9}, "º7"), "7b")
        self.assertEqual(self.interval_label_for_context(9, {0, 4, 7, 9, 10}, "13"), "13")


class TestPreloadedChordIntervalLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from pathlib import Path
        import ast

        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _class_method_source(self, class_name: str, method_name: str) -> str:
        import ast

        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.get_source_segment(self.source, item) or ""
        return ""

    def test_preloaded_chord_overlay_generates_interval_labels_without_note_on(self) -> None:
        overlay_source = self._class_method_source("ControlWindow", "_update_display_overlays")
        interval_source = self._class_method_source("ControlWindow", "_update_interval_labels")

        self.assertIn("chord_interval_labels: Dict[int, str] = {}", overlay_source)
        self.assertIn("self.display_chord_interval_labels = chord_interval_labels", overlay_source)
        self.assertIn("if not self._effective_visual_notes():", overlay_source)
        self.assertIn("self.piano.set_interval_labels(dict(self.display_chord_interval_labels))", overlay_source)
        self.assertIn("self.piano.set_interval_labels(dict(self.display_chord_interval_labels))", interval_source)


if __name__ == "__main__":
    unittest.main()
