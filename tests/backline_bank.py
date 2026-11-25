# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A tiny General MIDI drum bank for Backline's tests, on any interpreter.

`write` makes a SoundFont with one decaying tone on each of `PADS`, the two
hats in one exclusive class, as a real kit chokes its open hat. `use` makes it
the bank the ``soundfont`` kit plays, so a test never needs Backline's own
bank or a network.
"""

import math
import struct

PADS = (36, 38, 42, 46, 49)
HATS = (42, 46)
RATE = 48000


def _chunk(cid, body):
    return cid + struct.pack("<I", len(body)) + body + b"\0" * (len(body) & 1)


def _name(text):
    return (text + b"\0" * 20)[:20]


def write(path, rate=RATE):
    """Write the bank to ``path``."""
    smpl = bytearray()
    shdr = bytearray()
    igen = bytearray()
    ibag = bytearray()
    for i, pitch in enumerate(PADS):
        n = rate // 5
        hz = 80.0 + 140.0 * i
        start = len(smpl) // 2
        for k in range(n):
            v = int(20000 * math.exp(-k / 2400.0) * math.sin(2 * math.pi * hz * k / rate))
            smpl += struct.pack("<h", v)
        smpl += bytes(92)  # the 46 zero samples SoundFont wants after each one
        shdr += _name(b"pad%d" % pitch) + struct.pack("<5IbbHH", start, start + n, start, start + n, rate, 60, 0, 0, 1)
        ibag += struct.pack("<HH", len(igen) // 4, 0)
        igen += struct.pack("<HBB", 43, pitch, pitch)
        if pitch in HATS:
            igen += struct.pack("<HH", 57, 1)
        igen += struct.pack("<HH", 58, pitch) + struct.pack("<HH", 53, i)
    ibag += struct.pack("<HH", len(igen) // 4, 0)
    igen += bytes(4)
    shdr += _name(b"EOS") + bytes(26)
    pdta = b"".join((
        _chunk(b"phdr", _name(b"Standard") + struct.pack("<HHH3I", 0, 128, 0, 0, 0, 0)
               + _name(b"EOP") + struct.pack("<HHH3I", 0, 0, 1, 0, 0, 0)),
        _chunk(b"pbag", struct.pack("<4H", 0, 0, 1, 0)),
        _chunk(b"pmod", bytes(10)),
        _chunk(b"pgen", struct.pack("<HH", 41, 0) + bytes(4)),
        _chunk(b"inst", _name(b"Drums") + struct.pack("<H", 0) + _name(b"EOI") + struct.pack("<H", len(PADS))),
        _chunk(b"ibag", bytes(ibag)),
        _chunk(b"imod", bytes(10)),
        _chunk(b"igen", bytes(igen)),
        _chunk(b"shdr", bytes(shdr)),
    ))
    info = _chunk(b"ifil", struct.pack("<HH", 2, 1)) + _chunk(b"isng", b"EMU8000\0") + _chunk(b"INAM", b"Test tones\0\0")
    body = (b"sfbk" + _chunk(b"LIST", b"INFO" + info) + _chunk(b"LIST", b"sdta" + _chunk(b"smpl", bytes(smpl)))
            + _chunk(b"LIST", b"pdta" + pdta))
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def use(folder):
    """Write the bank into ``folder`` and make it the one Backline's
    ``soundfont`` kit plays, in place of its own; returns its path."""
    from backline import kits

    path = write(folder + "/test-drums.sf2")
    kits.default_bank = lambda: path
    kits.find_bank = lambda: path
    return path
