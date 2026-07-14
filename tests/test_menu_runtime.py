import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

import main
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
        cls.original_patterns = copy.deepcopy(CHORD_PATTERNS)

        root = Path(cls.temp_dir.name)
        ControlWindow.CONFIG_PATH = root / "preferences.json"
        ControlWindow.APPEARANCE_CONFIG_PATH = root / "appearance.json"
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
