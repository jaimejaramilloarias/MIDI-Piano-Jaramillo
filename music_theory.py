from __future__ import annotations

from typing import Optional, Tuple

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
NOTE_LETTER_TO_INDEX = {letter: index for index, letter in enumerate(NOTE_LETTERS)}
NOTE_LETTER_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTAL_TO_SYMBOL = {"bb": "𝄫", "b": "♭", "": "", "#": "♯", "##": "𝄪"}
DETECT_NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _parse_root_spelling(chord_name: str) -> Tuple[Optional[str], str]:
    if not chord_name:
        return None, ""
    root = chord_name.split("/")[0].strip()
    if not root:
        return None, ""
    letter = root[0].upper()
    if letter not in NOTE_LETTER_TO_INDEX:
        return None, ""
    accidental = ""
    if len(root) > 1 and root[1] in ("b", "#"):
        accidental = root[1]
        if len(root) > 2 and root[2] == root[1]:
            accidental += root[2]
    return letter, accidental


def _degree_offset(degree: int) -> int:
    mapping = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 9: 1, 11: 3, 13: 5}
    return mapping.get(degree, 0)


def _degree_for_interval(interval: int, chord_name: str) -> int:
    name = chord_name or ""
    is_sus2 = "sus2" in name
    is_sus4 = "sus4" in name

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

    if interval == 4:
        return 3

    if interval in (5, 6):
        if is_sus4 and interval == 5:
            return 4
        if "add4" in name and interval == 5:
            return 4
        if "#11" in name and interval == 6:
            return 11
        if "11" in name and interval in (5, 6):
            return 11
        if "b5" in name or "(b5)" in name or "º" in name or "ø" in name:
            if interval == 6:
                return 5
        if interval == 5 and not is_sus4:
            return 11
        return 4 if is_sus4 else 5

    if interval == 7:
        return 5

    if interval == 8:
        if "b13" in name:
            return 13
        if "+" in name or "#5" in name:
            return 5
        return 13 if "13" in name else 5

    if interval == 9:
        if "º7" in name or ("º" in name and "7" in name):
            return 7
        if "13" in name or "b13" in name:
            return 13
        if "6" in name and "13" not in name:
            return 6
        return 6

    if interval in (10, 11):
        return 7

    return 1


def _accidental_offset(accidental: str) -> int:
    return {"bb": -2, "b": -1, "": 0, "#": 1, "##": 2}.get(accidental, 0)


def note_octave(note: int) -> int:
    """Devuelve la octava según la convención MIDI típica."""
    return note // 12 - 1


def midi_of_C(octave: int) -> int:
    """Devuelve el número de nota MIDI de C<octave>."""
    return (octave + 1) * 12


def spelled_octave(note: int, letter: str, accidental: str) -> int:
    base_octave = note_octave(note)
    base_pc = NOTE_LETTER_TO_PC.get(letter, 0) + _accidental_offset(accidental)
    for octave in (base_octave - 1, base_octave, base_octave + 1):
        midi = midi_of_C(octave) + base_pc
        if midi == note:
            return octave
    return base_octave


def spell_note_for_interval(root_letter: str, root_pc: int, chord_name: str, interval: int) -> str:
    root_index = NOTE_LETTER_TO_INDEX[root_letter]
    degree = _degree_for_interval(interval, chord_name)
    letter_index = (root_index + _degree_offset(degree)) % 7
    letter = NOTE_LETTERS[letter_index]
    natural_pc = NOTE_LETTER_TO_PC[letter]
    note_pc = (root_pc + interval) % 12
    diff = (note_pc - natural_pc + 12) % 12
    if diff > 6:
        diff -= 12
    if diff not in (-2, -1, 0, 1, 2):
        return NOTE_NAMES[note_pc]
    accidental = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}[diff]
    return f"{letter}{accidental}"
