from __future__ import annotations

import json
import math
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ET

import mido


MIN_NOTE_DURATION_MS = 45.0
DEFAULT_CHORD_TOLERANCE_MS = 70
MIN_SPEED_FACTOR = 0.5
MAX_SPEED_FACTOR = 2.0
DEFAULT_STUDY_NOTE_VELOCITY = 67
DEFAULT_MUSICXML_VELOCITY = DEFAULT_STUDY_NOTE_VELOCITY
MIDI_IMPORT_EXTENSIONS = {".mid", ".midi", ".smf"}
MUSICXML_IMPORT_EXTENSIONS = {".musicxml", ".xml", ".mxl"}
STUDY_IMPORT_EXTENSIONS = MIDI_IMPORT_EXTENSIONS | MUSICXML_IMPORT_EXTENSIONS


@dataclass(frozen=True)
class StudyNote:
    note: int
    start_ms: float
    duration_ms: float
    velocity: int = DEFAULT_STUDY_NOTE_VELOCITY
    channel: int = 0
    staff: Optional[int] = None
    voice: str = ""
    fingering: str = ""

    def __post_init__(self) -> None:
        if not 0 <= int(self.note) <= 127:
            raise ValueError("La nota MIDI debe estar entre 0 y 127.")
        if not math.isfinite(float(self.start_ms)) or float(self.start_ms) < 0:
            raise ValueError("El inicio de la nota debe ser un valor positivo.")
        if not math.isfinite(float(self.duration_ms)) or float(self.duration_ms) < 0:
            raise ValueError("La duracion de la nota debe ser un valor positivo.")
        if not 0 <= int(self.velocity) <= 127:
            raise ValueError("La velocidad MIDI debe estar entre 0 y 127.")
        if not 0 <= int(self.channel) <= 15:
            raise ValueError("El canal MIDI debe estar entre 1 y 16.")

    @property
    def end_ms(self) -> float:
        return float(self.start_ms) + float(self.duration_ms)


@dataclass(frozen=True)
class StudyStep:
    notes: Tuple[int, ...]
    start_ms: float
    end_ms: float
    note_events: Tuple[StudyNote, ...] = ()
    active_notes: Tuple[int, ...] = ()
    active_note_events: Tuple[StudyNote, ...] = ()

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class PlaybackEvent:
    event_type: str
    at_ms: float
    note: int
    velocity: int
    channel: int
    staff: Optional[int] = None


@dataclass(frozen=True)
class GuidedProgress:
    matched_notes: Tuple[int, ...]
    wrong_notes: Tuple[int, ...]
    is_complete: bool


@dataclass(frozen=True)
class ImportedMidi:
    notes: Tuple[StudyNote, ...]
    bpm: int
    channels: Tuple[int, ...]
    warnings: Tuple[str, ...]


@dataclass(frozen=True)
class ExerciseMetadata:
    exercise_id: str
    name: str
    created_at: str
    updated_at: str
    bpm: int
    note_count: int
    duration_ms: float


def normalize_notes(notes: Sequence[StudyNote]) -> List[StudyNote]:
    if not notes:
        return []
    origin = min(float(note.start_ms) for note in notes)
    return [
        StudyNote(
            note=int(note.note),
            start_ms=float(note.start_ms) - origin,
            duration_ms=float(note.duration_ms),
            velocity=int(note.velocity),
            channel=int(note.channel),
            staff=int(note.staff) if note.staff is not None else None,
            voice=str(note.voice or ""),
            fingering=str(note.fingering or ""),
        )
        for note in notes
    ]


def total_duration_ms(notes: Sequence[StudyNote]) -> float:
    normalized = normalize_notes(notes)
    return max((note.end_ms for note in normalized), default=0.0)


def channels_for_notes(notes: Sequence[StudyNote]) -> List[int]:
    return sorted({int(note.channel) for note in notes})


def filter_notes_by_channels(
    notes: Sequence[StudyNote], channels: Iterable[int]
) -> List[StudyNote]:
    selected = {int(channel) for channel in channels}
    if not selected:
        selected = set(channels_for_notes(notes))
    return normalize_notes([note for note in notes if int(note.channel) in selected])


def transpose_notes(notes: Sequence[StudyNote], semitones: int) -> List[StudyNote]:
    transposition = int(semitones)
    if transposition == 0:
        return normalize_notes(notes)

    transposed: List[StudyNote] = []
    for note in normalize_notes(notes):
        note_number = int(note.note) + transposition
        if not 0 <= note_number <= 127:
            continue
        transposed.append(
            StudyNote(
                note=note_number,
                start_ms=float(note.start_ms),
                duration_ms=float(note.duration_ms),
                velocity=int(note.velocity),
                channel=int(note.channel),
                staff=int(note.staff) if note.staff is not None else None,
                voice=str(note.voice or ""),
                fingering=str(note.fingering or ""),
            )
        )
    return normalize_notes(transposed)


def group_notes_into_steps(
    notes: Sequence[StudyNote], tolerance_ms: int = DEFAULT_CHORD_TOLERANCE_MS
) -> List[StudyStep]:
    tolerance = int(tolerance_ms)
    if tolerance < 0:
        raise ValueError("La ventana de acorde no puede ser negativa.")
    ordered = sorted(notes, key=lambda note: (note.start_ms, note.note))
    if not ordered:
        return []

    steps: List[StudyStep] = []
    step_start = float(ordered[0].start_ms)
    step_end = float(ordered[0].end_ms)
    step_notes: Set[int] = {int(ordered[0].note)}
    step_events: List[StudyNote] = [ordered[0]]

    for note in ordered[1:]:
        if float(note.start_ms) - step_start <= tolerance:
            step_notes.add(int(note.note))
            step_events.append(note)
            step_end = max(step_end, float(note.end_ms))
            continue
        steps.append(
            StudyStep(
                tuple(sorted(step_notes)),
                step_start,
                step_end,
                tuple(sorted(step_events, key=lambda event: (event.note, event.channel))),
            )
        )
        step_start = float(note.start_ms)
        step_end = float(note.end_ms)
        step_notes = {int(note.note)}
        step_events = [note]

    steps.append(
        StudyStep(
            tuple(sorted(step_notes)),
            step_start,
            step_end,
            tuple(sorted(step_events, key=lambda event: (event.note, event.channel))),
        )
    )

    resolved_steps: List[StudyStep] = []
    for step in steps:
        active_events: List[StudyNote] = list(step.note_events)
        step_event_ids = {id(event) for event in step.note_events}
        for note in ordered:
            if id(note) in step_event_ids:
                continue
            if (
                float(note.start_ms) < float(step.start_ms) - 1e-6
                and float(note.end_ms) > float(step.start_ms) + 1e-6
            ):
                active_events.append(note)
        active_events.sort(
            key=lambda event: (
                int(event.note),
                int(event.channel),
                float(event.start_ms),
            )
        )
        active_notes = tuple(sorted({int(event.note) for event in active_events}))
        resolved_steps.append(
            StudyStep(
                notes=step.notes,
                start_ms=step.start_ms,
                end_ms=step.end_ms,
                note_events=step.note_events,
                active_notes=active_notes or step.notes,
                active_note_events=tuple(active_events),
            )
        )
    return resolved_steps


def evaluate_guided_progress(
    attacked_notes: Iterable[int],
    pressed_notes: Iterable[int],
    expected_notes: Iterable[int],
) -> GuidedProgress:
    attacked = {int(note) for note in attacked_notes}
    pressed = {int(note) for note in pressed_notes}
    expected = {int(note) for note in expected_notes}
    matched = tuple(sorted(expected & attacked))
    wrong = tuple(sorted(pressed - expected))
    return GuidedProgress(
        matched_notes=matched,
        wrong_notes=wrong,
        is_complete=len(matched) == len(expected) and not wrong,
    )


def _validate_speed(speed_factor: float) -> float:
    speed = float(speed_factor)
    if not math.isfinite(speed) or not MIN_SPEED_FACTOR <= speed <= MAX_SPEED_FACTOR:
        raise ValueError(
            f"La velocidad debe estar entre {MIN_SPEED_FACTOR:.1f}x y {MAX_SPEED_FACTOR:.1f}x."
        )
    return speed


def build_original_timeline(
    notes: Sequence[StudyNote], speed_factor: float = 1.0
) -> List[PlaybackEvent]:
    speed = _validate_speed(speed_factor)
    events: List[Tuple[float, int, PlaybackEvent]] = []
    for note in normalize_notes(notes):
        start = float(note.start_ms) / speed
        duration = max(MIN_NOTE_DURATION_MS, float(note.duration_ms) / speed)
        events.append(
            (
                start,
                1,
                PlaybackEvent(
                    "note_on",
                    start,
                    note.note,
                    note.velocity,
                    note.channel,
                    note.staff,
                ),
            )
        )
        events.append(
            (
                start + duration,
                0,
                PlaybackEvent(
                    "note_off",
                    start + duration,
                    note.note,
                    0,
                    note.channel,
                    note.staff,
                ),
            )
        )
    events.sort(key=lambda item: (item[0], item[1], item[2].note, item[2].channel))
    return [event for _time, _priority, event in events]


def _append_warning(warnings: List[str], text: str) -> None:
    if len(warnings) < 100:
        warnings.append(text)


def read_midi_file(path: Path | str) -> ImportedMidi:
    midi = mido.MidiFile(str(path))
    if midi.type not in (0, 1):
        raise ValueError("Solo se admiten archivos MIDI tipo 0 y tipo 1.")
    if int(midi.ticks_per_beat) <= 0:
        raise ValueError("Los archivos MIDI con tiempo SMPTE no son compatibles.")

    tempo = 500_000
    first_bpm: Optional[int] = None
    elapsed_seconds = 0.0
    active: Dict[Tuple[int, int], List[Tuple[float, int]]] = {}
    notes: List[StudyNote] = []
    warnings: List[str] = []

    for message in mido.merge_tracks(midi.tracks):
        elapsed_seconds += mido.tick2second(
            int(message.time), int(midi.ticks_per_beat), tempo
        )
        if message.type == "set_tempo":
            tempo = int(message.tempo)
            if first_bpm is None:
                first_bpm = max(30, min(260, int(round(mido.tempo2bpm(tempo)))))
            continue
        if message.type not in ("note_on", "note_off"):
            continue

        channel = int(getattr(message, "channel", 0))
        note_number = int(message.note)
        key = (channel, note_number)
        is_note_on = message.type == "note_on" and int(message.velocity) > 0
        if is_note_on:
            active.setdefault(key, []).append(
                (elapsed_seconds * 1000.0, int(message.velocity))
            )
            continue

        queue = active.get(key, [])
        if not queue:
            _append_warning(
                warnings,
                f"NOTE OFF sin NOTE ON para {note_number} en canal {channel + 1}.",
            )
            continue
        start_ms, velocity = queue.pop(0)
        if not queue:
            active.pop(key, None)
        notes.append(
                StudyNote(
                    note=note_number,
                    start_ms=start_ms,
                    duration_ms=max(0.0, elapsed_seconds * 1000.0 - start_ms),
                    velocity=velocity,
                    channel=channel,
                )
            )

    final_ms = elapsed_seconds * 1000.0
    for (channel, note_number), queue in active.items():
        for start_ms, velocity in queue:
            _append_warning(
                warnings,
                f"NOTE ON sin NOTE OFF para {note_number} en canal {channel + 1}.",
            )
            notes.append(
                StudyNote(
                    note=note_number,
                    start_ms=start_ms,
                    duration_ms=max(MIN_NOTE_DURATION_MS, final_ms - start_ms),
                    velocity=velocity,
                    channel=channel,
                )
            )

    normalized = tuple(normalize_notes(notes))
    return ImportedMidi(
        notes=normalized,
        bpm=first_bpm or 120,
        channels=tuple(channels_for_notes(normalized)),
        warnings=tuple(warnings),
    )


def _xml_local_name(tag: str) -> str:
    return str(tag).split("}", 1)[-1]


def _xml_namespace(root: ET.Element) -> str:
    tag = str(root.tag)
    if tag.startswith("{"):
        return tag.split("}", 1)[0] + "}"
    return ""


def _xml_text(element: Optional[ET.Element], child: Optional[str] = None) -> str:
    if element is None:
        return ""
    namespace = _xml_namespace(element)
    target = element.find(f"{namespace}{child}") if child else element
    if target is None or target.text is None:
        return ""
    return target.text.strip()


def _musicxml_root(path: Path | str) -> ET.Element:
    source = Path(path)
    if source.suffix.lower() != ".mxl":
        return ET.parse(source).getroot()

    with zipfile.ZipFile(source) as archive:
        target_name = ""
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            namespace = _xml_namespace(container)
            rootfile = container.find(f".//{namespace}rootfile")
            if rootfile is not None:
                target_name = str(rootfile.attrib.get("full-path") or "")
        except Exception:
            target_name = ""
        if not target_name:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith((".musicxml", ".xml")) and not lower.startswith("meta-inf/"):
                    target_name = name
                    break
        if not target_name:
            raise ValueError("El archivo .mxl no contiene una partitura MusicXML.")
        return ET.fromstring(archive.read(target_name))


def _musicxml_first_bpm(root: ET.Element) -> int:
    namespace = _xml_namespace(root)
    for sound in root.findall(f".//{namespace}sound"):
        raw = sound.attrib.get("tempo")
        if raw:
            try:
                return max(30, min(260, int(round(float(raw)))))
            except ValueError:
                pass
    for per_minute in root.findall(f".//{namespace}per-minute"):
        raw = (per_minute.text or "").strip()
        if raw:
            try:
                return max(30, min(260, int(round(float(raw)))))
            except ValueError:
                pass
    return 120


def _musicxml_midi_from_pitch(pitch: ET.Element) -> Optional[int]:
    namespace = _xml_namespace(pitch)
    step = _xml_text(pitch, "step")
    octave = _xml_text(pitch, "octave")
    if step not in _PITCH_CLASS_FROM_STEP or not octave:
        return None
    alter_text = _xml_text(pitch, "alter")
    try:
        alter = int(round(float(alter_text or 0)))
        midi_note = (int(octave) + 1) * 12 + _PITCH_CLASS_FROM_STEP[step] + alter
    except ValueError:
        return None
    if not 0 <= midi_note <= 127:
        return None
    return midi_note


_PITCH_CLASS_FROM_STEP = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_MUSICXML_DYNAMIC_VELOCITIES = {
    "pppp": 24,
    "ppp": 36,
    "pp": 48,
    "p": 64,
    "mp": 80,
    "mf": 96,
    "f": 112,
    "ff": 120,
    "fff": 124,
    "ffff": 127,
    "sf": 116,
    "sffz": 124,
    "sfz": 120,
    "rfz": 120,
    "fp": 76,
}


def _clamp_midi_velocity(value: float | int) -> int:
    return max(1, min(127, int(round(float(value)))))


def _musicxml_numeric_velocity(raw: object) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return _clamp_midi_velocity(float(text))
    except ValueError:
        return None


def _musicxml_staff_value(note: ET.Element) -> Optional[int]:
    raw = _xml_text(note, "staff")
    if not raw:
        return None
    try:
        value = int(float(raw))
    except ValueError:
        return None
    return value if value > 0 else None


def _musicxml_fingering(note: ET.Element) -> str:
    namespace = _xml_namespace(note)
    for fingering in note.findall(f".//{namespace}fingering"):
        value = (fingering.text or "").strip()
        if value:
            return value[:12]
    return ""


def _musicxml_tie_types(note: ET.Element) -> Set[str]:
    namespace = _xml_namespace(note)
    tie_types: Set[str] = set()
    for tie in note.findall(f"{namespace}tie"):
        value = str(tie.attrib.get("type") or "").strip().lower()
        if value:
            tie_types.add(value)
    for tied in note.findall(f".//{namespace}tied"):
        value = str(tied.attrib.get("type") or "").strip().lower()
        if value:
            tie_types.add(value)
    return tie_types


def _musicxml_direction_velocity(direction: ET.Element) -> Optional[int]:
    namespace = _xml_namespace(direction)
    for sound in direction.findall(f"{namespace}sound"):
        velocity = _musicxml_numeric_velocity(sound.attrib.get("dynamics"))
        if velocity is not None:
            return velocity
    for dynamics in direction.findall(f".//{namespace}dynamics"):
        for child in list(dynamics):
            velocity = _MUSICXML_DYNAMIC_VELOCITIES.get(
                _xml_local_name(child.tag).lower()
            )
            if velocity is not None:
                return velocity
    return None


def _musicxml_note_velocity(note: ET.Element, fallback: int) -> int:
    for key in ("dynamics", "velocity"):
        velocity = _musicxml_numeric_velocity(note.attrib.get(key))
        if velocity is not None:
            return velocity
    return _clamp_midi_velocity(fallback)


def _musicxml_find_pending_tie_key(
    pending_ties: Dict[Tuple[int, Optional[int], str, int], Dict[str, object]],
    tie_key: Tuple[int, Optional[int], str, int],
) -> Optional[Tuple[int, Optional[int], str, int]]:
    if tie_key in pending_ties:
        return tie_key
    part_index, staff, voice, midi_note = tie_key
    matches = []
    for candidate in pending_ties:
        candidate_part, candidate_staff, candidate_voice, candidate_midi = candidate
        if candidate_part != part_index or candidate_midi != midi_note:
            continue
        if (
            staff is not None
            and candidate_staff is not None
            and candidate_staff != staff
        ):
            continue
        if voice and candidate_voice and candidate_voice != voice:
            continue
        matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def read_musicxml_file(path: Path | str) -> ImportedMidi:
    root = _musicxml_root(path)
    if _xml_local_name(root.tag) != "score-partwise":
        raise ValueError("Solo se admite MusicXML partwise.")

    namespace = _xml_namespace(root)
    bpm = _musicxml_first_bpm(root)
    beat_ms = 60000.0 / float(bpm)
    notes: List[StudyNote] = []
    warnings: List[str] = []

    for part_index, part in enumerate(root.findall(f"{namespace}part")):
        divisions = 1.0
        measure_offset_quarters = 0.0
        current_velocity_by_staff: Dict[Optional[int], int] = {
            None: DEFAULT_MUSICXML_VELOCITY
        }
        pending_ties: Dict[
            Tuple[int, Optional[int], str, int],
            Dict[str, object],
        ] = {}
        for measure in part.findall(f"{namespace}measure"):
            cursor_quarters = 0.0
            previous_note_start = 0.0
            measure_end_quarters = 0.0

            for child in list(measure):
                name = _xml_local_name(child.tag)
                if name == "attributes":
                    divisions_text = _xml_text(child, "divisions")
                    if divisions_text:
                        try:
                            parsed_divisions = float(divisions_text)
                            if parsed_divisions > 0:
                                divisions = parsed_divisions
                        except ValueError:
                            _append_warning(warnings, "Divisions inválido en MusicXML.")
                    continue

                if name == "backup":
                    duration_text = _xml_text(child, "duration")
                    try:
                        cursor_quarters = max(
                            0.0,
                            cursor_quarters - float(duration_text or 0) / divisions,
                        )
                    except ValueError:
                        _append_warning(warnings, "Backup inválido en MusicXML.")
                    continue

                if name == "forward":
                    duration_text = _xml_text(child, "duration")
                    try:
                        cursor_quarters += float(duration_text or 0) / divisions
                        measure_end_quarters = max(measure_end_quarters, cursor_quarters)
                    except ValueError:
                        _append_warning(warnings, "Forward inválido en MusicXML.")
                    continue

                if name == "direction":
                    velocity = _musicxml_direction_velocity(child)
                    if velocity is not None:
                        current_velocity_by_staff[_musicxml_staff_value(child)] = velocity
                    continue

                if name != "note":
                    continue
                if child.find(f"{namespace}rest") is not None:
                    duration_text = _xml_text(child, "duration")
                    try:
                        duration_quarters = float(duration_text or 0) / divisions
                    except ValueError:
                        duration_quarters = 0.0
                    if child.find(f"{namespace}chord") is None:
                        cursor_quarters += duration_quarters
                        measure_end_quarters = max(measure_end_quarters, cursor_quarters)
                    continue

                pitch = child.find(f"{namespace}pitch")
                midi_note = _musicxml_midi_from_pitch(pitch) if pitch is not None else None
                duration_text = _xml_text(child, "duration")
                try:
                    duration_quarters = float(duration_text or 0) / divisions
                except ValueError:
                    duration_quarters = 0.0
                is_chord_tone = child.find(f"{namespace}chord") is not None
                start_quarters = previous_note_start if is_chord_tone else cursor_quarters

                if midi_note is None:
                    _append_warning(warnings, "Nota MusicXML sin altura MIDI válida.")
                else:
                    staff = _musicxml_staff_value(child)
                    channel = (
                        max(0, min(15, staff - 1))
                        if staff is not None
                        else max(0, min(15, part_index))
                    )
                    voice = _xml_text(child, "voice")
                    fingering = _musicxml_fingering(child)
                    note_velocity = _musicxml_note_velocity(
                        child,
                        current_velocity_by_staff.get(
                            staff,
                            current_velocity_by_staff.get(
                                None,
                                DEFAULT_MUSICXML_VELOCITY,
                            ),
                        ),
                    )
                    start_ms = (measure_offset_quarters + start_quarters) * beat_ms
                    end_ms = start_ms + max(0.0, duration_quarters * beat_ms)
                    tie_types = _musicxml_tie_types(child)
                    has_tie_start = "start" in tie_types or "continue" in tie_types
                    has_tie_stop = "stop" in tie_types or "continue" in tie_types
                    tie_key = (part_index, staff, voice, midi_note)
                    pending_key = _musicxml_find_pending_tie_key(pending_ties, tie_key)
                    pending = pending_ties.get(pending_key) if pending_key else None

                    if has_tie_stop and pending is not None:
                        pending["end_ms"] = max(float(pending["end_ms"]), end_ms)
                        if not str(pending.get("fingering") or "").strip() and fingering:
                            pending["fingering"] = fingering
                        if not has_tie_start:
                            duration_ms = max(
                                MIN_NOTE_DURATION_MS,
                                float(pending["end_ms"]) - float(pending["start_ms"]),
                            )
                            notes.append(
                                StudyNote(
                                    note=midi_note,
                                    start_ms=float(pending["start_ms"]),
                                    duration_ms=duration_ms,
                                    velocity=int(pending["velocity"]),
                                    channel=int(pending["channel"]),
                                    staff=(
                                        int(pending["staff"])
                                        if pending.get("staff") is not None
                                        else staff
                                    ),
                                    voice=str(pending.get("voice") or voice),
                                    fingering=str(pending.get("fingering") or ""),
                                )
                            )
                            pending_ties.pop(pending_key, None)
                    elif has_tie_stop and pending is None and not has_tie_start:
                        _append_warning(
                            warnings,
                            "Ligadura MusicXML sin inicio; se importó como nota independiente.",
                        )
                        notes.append(
                            StudyNote(
                                note=midi_note,
                                start_ms=start_ms,
                                duration_ms=max(
                                    MIN_NOTE_DURATION_MS,
                                    duration_quarters * beat_ms,
                                ),
                                velocity=note_velocity,
                                channel=channel,
                                staff=staff,
                                voice=voice,
                                fingering=fingering,
                            )
                        )
                    elif has_tie_start:
                        if pending is None:
                            pending_ties[tie_key] = {
                                "start_ms": start_ms,
                                "end_ms": end_ms,
                                "velocity": note_velocity,
                                "channel": channel,
                                "staff": staff,
                                "voice": voice,
                                "fingering": fingering,
                            }
                        else:
                            pending["end_ms"] = max(float(pending["end_ms"]), end_ms)
                            if (
                                not str(pending.get("fingering") or "").strip()
                                and fingering
                            ):
                                pending["fingering"] = fingering
                    else:
                        if pending is not None:
                            _append_warning(
                                warnings,
                                "Ligadura MusicXML sin cierre; se importó hasta su última duración escrita.",
                            )
                            notes.append(
                                StudyNote(
                                    note=midi_note,
                                    start_ms=float(pending["start_ms"]),
                                    duration_ms=max(
                                        MIN_NOTE_DURATION_MS,
                                        float(pending["end_ms"])
                                        - float(pending["start_ms"]),
                                    ),
                                    velocity=int(pending["velocity"]),
                                    channel=int(pending["channel"]),
                                    staff=(
                                        int(pending["staff"])
                                        if pending.get("staff") is not None
                                        else None
                                    ),
                                    voice=str(pending.get("voice") or ""),
                                    fingering=str(pending.get("fingering") or ""),
                                )
                            )
                            pending_ties.pop(pending_key, None)
                        notes.append(
                            StudyNote(
                                note=midi_note,
                                start_ms=start_ms,
                                duration_ms=max(
                                    MIN_NOTE_DURATION_MS,
                                    duration_quarters * beat_ms,
                                ),
                                velocity=note_velocity,
                                channel=channel,
                                staff=staff,
                                voice=voice,
                                fingering=fingering,
                            )
                        )

                measure_end_quarters = max(
                    measure_end_quarters,
                    start_quarters + max(0.0, duration_quarters),
                )
                if not is_chord_tone:
                    previous_note_start = start_quarters
                    cursor_quarters += duration_quarters
                    measure_end_quarters = max(measure_end_quarters, cursor_quarters)

            measure_offset_quarters += max(measure_end_quarters, cursor_quarters)

        for tie_key, pending in pending_ties.items():
            _part_index, staff, voice, midi_note = tie_key
            _append_warning(
                warnings,
                "Ligadura MusicXML sin cierre; se importó hasta su última duración escrita.",
            )
            notes.append(
                StudyNote(
                    note=midi_note,
                    start_ms=float(pending["start_ms"]),
                    duration_ms=max(
                        MIN_NOTE_DURATION_MS,
                        float(pending["end_ms"]) - float(pending["start_ms"]),
                    ),
                    velocity=int(pending["velocity"]),
                    channel=int(pending["channel"]),
                    staff=(
                        int(pending["staff"])
                        if pending.get("staff") is not None
                        else staff
                    ),
                    voice=str(pending.get("voice") or voice),
                    fingering=str(pending.get("fingering") or ""),
                )
            )

    normalized = tuple(normalize_notes(notes))
    if not normalized:
        raise ValueError("El MusicXML no contiene notas reproducibles.")
    return ImportedMidi(
        notes=normalized,
        bpm=bpm,
        channels=tuple(channels_for_notes(normalized)),
        warnings=tuple(warnings),
    )


def read_study_file(path: Path | str) -> ImportedMidi:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in MIDI_IMPORT_EXTENSIONS:
        return read_midi_file(source)
    if suffix in MUSICXML_IMPORT_EXTENSIONS:
        return read_musicxml_file(source)
    raise ValueError("Formato no compatible. Usa MIDI, MusicXML o MXL.")


def write_midi_file(
    path: Path | str,
    notes: Sequence[StudyNote],
    bpm: int = 120,
    track_name: str = "Estudio MIDI",
) -> None:
    tempo_bpm = max(30, min(260, int(bpm)))
    ticks_per_beat = 480
    tempo = mido.bpm2tempo(tempo_bpm)
    midi = mido.MidiFile(type=0, ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=str(track_name)[:80], time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    timed_messages: List[Tuple[int, int, mido.Message]] = []
    for note in normalize_notes(notes):
        start_tick = int(
            round(mido.second2tick(note.start_ms / 1000.0, ticks_per_beat, tempo))
        )
        duration_ms = max(MIN_NOTE_DURATION_MS, float(note.duration_ms))
        end_tick = int(
            round(
                mido.second2tick(
                    (note.start_ms + duration_ms) / 1000.0,
                    ticks_per_beat,
                    tempo,
                )
            )
        )
        timed_messages.append(
            (
                start_tick,
                1,
                mido.Message(
                    "note_on",
                    note=int(note.note),
                    velocity=max(1, int(note.velocity)),
                    channel=int(note.channel),
                    time=0,
                ),
            )
        )
        timed_messages.append(
            (
                max(start_tick + 1, end_tick),
                0,
                mido.Message(
                    "note_off",
                    note=int(note.note),
                    velocity=0,
                    channel=int(note.channel),
                    time=0,
                ),
            )
        )

    timed_messages.sort(key=lambda item: (item[0], item[1], item[2].note))
    previous_tick = 0
    for tick, _priority, message in timed_messages:
        message.time = max(0, tick - previous_tick)
        track.append(message)
        previous_tick = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(path))


class StudyLibrary:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or (Path.home() / ".midi_piano_exercises"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, exercise_id: str) -> Path:
        return self.root / f"{exercise_id}.json"

    def _midi_path(self, exercise_id: str) -> Path:
        return self.root / f"{exercise_id}.mid"

    def _notes_path(self, exercise_id: str) -> Path:
        return self.root / f"{exercise_id}.notes.json"

    def list_exercises(self) -> List[ExerciseMetadata]:
        exercises: List[ExerciseMetadata] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                metadata = ExerciseMetadata(**payload)
                if self._midi_path(metadata.exercise_id).is_file():
                    exercises.append(metadata)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(exercises, key=lambda item: item.updated_at, reverse=True)

    def load_exercise(
        self, exercise_id: str
    ) -> Tuple[ExerciseMetadata, ImportedMidi]:
        payload = json.loads(
            self._metadata_path(exercise_id).read_text(encoding="utf-8")
        )
        metadata = ExerciseMetadata(**payload)
        notes_path = self._notes_path(exercise_id)
        if notes_path.is_file():
            try:
                raw_notes = json.loads(notes_path.read_text(encoding="utf-8"))
                notes = [
                    StudyNote(
                        note=int(item["note"]),
                        start_ms=float(item["start_ms"]),
                        duration_ms=float(item["duration_ms"]),
                        velocity=int(
                            item.get("velocity", DEFAULT_STUDY_NOTE_VELOCITY)
                        ),
                        channel=int(item.get("channel", 0)),
                        staff=(
                            int(item["staff"])
                            if item.get("staff") is not None
                            else None
                        ),
                        voice=str(item.get("voice") or ""),
                        fingering=str(item.get("fingering") or ""),
                    )
                    for item in raw_notes
                    if isinstance(item, dict)
                ]
                normalized = tuple(normalize_notes(notes))
                return metadata, ImportedMidi(
                    notes=normalized,
                    bpm=int(metadata.bpm),
                    channels=tuple(channels_for_notes(normalized)),
                    warnings=(),
                )
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                pass
        return metadata, read_midi_file(self._midi_path(exercise_id))

    def save_exercise(
        self,
        name: str,
        notes: Sequence[StudyNote],
        bpm: int,
        exercise_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ExerciseMetadata:
        normalized = normalize_notes(notes)
        if not normalized:
            raise ValueError("No hay notas para guardar.")
        now = datetime.now(timezone.utc).isoformat()
        identifier = str(exercise_id or uuid.uuid4())
        metadata = ExerciseMetadata(
            exercise_id=identifier,
            name=(str(name).strip() or "Nueva grabación")[:80],
            created_at=created_at or now,
            updated_at=now,
            bpm=max(30, min(260, int(bpm))),
            note_count=len(normalized),
            duration_ms=total_duration_ms(normalized),
        )

        with tempfile.TemporaryDirectory(dir=self.root) as temporary_directory:
            temporary_root = Path(temporary_directory)
            temporary_midi = temporary_root / "exercise.mid"
            temporary_json = temporary_root / "exercise.json"
            temporary_notes = temporary_root / "exercise.notes.json"
            write_midi_file(
                temporary_midi,
                normalized,
                metadata.bpm,
                metadata.name,
            )
            temporary_notes.write_text(
                json.dumps(
                    [asdict(note) for note in normalized],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_json.write_text(
                json.dumps(asdict(metadata), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_midi.replace(self._midi_path(identifier))
            temporary_notes.replace(self._notes_path(identifier))
            temporary_json.replace(self._metadata_path(identifier))
        return metadata

    def delete_exercise(self, exercise_id: str) -> None:
        for path in (
            self._metadata_path(exercise_id),
            self._midi_path(exercise_id),
            self._notes_path(exercise_id),
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                continue

    def clear(self) -> None:
        for path in self.root.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".json", ".mid"}:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
