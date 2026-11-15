# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station's cost and underrun readings on a board that plays through ``audio_out``.

    python tests/synthstation_output_check.py
    micropython tests/synthstation_output_check.py

Runs on CPython and on unix MicroPython with ``apps/`` on the path, and needs
neither LVGL nor audiodsp. A stand-in ``board_peripherals`` has no I2S wire
of its own, so `Output` plays through its ``audio_out``, which reports
``pumped``; a stand-in pump owner hands back a status block the script
writes, the way the pump's loop would. Prints ``RESULT OK``, or ``FAIL``
lines and exit status 1.
"""

import struct
import sys

STATUS_WORDS = 34
BLOCKS, BYTES, PULL_US, SINK_BYTES, DMA_BYTES = 0, 1, 12, 15, 21
FRAME_BYTES = 4  # 16-bit stereo
BLOCK_FRAMES = 256  # audio_out's block, not the 128 Synth Station gives its own I2S

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL", what)


class Owner:
    """audiodev's pump owner: one status block and a health() that never sees a gap."""

    def __init__(self):
        self.block = bytearray(STATUS_WORDS * 8)
        self.words = [0] * STATUS_WORDS
        self.dropped = 0

    def status(self):
        struct.pack_into("<%dQ" % STATUS_WORDS, self.block, 0, *self.words)
        return self.block

    def health(self):
        return {"dropped": self.dropped}

    def run(self, blocks, pull_us_each, clocked_out=None):
        """*blocks* more blocks, each *pull_us_each* to render.

        The DMA clocks out *clocked_out* bytes meanwhile: by default what the
        pump wrote, so the speaker never runs dry.
        """
        w = self.words
        nbytes = blocks * BLOCK_FRAMES * FRAME_BYTES
        w[BLOCKS] += blocks
        w[BYTES] += nbytes
        w[PULL_US] += blocks * pull_us_each
        w[SINK_BYTES] += nbytes
        w[DMA_BYTES] += nbytes if clocked_out is None else clocked_out


OWNER = Owner()


class pump:
    @staticmethod
    def owner():
        return OWNER


class AudioFormat:
    def __init__(self, rate, channels, bits):
        self.rate = rate


class audiodev:
    AudioFormat = AudioFormat
    pump = pump


class audiopump:
    STATUS_WORDS = STATUS_WORDS
    STATUS_BYTES = STATUS_WORDS * 8


class Out:
    pumped = True

    def attach(self, scope):
        pass

    def play(self, sample):
        pass

    def stop(self):
        pass

    def detach(self):
        pass

    def close(self):
        pass


class Peripherals:
    """A board with a speaker behind ``audio_out`` and no ``AUDIO_OUT`` wire."""

    AUDIO_OUT = None

    @staticmethod
    def audio_out(fmt, **kwargs):
        return Out()


class Instrument:
    output = object()


sys.modules["board_peripherals"] = Peripherals
sys.modules["audiopump"] = audiopump
sys.modules["audiodev"] = audiodev
sys.modules["audiodev.pump"] = pump

from synthstation.audio import Output  # noqa: E402

out = Output(None)
check(not out.on_board, "a board with no I2S wire plays through audio_out")
out.start(Instrument())

# ---- the voice cap's two readings ---------------------------------------------

check(out.pull_us() is None, "pull_us is None before a block has landed")
OWNER.run(8, 3000)
cost = out.pull_us()
check(cost == 3000, "pull_us reads the blocks' mean render time through audio_out: %r" % (cost,))
check(out.block_us() == BLOCK_FRAMES * 1000000 // 48000,
      "block_us is audio_out's block, not the app's own I2S block: %r" % (out.block_us(),))
check(out.pull_us() is None, "pull_us is None when no block has landed since the last read")

# ---- the underrun count ---------------------------------------------------------

block = BLOCK_FRAMES * FRAME_BYTES
OWNER.run(0, 0, clocked_out=2 * block)  # the ring clocks silence before the first block lands
out.load()
check(out.underruns == 0, "the silence before the first block isn't an underrun: %d" % out.underruns)
OWNER.run(20, 2000, clocked_out=20 * block)
out.load()
check(out.underruns == 0, "a pump that keeps up counts no underrun: %d" % out.underruns)
OWNER.run(10, 6500, clocked_out=14 * block)  # the DMA ran 4 blocks of silence
out.load()
check(out.underruns == 1, "the DMA outrunning the pump counts an underrun: %d" % out.underruns)
check(OWNER.health()["dropped"] == 0, "the owner's dropped count stays 0 (what the readout used to show)")
check(out.starved_ms() == 4 * BLOCK_FRAMES * 1000 // 48000, "the silence heard is the gap: %d ms" % out.starved_ms())
OWNER.run(10, 6500, clocked_out=12 * block)
out.load()
check(out.underruns == 2, "a second gap counts again: %d" % out.underruns)
OWNER.run(10, 2000, clocked_out=10 * block)
out.load()
check(out.underruns == 2, "no new gap, no new count: %d" % out.underruns)

# ---- a computer's pump has no I2S: its dropped blocks are the count ---------------

out.stop()
OWNER.__init__()
out.start(Instrument())
OWNER.run(10, 1000, clocked_out=0)
out.load()
OWNER.dropped = 3
OWNER.run(10, 1000, clocked_out=0)
out.load()
check(out.underruns == 3, "with no I2S count, underruns are the owner's dropped blocks: %d" % out.underruns)

if failures:
    print("RESULT FAIL", len(failures))
    sys.exit(1)
print("RESULT OK")
