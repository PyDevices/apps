"""The engine: input -> effect slot -> master -> output.

    clip --> input mixer (loop, trim) --> effect --> master mixer
        --> DC blocker --> output

Every node is an audiodsp node; Python builds the graph and moves knobs.
The two mixers cut whatever a source hands over into 256-frame blocks and
give the input its loop and the output its master level.
"""

import audiomixer

try:
    import audiobiquad
except ImportError:
    audiobiquad = None

from . import BLOCK_FRAMES, CHANNELS, SAMPLE_RATE, effects

try:
    import audiopump
except ImportError:
    audiopump = None

_BUF = BLOCK_FRAMES * CHANNELS * 2

# A high-pass this low is inaudible on a guitar (its lowest string is 82 Hz)
# and takes out the offset some effects leave at extreme settings: MidAmp at
# tone 0 holds the output at a constant 0.23, which a speaker can only heat.
DC_BLOCK_HZ = 5


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
        it, and the recorder writing."""
        self.output.service()
        if self.playing and not self._in.voice[0].playing:
            self.playing = False
        if self._recorder is not None:
            self._recorder.service()

    # -- recording what goes out, for checking ------------------------------

    def record(self, path):
        self._recorder = Recorder(path)

    def stop_recording(self):
        r, self._recorder = self._recorder, None
        if r is not None:
            return r.close()

    def close(self):
        self.stop_recording()
        self.stop()
        self.output.close()
        if self.input is not None and hasattr(self.input, "close"):
            self.input.close()

    def latency(self):
        """(total ms, held ms, device periods ms) for a live input on a
        speaker the pump writes, or None where there is nothing to measure.

        Held is what the software path holds at this moment: the
        microphone's backlog, the ring between two clocks, and the speaker's
        queue. The periods are the Windows engine's, one each side."""
        inp, out = self.input, self.output
        if inp is None or not hasattr(inp, "held_frames") \
                or not hasattr(out, "held_frames"):
            return None
        held = inp.held_frames() + out.held_frames()
        periods = inp.period_frames() + out.period_frames()
        ms = 1000 / SAMPLE_RATE
        return (held + periods) * ms, held * ms, periods * ms


class Recorder:
    """Writes what the pump plays, through an audiopump.Tap."""

    def __init__(self, path):
        if audiopump is None:
            raise RuntimeError("recording needs audiopump")
        self.path = path
        self.tap = audiopump.Tap(frames=SAMPLE_RATE, channel_count=CHANNELS)
        audiopump.tap(self.tap)
        self._seen = self.tap.stats()[0]
        self._buf = bytearray(self.tap.stats()[4])
        self._chunks = []
        self.lost = 0

    def service(self):
        w = self.tap.stats()[0]
        new = (w - self._seen) & 0xFFFFFFFF
        if not new:
            return
        cap = len(self._buf)
        if new > cap:
            self.lost += new - cap
            new = cap
        n = self.tap.readinto(memoryview(self._buf)[:new])
        self._chunks.append(bytes(self._buf[:n]))
        self._seen = w

    def close(self):
        from . import wavfile

        self.service()
        audiopump.tap(None)
        pcm = b"".join(self._chunks)
        wavfile.write(self.path, SAMPLE_RATE, CHANNELS, pcm)
        return len(pcm) // (2 * CHANNELS)
