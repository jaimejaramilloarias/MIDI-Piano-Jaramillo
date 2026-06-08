import ast
import unittest
from pathlib import Path


class TestScalePatternTranspositionBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(__file__).resolve().parents[1] / "main.py"
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _function_source(self, function_name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return ast.get_source_segment(self.source, node) or ""
        return ""

    def _class_method_source(self, class_name: str, method_name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.get_source_segment(self.source, item) or ""
        return ""

    def test_scale_pc_builder_exists_and_uses_transposed_root(self) -> None:
        fn = self._function_source("build_scale_pcs")
        self.assertIn("((int(root_pc) + int(transpose)) % 12)", fn)
        self.assertIn("for step in intervals[:-1]:", fn)

    def test_degree_lookup_helper_exists(self) -> None:
        fn = self._function_source("degree_index_for_note_pc")
        self.assertIn("return list(scale_pcs).index(int(note_pc) % 12)", fn)
        self.assertIn("except ValueError", fn)

    def test_click_edit_uses_shared_scale_pattern_helpers(self) -> None:
        method = self._class_method_source("ControlWindow", "_handle_scale_circle_clicked")
        self.assertIn("scale_pcs = build_scale_pcs(root_pc, intervals, transpose)", method)
        self.assertIn("degree_idx = degree_index_for_note_pc(note % 12, scale_pcs)", method)

    def test_overlay_generation_uses_same_scale_pattern_helper(self) -> None:
        method = self._class_method_source("ControlWindow", "_update_display_overlays")
        self.assertIn("scale_pcs = build_scale_pcs(root_pc, intervals, transpose)", method)

    def test_scale_overrides_are_stored_by_degree_for_selected_scale(self) -> None:
        method = self._class_method_source("ControlWindow", "_handle_scale_circle_clicked")
        self.assertIn("role_overrides = self.scale_role_overrides.setdefault(scale_key, {})", method)
        self.assertIn("role_overrides[int(degree_idx)] = next_role", method)

    def test_scale_role_resolution_prioritizes_degree_override_without_breaking_legacy_pc(self) -> None:
        method = self._class_method_source("ControlWindow", "_category_role_for_scale_note")
        self.assertIn("role_override = overrides.get(idx)", method)
        self.assertIn("role_override = overrides.get(pc)", method)

    def test_exit_edit_mode_triggers_visual_state_save(self) -> None:
        method = self._class_method_source("ControlWindow", "_toggle_scale_edit_mode")
        self.assertIn("if not self.scale_edit_mode_enabled:", method)
        self.assertIn("self._schedule_visual_state_save()", method)

    def test_click_edit_keeps_root_fixed_as_green(self) -> None:
        method = self._class_method_source("ControlWindow", "_handle_scale_circle_clicked")
        self.assertIn("if int(degree_idx) == 0:", method)
        self.assertIn("fundamental mantiene siempre su categoría", method)

    def test_role_cycle_excludes_root(self) -> None:
        method = self._class_method_source("ControlWindow", "_next_scale_role")
        self.assertIn("order = [\"stable\", \"tension\", \"critical\"]", method)


if __name__ == "__main__":
    unittest.main()
