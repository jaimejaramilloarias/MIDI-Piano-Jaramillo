import unittest

from PyQt6.QtCore import QIODevice

from midi_synth import PianoSynthStream


class PianoSynthStreamTests(unittest.TestCase):
    def test_generates_pcm_and_releases_voices(self):
        stream = PianoSynthStream(sample_rate=8_000, channels=2)
        stream.open(QIODevice.OpenModeFlag.ReadOnly)
        stream.note_on("voice", 69, 100)
        sounding = stream.read(2048)
        self.assertEqual(len(sounding), 2048)
        self.assertNotEqual(set(bytes(sounding)), {0})

        stream.note_off("voice")
        for _ in range(12):
            stream.read(4096)
        silent = bytes(stream.read(512))
        self.assertEqual(silent, bytes(512))
        stream.close()


if __name__ == "__main__":
    unittest.main()
