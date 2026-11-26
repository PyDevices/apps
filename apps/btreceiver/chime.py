# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Two-note chimes for a ringing call and a new text, over the music.

`Chimes.mix` puts the music into one voice of an `audiomixer.Mixer`, which
the speaker plays in place of the music, and keeps the other voice for a
small synthio synthesizer. A chime is two sine notes pressed a moment apart,
each fading out on its own. The synthesizer plays only while a chime sounds:
left running beside the music, it takes enough of a small board's time to
starve its Bluetooth link. The music dips under each chime and comes back
after it, so the chime stands clear however loud the music is and whatever
the phone does with its own volume. The chime peaks at about -3 dBFS, and
with the music dipped the two together stay below full scale.
"""

import math
from array import array

from multimer import after

#: The two notes of each chime, in Hz: a text rises (E5, A5) and a call
#: falls (A5, E5).
NOTES = {"text": (659.25, 880.0), "call": (880.0, 659.25)}
GAP_MS = 180  # from the first note to the second
LEVEL = 0.8  # each note's peak: the chime peaks at about -3 dBFS where they overlap
DUCK = 0.18  # the music's level under a chime, about -15 dB
DUCK_MS = 50  # the music dips over this long before the first note
HOLD_MS = 800  # from the second note to when the music comes back
RISE_MS = 300  # the music comes back over this long
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
        self._silence = None
        self._missing = False
        self._rate = 0
        self._music = None
        self._ramps = False
        self._sounding = False

    def mix(self, rate, music=None):
        """An audiosample for the speaker at *rate*: *music* (an audiosample,
        or None for the chimes alone) with the chimes mixed in. On a firmware
        without audiomixer or synthio it's *music* itself, and the chimes are
        silent."""
        self.close()
        try:
            import audiocore
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
        env = synthio.Envelope(attack_time=ATTACK_S, decay_time=FADE_S, release_time=FADE_S, attack_level=1.0,
                               sustain_level=0.0)
        synth = synthio.Synthesizer(sample_rate=rate, channel_count=2, waveform=self._wave, envelope=env)
        mixer = audiomixer.Mixer(voice_count=2, sample_rate=rate, channel_count=2, bits_per_sample=16,
                                 samples_signed=True)
        if music is not None:
            mixer.voice[0].play(music, loop=True)
        # A level move walks over level_ramp frames; a mixer without it holds
        # the move to a zero crossing, which doesn't click either.
        self._ramps = hasattr(mixer, "level_ramp")
        if self._ramps:
            # On from the start: a voice's first level lands at once, and
            # walks only once the mixer has played with a ramp set.
            mixer.level_ramp = rate * DUCK_MS // 1000
        # A few frames of nothing that end by themselves: playing them in the
        # synthesizer's place lets its voice go quiet without stopping it.
        self._silence = audiocore.RawSample(array("h", [0] * 64), sample_rate=rate, channel_count=2)
        self._rate = rate
        self._music = mixer.voice[0] if music is not None else None
        self._sounding = False
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
        voice = self.mixer.voice[1]
        self._cancel()

        def done(t):
            self._timer = None
            voice.play(self._silence)
            self._sounding = False
            if self._music is not None:
                self._level(1.0, RISE_MS)

        def then(t):
            synth.press(self._note(second))
            self._timer = after(HOLD_MS, done)

        def start(t):
            if not self._sounding:
                voice.play(synth, loop=True)
                self._sounding = True
            synth.press(self._note(first))
            self._timer = after(GAP_MS, then)

        if self._music is None:
            start(None)
        else:
            self._level(DUCK, DUCK_MS)
            self._timer = after(DUCK_MS, start)
        return True

    def close(self):
        """Let the mixer and its synthesizer go, with the speaker that played
        them."""
        self._cancel()
        self.synth = None
        self.mixer = None
        self._music = None

    def _level(self, level, ms):
        """Move the music to *level* over *ms*."""
        if self._ramps:
            self.mixer.level_ramp = self._rate * ms // 1000
        self._music.level = level

    def _note(self, hz):
        return self._synthio.Note(frequency=hz, amplitude=LEVEL)

    def _cancel(self):
        t = self._timer
        self._timer = None
        if t is not None:
            t.deinit()
