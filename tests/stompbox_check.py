# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Stompbox's level meter and clip light, on the real engine and the real pump.

    python tests/stompbox_check.py [--plant NAME]

Runs on CPython and on unix MicroPython, with audiodsp and this repository's
root on the path. The engine gets a stand-in output that keeps the graph it
was given, a stand-in effect that passes its input through, and inputs made
here: a quiet tone, a loud one, one flattened at full scale. The script pulls
the graph through the pump, as a speaker would, and reads the meter.

``--plant`` breaks the meter one way, and the run must then fail: see `PLANTS`.
Prints ``all passed``, or ``FAIL`` lines and exit status 1.
"""

import math
import sys
from array import array

import audiocore
import audiomixer
import audiopump

from apps.stompbox import BLOCK_FRAMES, CHANNELS, SAMPLE_RATE, effects, engine, meter, wavfile

#: Each fault a check here has to catch.
PLANTS = (
    "noclip",    # the clip light never comes on
    "nomaster",  # the meter reads the level after the master, not before it
    "sparse",    # the meter looks at one sample in forty
    "mono",      # the meter reads the two channels' sum
)

plant = None
if "--plant" in sys.argv:
    plant = sys.argv[sys.argv.index("--plant") + 1]
    if plant not in PLANTS:
        raise SystemExit("no plant %r" % plant)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL %s%s" % (what, " (plant: %s)" % plant if plant else ""))


# ---- the planted faults -----------------------------------------------------

if plant == "noclip":
    _read = meter.Level.read

    def read(self, master=1.0):
        return _read(self, master)[0], False

    meter.Level.read = read
elif plant == "nomaster":
    engine.Engine.level = lambda self: self._level.read(1.0)
elif plant == "sparse":
    _feed = meter.Level.feed
    meter.Level.feed = lambda self, samples: _feed(self, array("h", [samples[i] for i in range(0, len(samples), 40)]))
elif plant == "mono":
    _feed = meter.Level.feed
    meter.Level.feed = lambda self, samples: _feed(
        self, array("h", [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)]))


# ---- stand-ins --------------------------------------------------------------


class Out:
    """An output that keeps the graph, for the script to pull."""

    sample = None

    def play(self, sample):
        self.sample = sample

    def service(self):
        pass

    def close(self):
        pass


class Through(effects.Effect):
    """An effect that changes nothing: the meter is what's being checked."""

    library = "check"

    def __init__(self, name):
        self.name = name
        self.node = audiomixer.Mixer(
            voice_count=1, sample_rate=SAMPLE_RATE, channel_count=CHANNELS, bits_per_sample=16,
            samples_signed=True, buffer_size=BLOCK_FRAMES * CHANNELS * 2)

    def play(self, source):
        self.node.voice[0].play(source)

    def stop(self):
        self.node.voice[0].stop()


effects.LIBRARIES["check"] = Through


class RacingTap:
    """A tap whose pump sends one more block just before every third read."""

    def __init__(self, tap, send):
        self._tap = tap
        self._send = send
        self._reads = 0

    def stats(self):
        return self._tap.stats()

    def readinto(self, buf):
        self._reads += 1
        if self._reads % 3 == 0:
            self._send()
        return self._tap.readinto(buf)


class Clip:
    """An input that loops *frames* of stereo samples."""

    kind = "clip"

    def __init__(self, left, right=None):
        right = left if right is None else right
        data = array("h", bytes(len(left) * 4))
        for i in range(len(left)):
            data[2 * i] = left[i]
            data[2 * i + 1] = right[i]
        self._data = data
        self.seconds = len(left) / SAMPLE_RATE

    def source(self):
        return audiocore.RawSample(self._data, channel_count=CHANNELS, sample_rate=SAMPLE_RATE)


TONE_FRAMES = 4800  # 100 ms, a whole number of 480 Hz cycles


def tone(gain):
    """480 Hz at *gain* of full scale; past 1.0 its tops are flattened there."""
    out = []
    for i in range(TONE_FRAMES):
        v = int(gain * 32767 * math.sin(2 * math.pi * 480 * i / SAMPLE_RATE))
        out.append(max(-32767, min(32767, v)))
    return out


SILENCE = [0] * TONE_FRAMES
QUIET = 10 ** (-39 / 20)
LOUD = 10 ** (-5 / 20)

status = bytearray(audiopump.STATUS_BYTES)


def play(eng, out, inp, ms=200):
    """Loop *inp* through the engine for *ms*, read as the app's tick reads it.

    Returns ``(level, clipped)`` over the second half, once the input's start
    has passed through the DC blocker.
    """
    eng.set_input(inp)
    eng.play()
    blocks = ms * SAMPLE_RATE // (1000 * BLOCK_FRAMES)
    for i in range(blocks):
        audiopump.pull(out.sample, 1, status)
        eng.service()
        if i == blocks // 2:
            eng.level()
    return eng.level()


def db(level):
    return 20 * math.log10(level) if level > 0 else -100.0


def near(level, want_db, within=0.3):
    return abs(db(level) - want_db) <= within


def main():
    out = Out()
    eng = engine.Engine(out)
    eng.set_effect("check", "through")
    check(eng.level() == (0.0, False), "before anything plays the meter reads nothing")

    for master in (0.8, 0.25, 1.0):
        eng.set_master(master)
        at = "master at %d%%" % (master * 100)
        # Under a low master a quiet tone is under a hundred steps tall, so it reads within a decibel.
        level, clipped = play(eng, out, Clip(tone(QUIET)))
        check(near(level, -39, 1.0) and not clipped, "%s: a quiet tone reads -39 dB and no clip (%.1f dB, %r)" % (at, db(level), clipped))
        check(meter.steps(level) == 4, "%s: that lights 4 of the bar's %d steps (%d)" % (at, meter.STEPS, meter.steps(level)))
        level, clipped = play(eng, out, Clip(tone(LOUD)))
        check(near(level, -5) and not clipped, "%s: a loud tone reads -5 dB and no clip (%.1f dB, %r)" % (at, db(level), clipped))
        check(meter.steps(level) == 21, "%s: that lights 21 steps (%d)" % (at, meter.steps(level)))
        level, clipped = play(eng, out, Clip(tone(0.9)))
        check(near(level, -0.9) and not clipped, "%s: a tone 0.9 dB under full scale doesn't clip (%.1f dB, %r)" % (at, db(level), clipped))
        level, clipped = play(eng, out, Clip(tone(1.5)))
        check(clipped and near(level, 0), "%s: a tone flattened at full scale clips (%.1f dB, %r)" % (at, db(level), clipped))
        check(meter.steps(level) == meter.STEPS, "%s: and fills the bar (%d)" % (at, meter.steps(level)))
        print("ok  %-14s quiet, loud, nearly full and flattened tones read right" % at)

    eng.set_master(0.8)
    level, clipped = play(eng, out, Clip(SILENCE, tone(1.5)))
    check(clipped, "a clip on the right channel alone lights the light (%.1f dB, %r)" % (db(level), clipped))
    level, clipped = play(eng, out, Clip(tone(1.5), [-v for v in tone(1.5)]))
    check(clipped, "a clip with the two channels out of phase lights it (%.1f dB, %r)" % (db(level), clipped))
    one = list(SILENCE)
    one[1237] = 32767
    level, clipped = play(eng, out, Clip(one))
    check(clipped, "one sample at full scale lights it (%.1f dB, %r)" % (db(level), clipped))
    level, clipped = play(eng, out, Clip(SILENCE))
    check(level == 0.0 and not clipped, "silence reads nothing again (%r, %r)" % (level, clipped))
    check(eng.level() == (0.0, False), "a read with nothing new played reads nothing")
    eng.set_master(0.0)
    check(play(eng, out, Clip(tone(1.5))) == (0.0, False), "with the master at 0 the meter reads nothing")
    eng.set_master(0.8)
    print("ok  one channel, out of phase, a single sample, silence")

    # A tick that comes late brings more than the tap holds: the meter reads the newest.
    eng.set_input(Clip(tone(1.5)))
    eng.play()
    audiopump.pull(out.sample, 4 * engine.METER_FRAMES // BLOCK_FRAMES, status)
    eng.service()
    level, clipped = eng.level()
    check(clipped, "after a late tick the meter reads what played last (%.1f dB, %r)" % (db(level), clipped))

    # The recorder and the meter share the tap, and neither takes the other's audio.
    path = "stompbox_check.wav"
    eng.set_input(Clip(tone(LOUD)))
    eng.play()
    eng.service()
    eng.level()
    eng.record(path)
    blocks = 40
    for _ in range(blocks):
        audiopump.pull(out.sample, 1, status)
        eng.service()
    level, clipped = eng.level()
    frames = eng.stop_recording()
    check(frames == blocks * BLOCK_FRAMES, "a recording holds every frame played (%r of %d)" % (frames, blocks * BLOCK_FRAMES))
    check(near(level, -5) and not clipped, "the meter reads while a recording runs (%.1f dB)" % db(level))
    level, clipped = play(eng, out, Clip(tone(1.5)))
    check(clipped, "and after it stops (%.1f dB, %r)" % (db(level), clipped))

    # The pump adds a block between the count and the read: the take runs on unbroken.
    eng.set_input(Clip(tone(LOUD)))
    eng.play()
    eng.service()
    eng.record(path)
    eng._tap = RacingTap(eng._tap, lambda: audiopump.pull(out.sample, 1, status))
    for _ in range(blocks):
        audiopump.pull(out.sample, 1, status)
        eng.service()
    eng.stop_recording()
    pcm = wavfile.read(path)[2]
    steepest = max(abs(pcm[i] - pcm[i - 2]) for i in range(2, len(pcm), 2))
    limit = 1.2 * LOUD * 32767 * 2 * math.pi * 480 / SAMPLE_RATE
    check(steepest <= limit, "a block arriving during a read leaves no splice (a step of %d, at most %d)" % (steepest, limit))
    import os

    os.remove(path)
    print("ok  a late tick, a recording beside the meter, and a block arriving during a read")

    eng.close()
    check(audiopump.tap() is None, "close lets go of the pump's tap")


main()
if failures:
    print("%d failed" % len(failures))
    sys.exit(1)
print("all passed")
