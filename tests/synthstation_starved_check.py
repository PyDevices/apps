# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station's starved count on a board that plays on its own I2S wire.

    python tests/synthstation_starved_check.py
    micropython tests/synthstation_starved_check.py

Runs on CPython and on unix MicroPython with ``apps/`` on the path. A
stand-in ``_audioif`` plays the part of the pump's I2S driver: it has the
byte total the DMA has clocked out and the driver's own count of bytes that
went out with no audio in them. A write to a board's flash holds off the
interrupt behind the first, so that total falls behind the clock while the
second keeps counting; `Output` must report the second. Prints ``RESULT
OK``, or ``FAIL`` lines and exit status 1.
"""

import struct
import sys

STATUS_WORDS = 34
BLOCKS, BYTES, PULL_US, SINK_BYTES = 0, 1, 12, 15
FRAME_BYTES = 4  # 16-bit stereo
BLOCK_FRAMES = 128

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL", what)


class _audioif:
    """The I2S driver's two counts, set by the script."""

    dma = 0
    starved = 0

    @staticmethod
    def i2s_start(*args, **kwargs):
        pass

    @staticmethod
    def i2s_stop(*args, **kwargs):
        pass

    @staticmethod
    def i2s_dma_bytes():
        return _audioif.dma

    @staticmethod
    def i2s_starved_bytes():
        return _audioif.starved


class audiopump:
    STATUS_WORDS = STATUS_WORDS
    STATUS_BYTES = STATUS_WORDS * 8
    words = [0] * STATUS_WORDS
    status = None

    @staticmethod
    def spawn(output, blocks, status, **kwargs):
        audiopump.status = status

    @staticmethod
    def stop(*args, **kwargs):
        pass

    @staticmethod
    def run(blocks, pull_us_each=1000):
        """*blocks* more blocks written by the pump."""
        w = audiopump.words
        nbytes = blocks * BLOCK_FRAMES * FRAME_BYTES
        w[BLOCKS] += blocks
        w[BYTES] += nbytes
        w[PULL_US] += blocks * pull_us_each
        w[SINK_BYTES] += nbytes
        struct.pack_into("<%dQ" % STATUS_WORDS, audiopump.status, 0, *w)
        return nbytes


class Wire:
    port = 0
    sck = 1
    ws = 2
    sd = 3
    mck = None
    mck_fs = 256


class AudioOut:
    wire = Wire()


class Peripherals:
    """A board with its speaker on an I2S wire."""

    AUDIO_OUT = AudioOut()


class Instrument:
    output = object()


sys.modules["board_peripherals"] = Peripherals
sys.modules["audiopump"] = audiopump
sys.modules["_audioif"] = _audioif

from synthstation.audio import Output  # noqa: E402

out = Output(None)
check(out.on_board, "a board with an I2S wire plays on it")
out.start(Instrument())

block = BLOCK_FRAMES * FRAME_BYTES
_audioif.dma += audiopump.run(20)
out.load()
check(out.underruns == 0 and out.starved_ms() == 0,
      "a pump that keeps up starves nothing: %d underruns, %d ms" % (out.underruns, out.starved_ms()))

# This thread held up between reading the two totals: the DMA total is old,
# the pump's is new. Nothing went quiet, and the driver says so.
audiopump.run(40)
out.load()
check(out.underruns == 0 and out.starved_ms() == 0,
      "a pause between two reads is not silence: %d underruns, %d ms" % (out.underruns, out.starved_ms()))
_audioif.dma = audiopump.words[SINK_BYTES]

# A flash write: 800 ms goes by, the pump writes nothing, the interrupt that
# counts the DMA's bytes is held off for all but 100 ms of it, and the
# driver's own count has the whole 800 ms.
ms = 48000 * FRAME_BYTES // 1000
_audioif.dma += 100 * ms
_audioif.starved += 800 * ms
out.load()
check(out.underruns == 1, "the write counts as one underrun: %d" % out.underruns)
check(out.starved_ms() == 800, "the silence is the driver's count, 800 ms: %d ms" % out.starved_ms())

_audioif.dma += audiopump.run(20)
out.load()
check(out.underruns == 1 and out.starved_ms() == 800,
      "no new silence, no new count: %d underruns, %d ms" % (out.underruns, out.starved_ms()))

if failures:
    print("RESULT FAIL (%d)" % len(failures))
    sys.exit(1)
print("RESULT OK")
