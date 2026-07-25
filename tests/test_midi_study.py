import tempfile
import unittest
import unicodedata
from pathlib import Path

import mido

from midi_study import (
    StudyLibrary,
    StudyControlEvent,
    StudyNote,
    build_original_timeline,
    evaluate_guided_progress,
    filter_notes_by_channels,
    group_notes_into_steps,
    read_midi_file,
    read_musicxml_file,
    read_study_file,
    transpose_notes,
    write_midi_file,
)


MUSICXML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <staves>2</staves>
      </attributes>
      <direction placement="above">
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type>
        <sound tempo="120"/>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><type>quarter</type><staff>1</staff>
        <notations><technical><fingering placement="above">1</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><type>quarter</type><staff>1</staff>
        <notations><technical><fingering placement="above">2</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><type>quarter</type><staff>1</staff>
        <notations><technical><fingering placement="above">3</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>F</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><type>quarter</type><staff>1</staff>
        <notations><technical><fingering placement="above">4</fingering></technical></notations>
      </note>
      <backup><duration>16</duration></backup>
      <note>
        <pitch><step>C</step><octave>3</octave></pitch>
        <duration>8</duration><voice>2</voice><type>half</type><staff>2</staff>
        <notations><technical><fingering placement="below">5</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>G</step><octave>3</octave></pitch>
        <duration>8</duration><voice>2</voice><type>half</type><staff>2</staff>
        <notations><technical><fingering placement="below">1</fingering></technical></notations>
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch><step>G</step><octave>4</octave></pitch>
        <duration>16</duration><voice>1</voice><type>whole</type><staff>1</staff>
        <notations><technical><fingering placement="above">5</fingering></technical></notations>
      </note>
      <backup><duration>16</duration></backup>
      <note>
        <pitch><step>E</step><octave>3</octave></pitch>
        <duration>16</duration><voice>2</voice><type>whole</type><staff>2</staff>
        <notations><technical><fingering placement="below">3</fingering></technical></notations>
      </note>
    </measure>
  </part>
</score-partwise>
"""


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
        self.assertEqual(
            [(note.note, note.velocity, note.channel) for note in steps[0].note_events],
            [(60, 96, 0), (64, 90, 0)],
        )
        self.assertEqual(steps[0].start_ms, 100)
        self.assertEqual(steps[0].end_ms, 505)

    def test_steps_include_sustained_notes_without_turning_them_into_attacks(self):
        notes = [
            StudyNote(60, 0, 1000, 96, 0),
            StudyNote(64, 500, 250, 90, 0),
            StudyNote(67, 1200, 200, 88, 0),
        ]
        steps = group_notes_into_steps(notes, tolerance_ms=20)

        self.assertEqual([step.notes for step in steps], [(60,), (64,), (67,)])
        self.assertEqual(steps[1].active_notes, (60, 64))
        self.assertEqual([event.note for event in steps[1].active_note_events], [60, 64])

    def test_guided_progress_credits_released_correct_notes(self):
        progress = evaluate_guided_progress({60, 64}, {64}, {60, 64})
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.matched_notes, (60, 64))
        self.assertEqual(progress.wrong_notes, ())

        wrong = evaluate_guided_progress({60, 64}, {64, 66}, {60, 64})
        self.assertFalse(wrong.is_complete)
        self.assertEqual(wrong.wrong_notes, (66,))

    def test_builds_original_timeline_with_source_timing(self):
        notes = [
            StudyNote(60, 100, 400, 96, 0, staff=1, fingering="2"),
            StudyNote(64, 145, 360, 90, 0, staff=2),
            StudyNote(67, 520, 250, 88, 1),
        ]
        original = build_original_timeline(notes, speed_factor=2.0)
        self.assertEqual(original[0].event_type, "note_on")
        self.assertEqual(original[0].at_ms, 0)
        self.assertEqual(original[-1].event_type, "note_off")
        self.assertEqual(original[0].velocity, 96)
        self.assertEqual(original[0].staff, 1)
        self.assertEqual(original[0].fingering, "2")
        second_note_on = next(
            event
            for event in original
            if event.event_type == "note_on" and event.note == 67
        )
        self.assertEqual(second_note_on.velocity, 88)
        self.assertEqual(second_note_on.channel, 1)

    def test_original_timeline_preserves_short_durations_and_midi_controls(self):
        timeline = build_original_timeline(
            [StudyNote(60, 0, 18, 91, 0)],
            control_events=[
                StudyControlEvent(0, 11, 96, 0),
                StudyControlEvent(22, 11, 48, 0),
            ],
        )

        self.assertEqual(
            [(event.event_type, event.at_ms) for event in timeline],
            [
                ("control_change", 0),
                ("note_on", 0),
                ("note_off", 18),
                ("control_change", 22),
            ],
        )

    def test_reads_musicxml_duration_ties_as_single_note(self):
        sample = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions></attributes>
      <direction><sound tempo="120"/></direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><staff>1</staff>
        <tie type="start"/>
        <notations><tied type="start"/><technical><fingering>1</fingering></technical></notations>
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration>
        <tie type="stop"/>
        <notations><tied type="stop"/></notations>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><staff>1</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ligadura.musicxml"
            path.write_text(sample, encoding="utf-8")
            imported = read_musicxml_file(path)

        self.assertEqual([(note.note, round(note.start_ms)) for note in imported.notes], [(60, 0), (62, 1000)])
        self.assertAlmostEqual(imported.notes[0].duration_ms, 1000, delta=1)
        self.assertEqual(imported.notes[0].fingering, "1")
        self.assertEqual([note.velocity for note in imported.notes], [67, 67])

    def test_reads_musicxml_dynamics_as_note_velocity(self):
        sample = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions></attributes>
      <direction><sound tempo="120"/></direction>
      <direction>
        <direction-type><dynamics><p/></dynamics></direction-type>
        <staff>1</staff>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><staff>1</staff>
      </note>
      <direction>
        <direction-type><dynamics><f/></dynamics></direction-type>
        <staff>1</staff>
      </direction>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><staff>1</staff>
      </note>
      <direction>
        <sound dynamics="72"/>
      </direction>
      <note dynamics="43">
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>4</duration><voice>1</voice><staff>1</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "dinamicas.musicxml"
            path.write_text(sample, encoding="utf-8")
            imported = read_musicxml_file(path)

        self.assertEqual(
            [(note.note, note.velocity) for note in imported.notes],
            [(60, 64), (62, 112), (64, 43)],
        )
        timeline = build_original_timeline(imported.notes)
        self.assertEqual(
            [
                (event.note, event.velocity)
                for event in timeline
                if event.event_type == "note_on"
            ],
            [(60, 64), (62, 112), (64, 43)],
        )

    def test_bundled_study_exercises_import_from_assets(self):
        root = Path(__file__).resolve().parents[1] / "assets" / "study-exercises"
        expected = {
            "1 Enlace de triadas diatónicas, por el círculo de quintas.musicxml",
            "2 Inversiones de las triadas diatónicas.musicxml",
            "3 Armonización diatónica de la escala descendente en el bajo.musicxml",
            "4 Armonización diatónica de la escala descendente en la melodía.musicxml",
            "5 Ejemplo n.1 de regiones tonales (dominantes secundarias).musicxml",
            "6 Ejemplo n.2 de regiones tonales (dominantes secundarias, acordes disminuidos).musicxml",
            "7 Ejemplo n.1 de diseño para el bajo.musicxml",
            "8 Ejemplo n.2 de diseño para el bajo.musicxml",
            "9 Ejemplo n.1 de diseño para la mano derecha.musicxml",
            "10 Ejemplo n.2 de diseño para la mano derecha.musicxml",
            "Chopin nocturne Op9 n2.mid",
            "Escala de C mayor.musicxml",
            "II-V con notas guia.musicxml",
            "Misty 1.musicxml",
            "Misty 2.musicxml",
        }
        bundled_names = {
            unicodedata.normalize("NFC", path.name)
            for path in root.iterdir()
        }
        self.assertEqual(bundled_names, expected)

        files_with_duration_ties = set()
        for path in sorted(root.iterdir()):
            imported = read_study_file(path)
            self.assertGreater(len(imported.notes), 0, path.name)
            if path.suffix.lower() == ".musicxml" and "<tie" in path.read_text(encoding="utf-8", errors="ignore"):
                steps = group_notes_into_steps(imported.notes)
                has_sustained_overlay = any(
                    set(step.active_notes) > set(step.notes)
                    for step in steps
                )
                self.assertTrue(has_sustained_overlay, path.name)
                files_with_duration_ties.add(path.name)

        self.assertEqual(
            files_with_duration_ties,
            {
                next(
                    path.name
                    for path in root.iterdir()
                    if unicodedata.normalize("NFC", path.name) == "Misty 1.musicxml"
                ),
                next(
                    path.name
                    for path in root.iterdir()
                    if unicodedata.normalize("NFC", path.name) == "Misty 2.musicxml"
                ),
            },
        )
        chopin = read_midi_file(root / "Chopin nocturne Op9 n2.mid")
        self.assertEqual(len(chopin.control_events), 24)
        self.assertFalse(any(event.control == 64 for event in chopin.control_events))

    def test_filters_channels_and_removes_leading_silence(self):
        filtered = filter_notes_by_channels(self.notes, {1})
        self.assertEqual([note.note for note in filtered], [67])
        self.assertEqual(filtered[0].start_ms, 0)

    def test_transposes_notes_without_mutating_timing_or_channels(self):
        transposed = transpose_notes(self.notes, 2)
        self.assertEqual([note.note for note in transposed], [62, 66, 69])
        self.assertEqual([note.channel for note in transposed], [0, 0, 1])
        self.assertEqual(transposed[1].start_ms, 45)

    def test_transpose_drops_notes_outside_midi_range(self):
        notes = [StudyNote(1, 500, 80), StudyNote(10, 700, 90)]
        transposed = transpose_notes(notes, -5)
        self.assertEqual([note.note for note in transposed], [5])
        self.assertEqual(transposed[0].start_ms, 0)

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

    def test_reads_musicxml_staves_voices_and_fingerings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Prueba.musicxml"
            path.write_text(MUSICXML_SAMPLE, encoding="utf-8")
            imported = read_musicxml_file(path)
            generic = read_study_file(path)

        self.assertEqual(imported.bpm, 120)
        self.assertEqual(len(imported.notes), 8)
        self.assertEqual(imported.channels, (0, 1))
        ordered = sorted(imported.notes, key=lambda note: (note.start_ms, note.note))
        self.assertEqual([note.note for note in ordered[:6]], [48, 60, 62, 55, 64, 65])
        self.assertEqual([note.staff for note in ordered[:2]], [2, 1])
        self.assertEqual([note.voice for note in ordered[:2]], ["2", "1"])
        self.assertEqual([note.fingering for note in ordered[:2]], ["5", "1"])
        self.assertAlmostEqual(ordered[2].start_ms, 500, delta=1)
        self.assertAlmostEqual(ordered[3].start_ms, 1000, delta=1)
        self.assertEqual(generic.notes, imported.notes)

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

    def test_library_preserves_musicxml_metadata_sidecar(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            library = StudyLibrary(Path(temporary_directory))
            saved = library.save_exercise(
                "Digitaciones",
                [StudyNote(60, 0, 300, 96, 0, staff=1, voice="1", fingering="2")],
                120,
            )
            _metadata, imported = library.load_exercise(saved.exercise_id)

        self.assertEqual(imported.notes[0].staff, 1)
        self.assertEqual(imported.notes[0].voice, "1")
        self.assertEqual(imported.notes[0].fingering, "2")

    def test_library_preserves_controls_and_lists_names_in_natural_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            library = StudyLibrary(Path(temporary_directory))
            for name in ("10 Décimo", "Alfa", "2 Segundo", "1 Primero"):
                library.save_exercise(
                    name,
                    [StudyNote(60, 0, 100)],
                    120,
                    control_events=[StudyControlEvent(0, 11, 96)],
                )

            self.assertEqual(
                [item.name for item in library.list_exercises()],
                ["1 Primero", "2 Segundo", "10 Décimo", "Alfa"],
            )
            metadata = library.list_exercises()[0]
            _saved, imported = library.load_exercise(metadata.exercise_id)
            self.assertEqual(
                imported.control_events,
                (StudyControlEvent(0, 11, 96),),
            )


if __name__ == "__main__":
    unittest.main()
