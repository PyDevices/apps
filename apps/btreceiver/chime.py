# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Soft two-note chimes for a ringing call and a new text, over the music.

`Chimes.mix` puts the music and a small synthio synthesizer into one
`audiomixer.Mixer`, which the speaker plays in place of the music. A chime is
two sine notes pressed a moment apart, each fading out on its own, so nothing
has to stop them. Both stay well below full scale: a chime is heard over
quiet music, or in the gap the phone leaves when it pauses for a call.
"""

import math
from array import array

from multimer import after

#: The two notes of each chime, in Hz: a text rises (E5, A5) and a call
#: falls (A5, E5).
NOTES = {"text": (659.25, 880.0), "call": (880.0, 659.25)}
GAP_MS = 180  # from the first note to the second
LEVEL = 0.18  # each note's peak: the chime peaks at about -16 dBFS where they overlap
ATTACK_S = 0.006  # long enough not to click
FADE_S = 0.8  # each note fades from its peak to nothing over this long
WAVE_POINTS = 256


class Chimes:
    """The chimes, and the mixer that carries them beside the music."""

    def __init__(self):
        self.synth = None
        self.mixer = None
        #: The chimes asked for, oldest first: "text" or "call". The last 8.
        self.played = []
        self._synthio = None
        self._timer = None
        self._wave = None
        self._missing = False

    def mix(self, rate, music=None):
        """An audiosample for the speaker at *rate*: *music* (an audiosample,
        or None for the chimes alone) with the chimes mixed in. On a firmware
        without audiomixer or synthio it's *music* itself, and the chimes are
        silent."""
        self.close()
        try:
            import audiomixer
            import synthio
        except ImportError as e:
            if not self._missing:
                self._missing = True
                print("btreceiver: no chimes:", e)
            return music
        if self._wave is None:
            self._wave = array("h", [int(32767 * math.sin(2 * math.pi * i / WAVE_POINTS)) for i in range(WAVE_POINTS)])
        # sustain_level 0: each note fades from its peak and frees itself.
        env = synthio.Envelope(attack_time=ATTACK_S, decay_time=FADE_S, release_time=FADE_S, attack_level=1.0, sustain_level=0.0)
        synth = synthio.Synthesizer(sample_rate=rate, channel_count=2, waveform=self._wave, envelope=env)
        mixer = audiomixer.Mixer(voice_count=2, sample_rate=rate, channel_count=2, bits_per_sample=16,
                                 samples_signed=True)
        if music is not None:
            mixer.voice[0].play(music, loop=True)
        mixer.voice[1].play(synth, loop=True)
        self._synthio = synthio
        self.synth = synth
        self.mixer = mixer
        return mixer

    def play(self, kind):
        """Chime *kind*, "text" or "call". False when there's no speaker to
        play it on."""
        self.played.append(kind)
        del self.played[:-8]
        synth = self.synth
        if synth is None:
            return False
        first, second = NOTES[kind]
        self._cancel()
        synth.press(self._note(first))

        def then(t):
            self._timer = None
            synth.press(self._note(second))

        self._timer = after(GAP_MS, then)
        return True

    def close(self):
        """Let the mixer and its synthesizer go, with the speaker that played
        them."""
        self._cancel()
        self.synth = None
        self.mixer = None

    def _note(self, hz):
        return self._synthio.Note(frequency=hz, amplitude=LEVEL)

    def _cancel(self):
        t = self._timer
        self._timer = None
        if t is not None:
            t.deinit()
