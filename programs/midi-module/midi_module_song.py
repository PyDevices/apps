# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A short General MIDI loop as raw bytes, for the MIDI module's self-test.

Four bars (C, A minor, F, G) on a piano, strings, a fingered bass and the
drum channel, one sixteenth note per step. step(n) returns what to send at
step n, note-offs first.
"""

PIANO, STRINGS, BASS, DRUMS = 0, 1, 2, 9  # channels 1, 2, 3 and 10
CHORDS = ((60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62))
KICK, SNARE, HAT = 36, 38, 42

# Program changes: Acoustic Grand Piano, String Ensemble 1, Electric Bass
# (finger); some reverb on each.
SETUP = bytes((0xC0 | PIANO, 0, 0xC0 | STRINGS, 48, 0xC0 | BASS, 33,
               0xB0 | PIANO, 91, 50, 0xB0 | STRINGS, 91, 70, 0xB0 | STRINGS, 7, 80))

_held = []  # (channel, note) sounding now


def _on(out, channel, note, velocity):
    out.extend((0x90 | channel, note, velocity))
    _held.append((channel, note))


def step(n):
    """The bytes for sixteenth ``n`` of the loop."""
    out = bytearray()
    bar, pos = divmod(n % 64, 16)
    chord = CHORDS[bar]
    # Let go of the notes whose time is up: the piano, bass and drums every
    # eighth, the strings at the bar.
    keep = []
    for channel, note in _held:
        if channel in (PIANO, BASS, DRUMS) and pos % 2 == 0 or pos == 0:
            out.extend((0x80 | channel, note, 0))
        else:
            keep.append((channel, note))
    _held[:] = keep
    if pos == 0:
        for note in chord:
            _on(out, STRINGS, note, 70)
    if pos % 4 == 0:
        for note in chord:
            _on(out, PIANO, note + 12, 90)
    if pos % 2 == 0:
        _on(out, BASS, chord[0] - 24, 100)
        _on(out, DRUMS, HAT, 60)
    if pos in (0, 6, 8):
        _on(out, DRUMS, KICK, 110)
    if pos in (4, 12):
        _on(out, DRUMS, SNARE, 100)
    return bytes(out)
