# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The engine: input -> effect slot -> master -> output.

    clip --> input mixer (loop, trim) --> effect --> master mixer
        --> DC blocker --> output

Every node is an audiodsp node; Python builds the graph and moves knobs.
The two mixers cut whatever a source hands over into 256-frame blocks and
give the input its loop and the output its master level.

Where the pump plays the output, a tap copies what it sends. `Engine.service`
reads the tap once and hands the audio to the level meter, and to the recorder
while there is one.
"""

from array import array

import audiomixer

try:
    import audiobiquad
except ImportError:
    audiobiquad = None

from . import BLOCK_FRAMES, CHANNELS, SAMPLE_RATE, effects
from .meter import Level

try:
    import audiopump
except ImportError:
    audiopump = None

_BUF = BLOCK_FRAMES * CHANNELS * 2

# A high-pass this low is inaudible on a guitar (its lowest string is 82 Hz)
# and takes out the offset some effects leave at extreme settings: MidAmp at
# tone 0 holds the output at a constant 0.23, which a speaker can only heat.
DC_BLOCK_HZ = 5

# The tap holds 85 ms for the meter, which is read every 10 ms, and a second
# while recording, so a slow moment on the screen loses none of the take.
METER_FRAMES = 4096
RECORD_FRAMES = SAMPLE_RATE


def _mixer():
    return audiomixer.Mixer(voice_count=1, sample_rate=SAMPLE_RATE,
                            channel_count=CHANNELS, bits_per_sample=16,
                            samples_signed=True, buffer_size=_BUF)


class Engine:
    def __init__(self, output):
        self.output = output
        self.input = None
        self.effect = None
        self.loop = True
        self.playing = False
        self.master = 0.8
        self._in = _mixer()
        self._out = _mixer()
        self._out.voice[0].level = self.master
        self._tail = self._out
        if audiobiquad is not None:
            self._dc = audiobiquad.Biquad(
                mode=audiobiquad.HIGH_PASS, frequency=DC_BLOCK_HZ, Q=0.707,
                sample_rate=SAMPLE_RATE, channel_count=CHANNELS)
            self._dc.play(self._out)
            self._tail = self._dc
        self._recorder = None
        self._started = False
        self._level = Level()
        self._tap = None
        if audiopump is not None and hasattr(audiopump, "Tap"):
            self._open_tap(METER_FRAMES)

    # -- what plays --------------------------------------------------------

    def set_input(self, inp):
        was = self.playing
        self.stop()
        old, self.input = self.input, inp
        if old is not None and old is not inp and hasattr(old, "close"):
            # A live input holds a device, and between two clocks a thread.
            old.close()
        if was:
            self.play()

    def set_effect(self, library, name):
        new = effects.make(library, name)
        new.play(self._in)
        old, self.effect = self.effect, new
        self._out.voice[0].play(new.node)
        if old is not None:
            old.stop()
            old.deinit()
        self._start_output()
        return new

    def _start_output(self):
        if not self._started:
            self.output.play(self._tail)
            self._started = True

    # -- transport ---------------------------------------------------------

    def play(self):
        if self.input is None:
            return
        self._in.voice[0].play(self.input.source(), loop=self.loop)
        self.playing = True
        self._start_output()

    def stop(self):
        self._in.voice[0].stop()
        self.playing = False

    def set_loop(self, on):
        self.loop = bool(on)
        if self.playing:
            self.play()

    def set_master(self, level):
        self.master = max(0.0, min(1.0, float(level)))
        self._out.voice[0].level = self.master

    def service(self):
        """Call from the app's loop: keeps the output fed where Python feeds
        it, the meter reading and the recorder writing."""
        self.output.service()
        if self.playing and not self._in.voice[0].playing:
            self.playing = False
        self._hear()

    # -- what went out: the meter, and a recording for checking --------------

    def _open_tap(self, frames):
        self._tap = audiopump.Tap(frames=frames, channel_count=CHANNELS)
        audiopump.tap(self._tap)
        stats = self._tap.stats()
        self._seen = stats[0]
        self._heard = array("h", bytes(stats[4]))

    def _hear(self):
        """Read what the pump has sent since the last call, once, for the
        meter and the recorder."""
        tap = self._tap
        if tap is None:
            return
        written = tap.stats()[0]
        new = (written - self._seen) & 0xFFFFFFFF
        if not new:
            return
        room = len(self._heard) * 2
        lost = 0
        if new > room:
            lost = new - room
            new = room
        n = tap.readinto(memoryview(self._heard)[:new // 2])
        self._seen = written
        if not n:
            return
        samples = memoryview(self._heard)[:n // 2]
        self._level.feed(samples)
        if self._recorder is not None:
            self._recorder.take(samples, lost)

    def level(self):
        """``(level, clipped)`` for what has played since the last call.

        The level is the peak at the effect's output as a share of full
        scale, 0.0 to 1.0, whatever the master is set to, and ``clipped`` is
        True when it came within half a decibel of full scale. Both are
        zero where no pump plays the output, as there is nothing to tap.
        """
        return self._level.read(self.master)

    def record(self, path):
        if self._tap is None:
            raise RuntimeError("recording needs audiopump")
        self._open_tap(RECORD_FRAMES)
        self._recorder = Recorder(path)

    def stop_recording(self):
        if self._recorder is None:
            return None
        self._hear()
        r, self._recorder = self._recorder, None
        self._open_tap(METER_FRAMES)
        return r.close()

    def close(self):
        self.stop_recording()
        if self._tap is not None:
            self._tap = None
            audiopump.tap(None)
        self.stop()
        self.output.close()
        if self.input is not None and hasattr(self.input, "close"):
            self.input.close()
        if self.effect is not None:
            self.effect.stop()
            self.effect.deinit()
            self.effect = None

    def latency(self):
        """(total ms, held ms, device periods ms) for a live input on a
        speaker the pump writes, or None where there is nothing to measure.

        Held is what the software path holds at this moment: the
        microphone's backlog, the ring between two clocks, and the speaker's
        queue. The periods are the device engine's, one each side."""
        inp, out = self.input, self.output
        if inp is None or not hasattr(inp, "held_frames") \
                or not hasattr(out, "held_frames"):
            return None
        held = inp.held_frames() + out.held_frames()
        periods = inp.period_frames() + out.period_frames()
        ms = 1000 / SAMPLE_RATE
        return (held + periods) * ms, held * ms, periods * ms


class Recorder:
    """Writes what the pump plays, from the audio the engine reads off its tap."""

    def __init__(self, path):
        self.path = path
        self._chunks = []
        self.lost = 0

    def take(self, samples, lost=0):
        """Keep a stretch of samples; *lost* bytes before it were overwritten."""
        self._chunks.append(bytes(samples))
        self.lost += lost

    def close(self):
        from . import wavfile

        pcm = b"".join(self._chunks)
        wavfile.write(self.path, SAMPLE_RATE, CHANNELS, pcm)
        return len(pcm) // (2 * CHANNELS)
