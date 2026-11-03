# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Input adapters. Each reports its rate, channel count and clock, and hands
the engine an audiocore source at the engine's rate and channel count.

ClipInput is a WAV clip. LiveInput is the board's microphone or line input, or
a Windows capture device, read by the pump's own thread (audioif's `Input`), so
a guitar goes through the effect with no Python in the path.
"""

import array

import audiocore

from . import CHANNELS, SAMPLE_RATE, wavfile

try:
    import audiospeed
except ImportError:  # a build without it plays clips at their own rate only
    audiospeed = None


def live_available():
    """True where there is an input to open: Windows' capture devices, or a
    board whose microphone shares its speaker's I2S clocks."""
    try:
        import _audioif
    except ImportError:
        return False
    if not hasattr(_audioif, "Input"):
        return False
    if hasattr(_audioif, "same_clock"):
        return True
    try:
        import board_peripherals as bp
    except ImportError:
        return False
    wire = getattr(getattr(bp, "AUDIO_OUT", None), "wire", None)
    return getattr(wire, "sd_in", None) is not None


class ClipInput:
    """A WAV file, held in memory, played from the start or looped."""

    kind = "clip"
    clock = "file"

    def __init__(self, path):
        self.path = path
        rate, ch, pcm = wavfile.read(path)
        if ch == 1:
            pcm = _mono_to_stereo(pcm)
        elif ch > 2:
            raise ValueError("clips with more than two channels aren't supported")
        self.file_rate = rate
        self.sample_rate = SAMPLE_RATE
        self.channel_count = CHANNELS
        self.frames = len(pcm) // CHANNELS
        self.seconds = self.frames / rate
        self._pcm = pcm

    def source(self):
        """A fresh source at the engine's rate, from the clip's first frame."""
        raw = audiocore.RawSample(self._pcm, channel_count=CHANNELS,
                                  sample_rate=self.file_rate)
        if self.file_rate == SAMPLE_RATE:
            return raw
        if audiospeed is None:
            raise ValueError("this build has no resampler for a %d Hz clip"
                             % self.file_rate)
        return audiospeed.Resampler(raw)

    def name(self):
        p = self.path.replace("\\", "/")
        return p[p.rfind("/") + 1:]


class BoardInput:
    """The board's microphone or line input: the RX half of the speaker's own
    I2S channel, so the two share a clock and the graph reads it directly.
    The output has to be open first; Engine.set_effect opens it."""

    kind = "live"
    clock = "device"
    clocks = 1
    drift = None
    name_in = "the board's input"
    target = 0

    def __init__(self, frames=128):
        import _audioif

        import board_peripherals as bp

        power = getattr(bp, "audio_in_power", None)
        if power is not None:
            power(True)
        self._power = power
        self.sample_rate = SAMPLE_RATE
        self.channel_count = CHANNELS
        self.seconds = 0
        self.file_rate = SAMPLE_RATE
        self._mic = _audioif.Input(sample_rate=SAMPLE_RATE,
                                   channel_count=CHANNELS, frames=frames)

    def source(self):
        return self._mic

    def name(self):
        return "live input"

    def close(self):
        if hasattr(self._mic, "deinit"):
            self._mic.deinit()
        if self._power is not None:
            self._power(False)


def open_live(device=None, speaker=None, clock="auto", target=None):
    import _audioif

    if hasattr(_audioif, "same_clock"):
        return LiveInput(device, speaker, clock, target=target)
    return BoardInput()


class LiveInput:
    """A Windows capture device, live. `device` is an endpoint ID, or None for
    the default.

    When the speaker is part of the same device, the two share a clock and
    the microphone feeds the graph directly: the pump reads it on its own
    thread and is paced by it. When they are different devices, their clocks
    drift apart by tens of parts per million, so the microphone writes into
    an `audiopump.Ring` on a thread of its own and an
    `audiopump.DriftResampler` reads it at the speaker's pace, holding the
    ring at `target` frames. `clock` is "auto" (ask Windows which case this
    is), "same" or "two".
    """

    kind = "live"
    clock = "device"

    # The microphone hands over 10 ms packets (480 frames) in shared mode and
    # the speaker takes 10 ms at a time, so the ring's fill swings by twice
    # that between the resampler's looks at it. 768 frames ran dry every
    # second or two on the bench; 1024 (21 ms) held with no underrun.
    RING_BLOCK = 128
    RING_BLOCKS = 64
    TARGET = 1024

    def __init__(self, device=None, speaker=None, clock="auto", frames=128,
                 target=None):
        import _audioif

        self.device = device
        self.sample_rate = SAMPLE_RATE
        self.channel_count = CHANNELS
        self.seconds = 0
        self.file_rate = SAMPLE_RATE
        self.name_in = _endpoint_name(_audioif, device, True)
        if clock == "auto":
            clock = "same" if _same_clock(_audioif, speaker, device) else "two"
        self.clocks = 1 if clock == "same" else 2
        self.ring = None
        self.drift = None
        self.target = 0
        if self.clocks == 1:
            self._mic = _audioif.Input(sample_rate=SAMPLE_RATE,
                                       channel_count=CHANNELS, frames=frames,
                                       device=device)
            self._src = self._mic
        else:
            import audiopump

            self.ring = audiopump.Ring(sample_rate=SAMPLE_RATE,
                                       channel_count=CHANNELS,
                                       frames=self.RING_BLOCK,
                                       capacity=self.RING_BLOCKS)
            # The Ring first: the microphone's thread writes into it from
            # the moment the Input exists.
            self._mic = _audioif.Input(sample_rate=SAMPLE_RATE,
                                       channel_count=CHANNELS,
                                       frames=self.RING_BLOCK, device=device,
                                       ring=self.ring)
            self.target = target or self.TARGET
            self.drift = audiopump.DriftResampler(self.ring,
                                                  target=self.target)
            self._src = self.drift

    def source(self):
        return self._src

    def name(self):
        return "live input"

    def held_frames(self):
        """Frames this side holds right now: what the microphone has waiting,
        plus the ring's fill between two clocks."""
        st = self._mic.stats()
        held = st[6]
        if self.drift is not None:
            held += self.drift.fill
        return held

    def period_frames(self):
        """The Windows engine's period for the microphone, 0 until it opens."""
        st = self._mic.stats()
        return st[8] if len(st) > 8 else 0

    def stats(self):
        return self._mic.stats()

    def close(self):
        self._mic.deinit()


def _endpoint_name(audioif, device, capture):
    try:
        return audioif.endpoint(device, capture)[1]
    except (AttributeError, OSError):
        return device or ("default input" if capture else "default output")


def _same_clock(audioif, speaker, mic):
    try:
        return audioif.same_clock(speaker, mic)
    except (AttributeError, OSError):
        # A build that can't tell: two clocks is the safe guess, since the
        # resampler holds one clock as well as two.
        return False


def _mono_to_stereo(pcm):
    out = array.array("h", bytes(4 * len(pcm)))
    try:
        out[0::2] = pcm
        out[1::2] = pcm
    except NotImplementedError:
        # MicroPython's arrays take no stepped slices.
        j = 0
        for v in pcm:
            out[j] = v
            out[j + 1] = v
            j += 2
    return out
