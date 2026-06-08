import ast
import unittest
from pathlib import Path


class TestStaffCollisionOffsets(unittest.TestCase):
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

    def test_second_collisions_are_resolved_as_one_staff_run(self) -> None:
        method = self._class_method_source("StaffWidget", "computeNoteXOffsetsForCollisions")

        self.assertIn("step_map: Dict[int, List[int]]", method)
        self.assertIn("run_steps = [unique_steps[index]]", method)
        self.assertIn("second_contact_dx = note_head_width * 0.42", method)
        self.assertIn("dx = second_contact_dx * collision_scale", method)
        self.assertIn("base_offset = -dx if run_index % 2 == 0 else dx", method)
        self.assertNotIn("treble_group", method)
        self.assertNotIn("bass_group", method)

    def test_b_c_d_around_middle_c_alternates_sides(self) -> None:
        method = self._class_method_source("StaffWidget", "computeNoteXOffsetsForCollisions")

        self.assertIn("if len(run_steps) > 1:", method)
        self.assertIn("for run_index, step in enumerate(run_steps):", method)
        self.assertIn("offsets[note] += base_offset", method)

    def test_staff_does_not_draw_note_name_labels(self) -> None:
        paint_source = self._class_method_source("StaffWidget", "paintEvent")

        self.assertNotIn("label_texts", paint_source)
        self.assertNotIn("drawText(label_rect", paint_source)


if __name__ == "__main__":
    unittest.main()
