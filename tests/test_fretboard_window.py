import inspect
import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from main import (
    ChordDisplayWidget,
    ControlWindow,
    FretboardWidget,
    PianoWindow,
    SCALE_PATTERNS,
    analizar_cifrado_alternativos,
    interval_label_for_context,
    main as run_app,
)


class TestFretboardWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_middle_c_uses_every_playable_position(self) -> None:
        positions = FretboardWidget.positions_for_notes({60})
        string_and_fret = {(string_index, fret) for _note, string_index, fret, _x, _y in positions}

        self.assertEqual(string_and_fret, {(1, 1), (2, 5), (3, 10), (4, 15)})

    def test_low_e_maps_to_open_sixth_string(self) -> None:
        positions = FretboardWidget.positions_for_notes({40})

        self.assertEqual(len(positions), 1)
        note, string_index, fret, _x, _y = positions[0]
        self.assertEqual((note, string_index, fret), (40, 5, 0))

    def test_chord_spelling_and_root_are_reused(self) -> None:
        notes = {60, 64, 67}
        chord_info = analizar_cifrado_alternativos(notes)
        widget = FretboardWidget()
        widget.set_notes(notes, chord_info)

        self.assertEqual(widget._root_pc(), 0)
        self.assertEqual(widget._note_label(60), "C")
        self.assertEqual(widget._note_label(64), "E")
        self.assertEqual(widget._note_label(67), "G")
        self.assertFalse(widget.background.isNull())

    def test_chord_display_centers_one_line_of_alternatives_below_main(self) -> None:
        widget = ChordDisplayWidget()
        widget.resize(1000, 180)
        widget.main_label.setText("F∆(b5)")
        widget.alt_label.setText(
            widget._format_alternative_chords(["B11(b5)no3", "Esus4(addb2)"])
        )
        widget.alt_label.show()
        widget._apply_responsive_fonts()

        self.assertIsInstance(widget.layout(), QVBoxLayout)
        self.assertEqual(widget.main_label.alignment(), Qt.AlignmentFlag.AlignCenter)
        self.assertEqual(widget.alt_label.alignment(), Qt.AlignmentFlag.AlignCenter)
        self.assertFalse(widget.alt_label.wordWrap())
        self.assertNotIn("\n", widget.alt_label.text())
        self.assertGreater(
            widget.main_label.font().pointSize(),
            widget.alt_label.font().pointSize(),
        )

    def test_embedded_fretboard_maps_image_to_full_widget_width(self) -> None:
        widget = FretboardWidget()
        widget.resize(1200, 240)
        widget.set_embedded_mode(True)

        top_left = widget._embedded_map_point(0.0, widget.EMBEDDED_SOURCE_TOP)
        bottom_right = widget._embedded_map_point(
            widget.IMAGE_WIDTH,
            widget.EMBEDDED_SOURCE_TOP + widget.EMBEDDED_SOURCE_HEIGHT,
        )

        self.assertAlmostEqual(top_left.x(), 0.0)
        self.assertAlmostEqual(top_left.y(), 0.0)
        self.assertAlmostEqual(bottom_right.x(), 1200.0)
        self.assertAlmostEqual(bottom_right.y(), 240.0)

    def test_middle_c_is_drawn_only_once_in_first_position(self) -> None:
        widget = FretboardWidget()
        widget.set_notes({60}, analizar_cifrado_alternativos({60}))

        self.assertEqual(widget.current_position, 1)
        self.assertEqual(len(widget.display_assignment), 1)
        note, string_index, fret, _x, _y, secondary = widget.display_assignment[0]
        self.assertEqual((note, string_index, fret), (60, 1, 1))
        self.assertFalse(secondary)

    def test_regular_chord_prefers_one_note_per_string(self) -> None:
        notes = {60, 64, 67}
        widget = FretboardWidget()
        widget.set_notes(notes, analizar_cifrado_alternativos(notes))

        self.assertEqual({placement[0] for placement in widget.display_assignment}, notes)
        strings = [placement[1] for placement in widget.display_assignment]
        self.assertEqual(len(strings), len(set(strings)))
        self.assertFalse(any(placement[5] for placement in widget.display_assignment))

    def test_position_moves_up_and_resets_after_release(self) -> None:
        widget = FretboardWidget()
        widget.set_notes({60}, analizar_cifrado_alternativos({60}))
        widget.set_notes({72}, analizar_cifrado_alternativos({72}))

        self.assertEqual(widget.current_position, 4)
        widget.set_notes(set(), {})
        self.assertEqual(widget.current_position, 1)
        self.assertFalse(widget._position_initialized)
        widget.set_notes({64}, analizar_cifrado_alternativos({64}))
        self.assertEqual(widget.current_position, 1)

    def test_open_low_string_remains_available_in_high_position(self) -> None:
        widget = FretboardWidget()
        widget.set_notes({72}, analizar_cifrado_alternativos({72}))
        high_position = widget.current_position
        widget.set_notes({40}, analizar_cifrado_alternativos({40}))

        self.assertEqual(widget.current_position, high_position)
        note, string_index, fret, _x, _y, _secondary = widget.display_assignment[0]
        self.assertEqual((note, string_index, fret), (40, 5, 0))

    def test_more_than_six_notes_are_all_drawn_with_dimmed_extras(self) -> None:
        notes = set(range(60, 67))
        widget = FretboardWidget()
        widget.set_notes(notes, analizar_cifrado_alternativos(notes), sorted(notes))

        self.assertEqual({placement[0] for placement in widget.display_assignment}, notes)
        self.assertEqual(len(widget.display_assignment), len(notes))
        self.assertTrue(any(placement[5] for placement in widget.display_assignment))
        self.assertFalse(widget.partial_assignment)

    def test_preloaded_chord_and_scale_overlays_are_drawn_on_fretboard(self) -> None:
        widget = FretboardWidget()
        chord_notes = {
            60: QColor(52, 199, 89),
            64: QColor(40, 105, 220),
            67: QColor(40, 105, 220),
        }
        scale_notes = {60: QColor(60, 200, 120), 62: QColor(60, 120, 240)}
        widget.set_display_overlays(
            chord_notes,
            scale_notes,
            {60: "f", 64: "3M", 67: "5j"},
            0,
            "C",
        )

        self.assertEqual(
            {placement[0] for placement in widget.display_assignment},
            {60, 62, 64, 67},
        )
        self.assertEqual(widget._marker_label(60), "f")
        self.assertEqual(widget._marker_label(64), "3M")
        self.assertEqual(widget._marker_label(62), "D")

    def test_all_fretboard_markers_match_the_string_spacing(self) -> None:
        widget = FretboardWidget()
        widget.resize(1200, 240)
        widget.set_embedded_mode(True)
        widget.notes = {60}
        widget.display_chord_notes = {64: QColor(40, 105, 220)}
        widget.display_scale_notes = {62: QColor(60, 120, 240)}

        string_positions = [
            widget._embedded_map_point(0.0, string_y).y()
            for string_y in widget.STRING_Y
        ]
        minimum_spacing = min(
            abs(second - first)
            for first, second in zip(string_positions, string_positions[1:])
        )
        marker_radius = widget._embedded_marker_radius()
        radii = {
            widget._marker_radius_for_note(note, marker_radius)
            for note in (
                set(widget.notes)
                | set(widget.display_chord_notes)
                | set(widget.display_scale_notes)
            )
        }

        self.assertEqual(radii, {marker_radius})
        self.assertAlmostEqual(marker_radius * 2.0, minimum_spacing)

    def test_guitar_scales_keep_every_note_at_full_opacity(self) -> None:
        widget = FretboardWidget()
        has_shared_string = False

        for scale_name, steps in SCALE_PATTERNS.items():
            for root_pc in range(12):
                with self.subTest(scale=scale_name, root=root_pc):
                    notes = FretboardWidget.guitar_scale_notes(root_pc, steps)
                    widget.set_display_overlays(
                        {},
                        {note: QColor(60, 120, 240) for note in notes},
                        {},
                        root_pc,
                        "",
                    )
                    assigned_notes = {
                        placement[0] for placement in widget.display_assignment
                    }
                    self.assertEqual(assigned_notes, set(notes))
                    self.assertFalse(widget.partial_assignment)
                    frets = [
                        placement[2] for placement in widget.display_assignment
                    ]
                    self.assertTrue(frets)
                    self.assertLessEqual(max(frets) - min(frets) + 1, 4)
                    for note, _string, _fret, _x, _y, secondary in widget.display_assignment:
                        has_shared_string = has_shared_string or secondary
                        self.assertEqual(widget._marker_opacity(note, secondary), 1.0)

        self.assertTrue(has_shared_string)

    def test_guitar_voicing_uses_unique_pitch_classes_and_strings(self) -> None:
        result = FretboardWidget.guitar_voicing_for_pitch_classes(
            0,
            {0, 2, 4, 7, 10},
        )
        notes = set(result["notes"])
        placements = list(result["placements"])

        self.assertEqual(len(notes), len({note % 12 for note in notes}))
        self.assertEqual(len(placements), len({placement[1] for placement in placements}))

    def test_preloaded_ninth_omits_its_optional_fifth_on_guitar(self) -> None:
        required = ControlWindow._guitar_chord_required_intervals(
            "9",
            [4, 7, 10, 14],
        )

        self.assertEqual(set(required), {0, 2, 4, 10})

    def test_six_voice_chords_use_the_allowed_suppressions(self) -> None:
        with_perfect_fifth = ControlWindow._guitar_chord_required_intervals(
            "∆13",
            [0, 2, 4, 7, 9, 11],
        )
        with_tritone = ControlWindow._guitar_chord_required_intervals(
            "+7(b9)#11",
            [0, 1, 4, 6, 8, 10],
        )
        four_voice_sixth = ControlWindow._guitar_chord_required_intervals(
            "6",
            [0, 4, 7, 9],
        )

        self.assertEqual(set(with_perfect_fifth), {0, 2, 4, 9, 11})
        self.assertEqual(set(with_tritone), {0, 1, 6, 8, 10})
        self.assertEqual(set(four_voice_sixth), {0, 4, 7, 9})

    def test_string_continuity_allows_only_the_low_string_exception(self) -> None:
        self.assertEqual(FretboardWidget._string_continuity_penalties({0, 1, 2, 3}), (0, 0))
        self.assertEqual(FretboardWidget._string_continuity_penalties({0, 2}), (1, 1))
        self.assertEqual(FretboardWidget._string_continuity_penalties({3, 5}), (0, 0))

    def test_widget_preserves_preloaded_chord_string_continuity(self) -> None:
        result = ControlWindow._guitar_chord_voicing(0, "6", [0, 4, 7, 9])
        widget = FretboardWidget()
        widget.set_display_overlays(
            {note: QColor(40, 105, 220) for note in result["notes"]},
            {},
            {},
            0,
            "C",
        )
        strings = {placement[1] for placement in widget.display_assignment}

        self.assertEqual(len(strings), len(widget.display_assignment))
        self.assertEqual(widget._string_continuity_penalties(strings), (0, 0))

    def test_every_preloaded_chord_has_a_clean_guitar_voicing(self) -> None:
        library_path = Path(__file__).resolve().parents[1] / "assets" / "jazzscope_chords.json"
        library = json.loads(library_path.read_text(encoding="utf-8"))

        for chord_name, intervals in library.items():
            required = set(
                ControlWindow._guitar_chord_required_intervals(chord_name, intervals)
            )
            self.assertLessEqual(len(required), 5)
            normalized_name = ControlWindow._normalized_guitar_chord_name(chord_name)
            is_penta = normalized_name.lower().startswith("penta")
            for root_pc in range(12):
                with self.subTest(chord=chord_name, root=root_pc):
                    result = ControlWindow._guitar_chord_voicing(
                        root_pc,
                        chord_name,
                        intervals,
                    )
                    notes = set(result["notes"])
                    placements = list(result["placements"])
                    present = set(result["intervals"])
                    self.assertTrue(notes)
                    self.assertEqual(present, required)
                    self.assertLessEqual(len(notes), len(FretboardWidget.OPEN_STRING_MIDI))
                    self.assertEqual(len(notes), len({note % 12 for note in notes}))
                    self.assertEqual(
                        len(placements),
                        len({placement[1] for placement in placements}),
                    )
                    self.assertEqual(
                        FretboardWidget._string_continuity_penalties(
                            {placement[1] for placement in placements}
                        ),
                        (0, 0),
                    )

                    note_by_interval = {
                        (note - root_pc) % 12: note
                        for note in notes
                    }
                    if is_penta:
                        voice_order = list(result.get("voice_order", []))
                        self.assertEqual(set(voice_order), present)
                        ordered_notes = [
                            note_by_interval[interval]
                            for interval in voice_order
                        ]
                        self.assertEqual(ordered_notes, sorted(ordered_notes))
                        continue

                    labels = {
                        interval: interval_label_for_context(
                            interval,
                            present,
                            normalized_name,
                        )
                        for interval in present
                    }
                    ninths = [
                        interval
                        for interval, label in labels.items()
                        if label in {"9m", "9M", "9+"}
                    ]
                    thirds = [
                        interval
                        for interval, label in labels.items()
                        if label in {"3m", "3M"}
                    ]
                    elevenths = [
                        interval
                        for interval, label in labels.items()
                        if label in {"11j", "11+"}
                    ]
                    fifths = [
                        interval
                        for interval, label in labels.items()
                        if label in {"5b", "5j", "5+"}
                    ]
                    thirteenths = [
                        interval
                        for interval, label in labels.items()
                        if label in {"13m", "13"}
                    ]
                    sevenths = [
                        interval
                        for interval, label in labels.items()
                        if label in {"7b", "7m", "7M"}
                    ]
                    if (
                        "º" in normalized_name
                        and ("b13" in normalized_name or "♭13" in normalized_name)
                        and 8 in present
                        and 9 in present
                    ):
                        sevenths.append(9)

                    for ninth in ninths:
                        self.assertGreater(note_by_interval[ninth], note_by_interval[0])
                        for third in thirds:
                            if ninth != third:
                                self.assertGreater(
                                    note_by_interval[ninth],
                                    note_by_interval[third],
                                )
                    for eleventh in elevenths:
                        for fifth in fifths:
                            if eleventh != fifth:
                                self.assertGreater(
                                    note_by_interval[eleventh],
                                    note_by_interval[fifth],
                                )
                    for thirteenth in thirteenths:
                        for seventh in sevenths:
                            if thirteenth != seventh:
                                self.assertGreater(
                                    note_by_interval[thirteenth],
                                    note_by_interval[seventh],
                                )

    def test_penta_families_keep_their_five_distinct_rotations(self) -> None:
        library_path = Path(__file__).resolve().parents[1] / "assets" / "jazzscope_chords.json"
        library = json.loads(library_path.read_text(encoding="utf-8"))

        for family_prefix in ("Penta_", "Penta7_"):
            family = {
                name: intervals
                for name, intervals in library.items()
                if name.startswith(family_prefix)
            }
            self.assertEqual(len(family), 5)
            signatures = set()
            for chord_name, intervals in family.items():
                result = ControlWindow._guitar_chord_voicing(0, chord_name, intervals)
                required = set(
                    ControlWindow._guitar_chord_required_intervals(
                        chord_name,
                        intervals,
                    )
                )
                self.assertEqual(len(result["notes"]), 5)
                self.assertEqual(set(result["intervals"]), required)
                if family_prefix == "Penta7_":
                    self.assertIn(7, required)
                signatures.add(tuple(sorted(result["notes"])))

            self.assertEqual(len(signatures), 5)

    def test_piano_and_guitar_share_the_main_instrument_stack(self) -> None:
        window = PianoWindow()
        fretboard = FretboardWidget()
        window.show_combined_view(
            QWidget(),
            QWidget(),
            QWidget(),
            fretboard,
        )

        self.assertIs(window.instrument_stack.currentWidget(), window.piano)
        window.set_instrument_view("guitar")
        self.assertIs(window.instrument_stack.currentWidget(), fretboard)
        self.assertIs(window.centralWidget(), window._combined_container)
        window.close()

    def test_staff_view_is_not_exposed_anywhere_in_the_interface(self) -> None:
        menu_source = inspect.getsource(ControlWindow._setup_window_menu)
        control_source = inspect.getsource(ControlWindow)
        combined_source = inspect.getsource(PianoWindow.show_combined_view)
        main_source = inspect.getsource(run_app)

        self.assertNotIn("Partitura", menu_source)
        self.assertNotIn("_setup_staff_menu()", menu_source)
        self.assertNotIn('addMenu("Partitura")', control_source)
        self.assertFalse(hasattr(ControlWindow, "_setup_staff_menu"))
        self.assertNotIn("staff_widget", combined_source)
        self.assertNotIn("staff_window.show()", main_source)


if __name__ == "__main__":
    unittest.main()
