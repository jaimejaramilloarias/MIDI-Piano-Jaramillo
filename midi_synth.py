from __future__ import annotations

import math
import threading
from array import array
from dataclasses import dataclass
from typing import Dict, Hashable, Optional

from PyQt6.QtCore import QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices


@dataclass
class _Voice:
    note: int
    velocity: int
    phase: float = 0.0
    age_samples: int = 0
    release_samples: Optional[int] = None
    release_level: float = 0.0


class PianoSynthStream(QIODevice):
    """Small pull-based polyphonic synth used for local practice playback."""

    ATTACK_SECONDS = 0.008
    DECAY_SECONDS = 0.72
    SUSTAIN_LEVEL = 0.28
    RELEASE_SECONDS = 0.12

    def __init__(self, sample_rate: int = 44_100, channels: int = 2) -> None:
        super().__init__()
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.master_volume = 0.25
        self._voices: Dict[Hashable, _Voice] = {}
        self._lock = threading.RLock()

    def note_on(self, voice_id: Hashable, note: int, velocity: int) -> None:
        if not 0 <= int(note) <= 127 or int(velocity) <= 0:
            return
        with self._lock:
            self._voices[voice_id] = _Voice(
                note=int(note), velocity=max(1, min(127, int(velocity)))
            )

    def note_off(self, voice_id: Hashable) -> None:
        with self._lock:
            voice = self._voices.get(voice_id)
            if voice is None or voice.release_samples is not None:
                return
            voice.release_level = self._envelope(voice)
            voice.release_samples = 0

    def panic(self) -> None:
        with self._lock:
            self._voices.clear()

    def _envelope(self, voice: _Voice) -> float:
        age = voice.age_samples / self.sample_rate
        if age < self.ATTACK_SECONDS:
            level = age / self.ATTACK_SECONDS
        else:
            decay_age = age - self.ATTACK_SECONDS
            level = self.SUSTAIN_LEVEL + (
                1.0 - self.SUSTAIN_LEVEL
            ) * math.exp(-decay_age / self.DECAY_SECONDS)
        if voice.release_samples is None:
            return level
        release_age = voice.release_samples / self.sample_rate
        release_factor = max(0.0, 1.0 - release_age / self.RELEASE_SECONDS)
        return voice.release_level * release_factor * release_factor

    def readData(self, max_length: int) -> bytes:  # noqa: N802 - Qt API
        bytes_per_frame = self.channels * 2
        frame_count = max(0, int(max_length) // bytes_per_frame)
        if frame_count <= 0:
            return b""

        samples = array("h")
        with self._lock:
            voice_items = list(self._voices.items())
            voice_count = max(1, len(voice_items))
            mix_scale = self.master_volume / math.sqrt(voice_count)
            finished = set()

            for _frame in range(frame_count):
                mixed = 0.0
                for voice_id, voice in voice_items:
                    envelope = self._envelope(voice)
                    if envelope <= 0.0001 and voice.release_samples is not None:
                        finished.add(voice_id)
                        continue
                    frequency = 440.0 * (2.0 ** ((voice.note - 69) / 12.0))
                    phase_step = math.tau * frequency / self.sample_rate
                    wave = (
                        math.sin(voice.phase)
                        + 0.24 * math.sin(voice.phase * 2.0)
                        + 0.10 * math.sin(voice.phase * 3.0)
                    ) / 1.34
                    velocity = voice.velocity / 127.0
                    mixed += wave * envelope * velocity
                    voice.phase = (voice.phase + phase_step) % math.tau
                    voice.age_samples += 1
                    if voice.release_samples is not None:
                        voice.release_samples += 1

                sample = max(-1.0, min(1.0, mixed * mix_scale))
                value = int(sample * 32767)
                for _channel in range(self.channels):
                    samples.append(value)

            for voice_id in finished:
                self._voices.pop(voice_id, None)

        return samples.tobytes()

    def writeData(self, data: bytes) -> int:  # noqa: N802 - Qt API
        del data
        return -1

    def bytesAvailable(self) -> int:  # noqa: N802 - Qt API
        return 8192 + super().bytesAvailable()


class LocalPianoSynth:
    """Lazy QAudioSink wrapper that degrades cleanly on machines without audio."""

    def __init__(self) -> None:
        self.stream = PianoSynthStream()
        self.sink: Optional[QAudioSink] = None
        self.error_message = ""

    @property
    def is_available(self) -> bool:
        return self.sink is not None

    def ensure_started(self) -> bool:
        if self.sink is not None:
            return True
        try:
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                self.error_message = "No hay una salida de audio disponible."
                return False
            audio_format = QAudioFormat()
            audio_format.setSampleRate(self.stream.sample_rate)
            audio_format.setChannelCount(self.stream.channels)
            audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not device.isFormatSupported(audio_format):
                audio_format = device.preferredFormat()
                if audio_format.sampleFormat() != QAudioFormat.SampleFormat.Int16:
                    self.error_message = "La salida de audio no admite el formato del sintetizador."
                    return False
                self.stream.sample_rate = audio_format.sampleRate()
                self.stream.channels = audio_format.channelCount()
            self.stream.open(QIODevice.OpenModeFlag.ReadOnly)
            self.sink = QAudioSink(device, audio_format)
            self.sink.setBufferSize(max(8192, audio_format.bytesForDuration(80_000)))
            self.sink.start(self.stream)
            self.error_message = ""
            return True
        except Exception as exc:
            self.error_message = f"No se pudo iniciar el audio local: {exc}"
            self.sink = None
            return False

    def note_on(
        self, voice_id: Hashable, note: int, velocity: int = 100
    ) -> bool:
        if not self.ensure_started():
            return False
        self.stream.note_on(voice_id, note, velocity)
        return True

    def note_off(self, voice_id: Hashable) -> None:
        self.stream.note_off(voice_id)

    def panic(self) -> None:
        self.stream.panic()

    def close(self) -> None:
        self.stream.panic()
        if self.sink is not None:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = None
        self.stream.close()
