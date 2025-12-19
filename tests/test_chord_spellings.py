import json
import unittest
from pathlib import Path

import music_theory


def expected_degree(interval: int, chord_name: str) -> int | None:
    name = chord_name or ""
    is_sus2 = "sus2" in name

    if interval == 0:
        return 1

    if interval in (1, 2, 3):
        if "addb2" in name and interval == 1:
            return 2
        if "#9" in name and interval == 3:
            return 9
        if "b9" in name and interval == 1:
            return 9
        if interval == 2 and ("add2" in name or is_sus2):
            return 2
        if interval in (1, 2) and any(token in name for token in ("9", "11", "13")):
            return 9
        return 3

    return None


class TestChordSpellings(unittest.TestCase):
    def test_diminished_fifth_spellings_override_augmented_fourth(self) -> None:
        cases = [
            ("11(b5)no3", "B", 11, 6, "F"),
            ("13(b5)", "C", 1, 6, "G"),
            ("º7(11)", "E", 4, 6, "Bb"),
            ("ø11", "A", 9, 6, "Eb"),
        ]

        for chord_name, root_letter, root_pc, interval, expected in cases:
            spelling = music_theory.spell_note_for_interval(
                root_letter, root_pc, chord_name, interval
            )
            self.assertEqual(
                spelling,
                expected,
                msg=(
                    f"{root_letter}{chord_name}: intervalo {interval} esperaba {expected} "
                    f"pero fue {spelling}"
                ),
            )

    def test_dictionary_spellings(self) -> None:
        dictionary_path = Path(__file__).resolve().parents[1] / "diccionario_acordes.json"
        payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
        chords = payload.get("chords", [])

        for chord in chords:
            name = chord.get("nombre", "")
            intervals = list(chord.get("obligatorias", [])) + list(chord.get("opcionales", []))
            normalized = {int(interval) % 12 for interval in intervals} | {0}

            for root_pc, root_name in enumerate(music_theory.DETECT_NOTE_NAMES):
                root_letter, _accidental = music_theory._parse_root_spelling(root_name)
                assert root_letter is not None
                root_index = music_theory.NOTE_LETTER_TO_INDEX[root_letter]

                for interval in normalized:
                    spelling = music_theory.spell_note_for_interval(root_letter, root_pc, name, interval)
                    degree = expected_degree(interval, name)
                    if degree is None:
                        continue
                    expected_letter = music_theory.NOTE_LETTERS[
                        (root_index + music_theory._degree_offset(degree)) % 7
                    ]
                    self.assertEqual(
                        spelling[0],
                        expected_letter,
                        msg=(
                            f"{root_name}{name}: intervalo {interval} esperaba letra {expected_letter} "
                            f"pero fue {spelling}"
                        ),
                    )

    def test_spelled_octave_for_cb4(self) -> None:
        self.assertEqual(music_theory.spelled_octave(59, "C", "b"), 4)


if __name__ == "__main__":
    unittest.main()
