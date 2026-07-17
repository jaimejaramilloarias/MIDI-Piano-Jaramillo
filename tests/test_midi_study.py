import tempfile
import unittest
from pathlib import Path

import mido

from midi_study import (
    StudyLibrary,
    StudyNote,
    build_original_timeline,
    build_step_timeline,
    evaluate_guided_progress,
    filter_notes_by_channels,
    group_notes_into_steps,
    read_midi_file,
    write_midi_file,
)


class MidiStudyEngineTests(unittest.TestCase):
    def setUp(self):
        self.notes = [
            StudyNote(60, 100, 400, 96, 0),
            StudyNote(64, 145, 360, 90, 0),
            StudyNote(67, 520, 250, 88, 1),
        ]

    def test_groups_chords_from_first_onset(self):
        steps = group_notes_into_steps(self.notes, tolerance_ms=70)
        self.assertEqual([step.notes for step in steps], [(60, 64), (67,)])
        self.assertEqual(steps[0].start_ms, 100)
        self.assertEqual(steps[0].end_ms, 505)

    def test_guided_progress_credits_released_correct_notes(self):
        progress = evaluate_guided_progress({60, 64}, {64}, {60, 64})
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.matched_notes, (60, 64))
        self.assertEqual(progress.wrong_notes, ())

        wrong = evaluate_guided_progress({60, 64}, {64, 66}, {60, 64})
        self.assertFalse(wrong.is_complete)
        self.assertEqual(wrong.wrong_notes, (66,))

    def test_builds_original_and_equal_step_timelines(self):
        original = build_original_timeline(self.notes, speed_factor=2.0)
        self.assertEqual(original[0].event_type, "note_on")
        self.assertEqual(original[0].at_ms, 0)
        self.assertEqual(original[-1].event_type, "note_off")

        steps = group_notes_into_steps(self.notes, tolerance_ms=70)
        stepped = build_step_timeline(steps, speed_factor=1.0)
        second_step_on = next(
            event
            for event in stepped
            if event.event_type == "note_on" and event.note == 67
        )
        self.assertEqual(second_step_on.at_ms, 900)

    def test_filters_channels_and_removes_leading_silence(self):
        filtered = filter_notes_by_channels(self.notes, {1})
        self.assertEqual([note.note for note in filtered], [67])
        self.assertEqual(filtered[0].start_ms, 0)

    def test_midi_round_trip_preserves_notes_and_channels(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "exercise.mid"
            write_midi_file(path, self.notes, bpm=96, track_name="Prueba")
            imported = read_midi_file(path)

        self.assertEqual(imported.bpm, 96)
        self.assertEqual(imported.channels, (0, 1))
        self.assertEqual(
            [(note.note, note.channel) for note in imported.notes],
            [(60, 0), (64, 0), (67, 1)],
        )
        self.assertAlmostEqual(imported.notes[1].start_ms, 45, delta=2)

    def test_type_one_tempo_map_is_applied_to_imported_note_timing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "tempo-map.mid"
            midi = mido.MidiFile(type=1, ticks_per_beat=480)
            tempo_track = mido.MidiTrack()
            note_track = mido.MidiTrack()
            midi.tracks.extend((tempo_track, note_track))
            tempo_track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
            tempo_track.append(mido.MetaMessage("set_tempo", tempo=1_000_000, time=480))
            note_track.append(
                mido.Message("note_on", note=60, velocity=90, channel=0, time=0)
            )
            note_track.append(
                mido.Message("note_off", note=60, velocity=0, channel=0, time=960)
            )
            midi.save(path)

            imported = read_midi_file(path)

        self.assertEqual(imported.bpm, 120)
        self.assertEqual(len(imported.notes), 1)
        self.assertAlmostEqual(imported.notes[0].duration_ms, 1500, delta=2)

    def test_library_save_load_copy_and_delete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            library = StudyLibrary(Path(temporary_directory))
            saved = library.save_exercise("Cadencia", self.notes, 120)
            self.assertEqual(len(library.list_exercises()), 1)

            metadata, imported = library.load_exercise(saved.exercise_id)
            self.assertEqual(metadata.name, "Cadencia")
            self.assertEqual(len(imported.notes), 3)

            copy = library.save_exercise("Cadencia copia", imported.notes, 120)
            self.assertNotEqual(copy.exercise_id, saved.exercise_id)
            self.assertEqual(len(library.list_exercises()), 2)

            library.delete_exercise(saved.exercise_id)
            self.assertEqual(
                [item.exercise_id for item in library.list_exercises()],
                [copy.exercise_id],
            )


if __name__ == "__main__":
    unittest.main()
