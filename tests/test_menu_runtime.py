import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

import main
from midi_study import StudyNote
from main import CHORD_PATTERNS, ChordWindow, ControlWindow, FretboardWidget, PianoWindow, StaffWindow


class FakeMidiPort:
    def __init__(self) -> None:
        self.messages = []
        self.close_count = 0

    def iter_pending(self):
        messages = list(self.messages)
        self.messages.clear()
        return messages

    def close(self) -> None:
        self.close_count += 1


class TestMenuRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="midi-piano-menu-tests-")
        cls.original_config_path = ControlWindow.CONFIG_PATH
        cls.original_appearance_path = ControlWindow.APPEARANCE_CONFIG_PATH
        cls.original_study_library_path = ControlWindow.STUDY_LIBRARY_PATH
        cls.original_patterns = copy.deepcopy(CHORD_PATTERNS)

        root = Path(cls.temp_dir.name)
        ControlWindow.CONFIG_PATH = root / "preferences.json"
        ControlWindow.APPEARANCE_CONFIG_PATH = root / "appearance.json"
        ControlWindow.STUDY_LIBRARY_PATH = root / "study-library"
        ControlWindow.CONFIG_PATH.write_text(
            json.dumps(
                {
                    "start_note": 48,
                    "octaves": 3,
                    "custom_chords": [
                        {"nombre": "Prueba guardada", "intervalos": [0, 1, 6, 8, 11]}
                    ],
                }
            ),
            encoding="utf-8",
        )

        cls.midi_patch = patch.object(main.mido, "get_input_names", return_value=[])
        cls.midi_patch.start()
        cls.piano = PianoWindow()
        cls.chords = ChordWindow()
        cls.staff = StaffWindow()
        cls.fretboard = FretboardWidget()
        cls.controls = ControlWindow(cls.piano, cls.chords, cls.staff, cls.fretboard)
        cls.controls.resize(760, 500)
        cls.controls.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.controls.timer.stop()
        cls.controls.close()
        cls.piano.close()
        cls.chords.close()
        cls.staff.close()
        cls.midi_patch.stop()
        CHORD_PATTERNS[:] = cls.original_patterns
        ControlWindow.CONFIG_PATH = cls.original_config_path
        ControlWindow.APPEARANCE_CONFIG_PATH = cls.original_appearance_path
        ControlWindow.STUDY_LIBRARY_PATH = cls.original_study_library_path
        cls.temp_dir.cleanup()

    def test_all_top_menus_are_present_without_staff_menu(self) -> None:
        titles = [action.text() for action in self.controls.menu_bar.actions()]
        self.assertEqual(
            titles,
            ["Ventana", "Diccionario", "Visualización", "Acordes", "Escalas", "Controles", "Ver"],
        )
        self.assertNotIn("Partitura", titles)

    def test_menu_and_control_surfaces_use_explicit_readable_colors(self) -> None:
        menu_style = self.controls.menu_bar.styleSheet()
        control_style = self.controls.styleSheet()
        self.assertIn("background-color: #f7f7f8", menu_style)
        self.assertIn("color: #1d1d1f", menu_style)
        self.assertIn("QWidget#ControlWindow", control_style)
        self.assertIn("QWidget#ControlTabPage", control_style)
        self.assertIn("color: #1d1d1f", control_style)
        self.assertGreaterEqual(self.controls.chord_menu.minimumWidth(), 666)
        self.assertGreaterEqual(self.controls.scale_menu.minimumWidth(), 626)

    def test_two_midi_inputs_can_hold_the_same_note_independently(self) -> None:
        self.controls._clear_live_midi_state()
        first = FakeMidiPort()
        second = FakeMidiPort()
        self.controls.midi_in = first
        self.controls.midi_inputs = [first, second]

        first.messages.append(main.mido.Message("note_on", note=60, velocity=100))
        second.messages.append(main.mido.Message("note_on", note=60, velocity=100))
        self.controls.poll_midi()
        self.assertIn(60, self.controls.active_notes)

        first.messages.append(main.mido.Message("note_off", note=60, velocity=0))
        self.controls.poll_midi()
        self.assertIn(60, self.controls.active_notes)
        self.assertIn(60, self.controls.piano.pressed_notes)

        second.messages.append(main.mido.Message("note_off", note=60, velocity=0))
        self.controls.poll_midi()
        self.assertNotIn(60, self.controls.active_notes)
        self.assertNotIn(60, self.controls.piano.pressed_notes)
        self.controls._close_midi_inputs()
        self.assertEqual(first.close_count, 1)
        self.assertEqual(second.close_count, 1)

    def test_input_close_clears_live_and_sustained_notes(self) -> None:
        port = FakeMidiPort()
        self.controls.midi_in = port
        self.controls.midi_inputs = [port]
        port.messages.extend(
            [
                main.mido.Message("note_on", note=64, velocity=100),
                main.mido.Message("control_change", control=64, value=127),
                main.mido.Message("note_off", note=64, velocity=0),
            ]
        )
        self.controls.poll_midi()
        self.assertIn(64, self.controls.sustained_notes)

        self.controls._close_midi_inputs()
        self.assertFalse(self.controls.active_notes)
        self.assertFalse(self.controls.sustained_notes)
        self.assertFalse(self.controls.piano.pressed_notes)
        self.assertFalse(self.controls.piano.sustained_notes)
        self.assertEqual(port.close_count, 1)

    def test_hidden_note_release_does_not_leave_a_stuck_key(self) -> None:
        piano = self.controls.piano
        piano.set_range(60, 72)
        piano.set_pressed(60, True)
        piano.set_range(72, 84)
        piano.set_pressed(60, False)
        self.assertNotIn(60, piano.pressed_notes)
        self.controls.range_changed(fit_window=False)

    def test_saved_preferences_and_learned_chords_are_loaded(self) -> None:
        self.assertEqual(self.controls.start_combo.currentData(), 48)
        self.assertEqual(self.controls.octaves_spin.value(), 3)
        self.assertTrue(
            any(chord.get("nombre") == "Prueba guardada" for chord in self.controls.custom_chords)
        )
        self.assertTrue(self.controls.learned_chords_scroll.widgetResizable())

    def test_single_window_accepts_compact_resize_and_keeps_it(self) -> None:
        window = self.controls.piano_window
        window.resize(800, 600)
        self.app.processEvents()
        large_children = []
        for child in window.findChildren(QWidget):
            hint = child.minimumSizeHint()
            minimum = child.minimumSize()
            if max(hint.width(), minimum.width()) >= 780:
                large_children.append(
                    f"{type(child).__name__}#{child.objectName() or '-'} "
                    f"minimum={minimum.width()}x{minimum.height()} "
                    f"minimumHint={hint.width()}x{hint.height()}"
                )
        diagnostic = "\n".join(large_children) or "No large child minimums."
        self.assertEqual(
            (window.width(), window.height()),
            (800, 600),
            diagnostic,
        )

        chord_index = 1 if self.controls.display_panel_chord_combo.count() > 1 else 0
        scale_index = 1 if self.controls.display_panel_scale_combo.count() > 1 else 0
        self.controls.display_panel_chord_combo.setCurrentIndex(chord_index)
        self.controls.display_panel_scale_combo.setCurrentIndex(scale_index)
        self.controls.octaves_spin.setValue(4)
        self.app.processEvents()
        self.assertEqual((window.width(), window.height()), (800, 600))

    def test_study_section_keeps_compact_layout_and_both_instruments(self) -> None:
        controls = self.controls
        window = controls.piano_window
        window.resize(800, 600)
        self.app.processEvents()
        self.assertEqual((window.width(), window.height()), (800, 600))
        controls._set_display_panel_section(2)
        self.app.processEvents()
        self.assertEqual((window.width(), window.height()), (800, 600))
        controls.study_notes = [
            StudyNote(60, 0, 400, 96, 0),
            StudyNote(64, 20, 380, 92, 0),
            StudyNote(67, 35, 365, 88, 0),
        ]
        controls.study_selected_channels = {0}
        controls._study_rebuild_steps()
        controls._study_set_mode("guided")
        self.app.processEvents()

        self.assertEqual(controls.display_panel_section_stack.count(), 3)
        self.assertEqual(controls.display_panel_section_stack.currentIndex(), 2)
        self.assertEqual((window.width(), window.height()), (800, 600))
        self.assertEqual(controls.study_expected_notes, {60, 64, 67})
        self.assertEqual(controls.chord_window.display_widget.main_label.text(), "C")
        self.assertEqual(controls.piano.interval_labels.get(64), "3M")
        self.assertEqual(controls.piano.interval_labels.get(67), "5j")
        page = controls.display_panel_section_stack.currentWidget()
        for child in page.findChildren(QWidget):
            if not child.isVisible():
                continue
            self.assertLessEqual(child.geometry().right(), page.rect().right() + 1)
            self.assertLessEqual(child.geometry().bottom(), page.rect().bottom() + 1)

        controls._set_instrument_view("guitar", persist=False, show_status=False)
        self.app.processEvents()
        self.assertIs(window.instrument_stack.currentWidget(), controls.fretboard_widget)
        self.assertEqual(set(controls.fretboard_widget.display_chord_notes), {60, 64, 67})
        self.assertEqual(controls.fretboard_widget.display_interval_labels.get(64), "3M")
        self.assertEqual(controls.fretboard_widget.display_interval_labels.get(67), "5j")

        controls._set_instrument_view("piano", persist=False, show_status=False)
        controls._set_display_panel_section(0)

    def test_study_recording_captures_midi_and_sustain_duration(self) -> None:
        controls = self.controls
        controls._set_display_panel_section(2)
        port = FakeMidiPort()
        controls.midi_in = port
        controls.midi_inputs = [port]
        controls._study_toggle_recording()

        port.messages.extend(
            [
                main.mido.Message("note_on", note=60, velocity=90, channel=0),
                main.mido.Message(
                    "control_change", control=64, value=127, channel=0
                ),
                main.mido.Message("note_off", note=60, velocity=0, channel=0),
            ]
        )
        controls.poll_midi()
        self.assertTrue(controls._study_recording_open)
        time.sleep(0.05)
        port.messages.append(
            main.mido.Message("control_change", control=64, value=0, channel=0)
        )
        controls.poll_midi()
        controls._study_finish_recording()

        self.assertEqual(len(controls.study_notes), 1)
        self.assertEqual(controls.study_notes[0].note, 60)
        self.assertGreaterEqual(controls.study_notes[0].duration_ms, 45)
        controls._close_midi_inputs()
        controls._set_display_panel_section(0)

    def test_study_guided_mode_handles_wrong_notes_and_advances(self) -> None:
        controls = self.controls
        controls._set_display_panel_section(2)
        controls.study_notes = [
            StudyNote(60, 0, 300),
            StudyNote(64, 10, 300),
            StudyNote(67, 20, 300),
            StudyNote(72, 600, 300),
        ]
        controls.study_selected_channels = {0}
        controls._study_rebuild_steps()
        controls._study_set_mode("guided")
        controls._study_start_playback()

        controls._study_input_note_on(61, 90, "test:wrong", 0)
        self.assertEqual(controls.study_wrong_notes, {61})
        controls._study_input_note_off("test:wrong")
        self.assertFalse(controls.study_wrong_notes)

        for note in (60, 64, 67):
            controls._study_input_note_on(note, 90, f"test:{note}", 0)
        self.assertEqual(controls.study_active_step_index, 1)
        for note in (60, 64, 67):
            controls._study_input_note_off(f"test:{note}")
        controls._study_input_note_on(72, 90, "test:72", 0)
        self.assertEqual(controls.study_transport, "idle")
        self.assertIn("completado", controls.study_status_label.text().lower())
        controls._study_input_note_off("test:72")
        controls._set_display_panel_section(0)

    def test_study_playback_uses_shared_visual_recognition(self) -> None:
        controls = self.controls
        controls._set_display_panel_section(2)
        controls.study_notes = [StudyNote(60, 0, 45, 96, 0)]
        controls.study_selected_channels = {0}
        controls._study_rebuild_steps()
        controls._study_set_mode("original")

        with patch.object(controls.study_synth, "note_on", return_value=True), patch.object(
            controls.study_synth, "note_off"
        ):
            controls._study_start_playback()
            controls.study_playback_timer.stop()
            controls._study_playback_started_at = time.monotonic() * 1000.0 - 10
            controls._study_poll_playback()
            self.assertIn(60, controls.piano.auxiliary_pressed_notes)
            self.assertEqual(controls.chord_window.display_widget.main_label.text(), "C4")

            controls._study_playback_started_at = time.monotonic() * 1000.0 - 100
            controls._study_poll_playback()
            self.assertFalse(controls.piano.auxiliary_pressed_notes)
            self.assertEqual(controls.study_transport, "idle")
        controls._set_display_panel_section(0)

    def test_confirmation_dialog_respects_cancel_and_accept(self) -> None:
        def finish_dialog(result: QDialog.DialogCode) -> None:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QDialog) and widget.isVisible():
                    widget.done(int(result))

        QTimer.singleShot(0, lambda: finish_dialog(QDialog.DialogCode.Rejected))
        self.assertFalse(self.controls._confirm_action("Prueba", "Cancelar no debe aceptar."))

        QTimer.singleShot(0, lambda: finish_dialog(QDialog.DialogCode.Accepted))
        self.assertTrue(self.controls._confirm_action("Prueba", "Aceptar debe continuar."))

    def test_background_menu_actions_open_real_color_selection(self) -> None:
        chord_color = QColor(20, 30, 40)
        single_color = QColor(50, 60, 70)
        with patch.object(main, "_get_popup_color", side_effect=[chord_color, single_color]), patch.object(
            self.controls, "_write_preferences"
        ):
            self.controls.choose_chord_background()
            self.controls.choose_single_window_background()

        self.assertEqual(self.controls.chord_bg_color, chord_color)
        self.assertEqual(self.controls.single_window_bg_color, single_color)


if __name__ == "__main__":
    unittest.main()
