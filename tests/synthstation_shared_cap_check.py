# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station's voice cap, shared by every instrument playing.

    python tests/synthstation_shared_cap_check.py
    micropython tests/synthstation_shared_cap_check.py

Runs on CPython and on unix MicroPython with ``apps/`` on the path, and needs
neither LVGL nor audiodsp. Three stand-in instruments play at once, as on
MIDI channels 1, 2 and 10: a six-voice synth, a sixteen-voice organ and a
drum kit. A stand-in output reads back what their sounding voices would cost
to render, and the app's own fill timer runs the governor. Prints
``RESULT OK``, or ``FAIL`` lines and exit status 1.
"""

import sys


class _Lvgl:
    """Enough of ``lvgl`` for the app's modules to import."""


try:
    import lvgl  # noqa: F401
except ImportError:
    sys.modules["lvgl"] = _Lvgl()

from synthstation import station  # noqa: E402
from synthstation.station import Station  # noqa: E402

BLOCK_US = 5333  # 256 frames at 48 kHz: what audio_out pulls through a mix
IDLE_US = 2000  # the three instruments and the mix, with nothing sounding
#: The governor aims at `station.BUDGET` of a block and rounds to the nearest
#: voice; the speaker starves only past the whole block.
BUDGET_US = station.BUDGET * BLOCK_US
SYNTH_CHORD = (60, 64, 67, 71, 74, 77)
ORGAN_CHORD = (36, 43, 48, 52, 55)
PADS = (36, 42)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL", what)


class Pool:
    def __init__(self, inst):
        self.inst = inst

    def sounding(self):
        return len(self.inst.held)


class Instrument:
    """Plays notes on up to ``voices`` voices; a new one steals the oldest."""

    def __init__(self, voices, cost_us):
        self._voices = voices
        self.cost_us = cost_us
        self.held = []
        self.voice_pool = Pool(self)
        self.dropped = 0

    @property
    def voices(self):
        return self._voices

    @voices.setter
    def voices(self, count):
        if count < 1:
            raise ValueError("an instrument has at least one voice")
        self._voices = count
        while len(self.held) > count:
            self.held.pop(0)
            self.dropped += 1

    def note_on(self, note):
        if note in self.held:
            self.held.remove(note)
        elif len(self.held) >= self._voices:
            self.held.pop(0)
            self.dropped += 1
        self.held.append(note)

    def note_off(self, note):
        if note in self.held:
            self.held.remove(note)

    def fill(self):
        pass


class Kit(Instrument):
    """A drum machine: a voice per sound, each a circuit of its own."""

    def note_on(self, note):
        if note not in self.held:
            self.held.append(note)


class Adapter:
    def __init__(self, inst):
        self.instrument = inst


class Part:
    def __init__(self, inst, most):
        self.adapter = Adapter(inst)
        self.most = most


class Output:
    """Reads back what the parts' sounding voices cost, as the pump would."""

    def __init__(self, parts):
        self.parts = parts

    def cost(self):
        us = IDLE_US
        for part in self.parts:
            inst = part.adapter.instrument
            us += inst.cost_us * len(inst.held)
        return us

    def pull_us(self):
        return self.cost()

    def block_us(self):
        return BLOCK_US


class Rig(Station):
    """A Station with only what its fill timer and governor touch."""

    def __init__(self, parts):
        self.output = Output(parts)
        self._playing = tuple(parts)
        self.adapter = parts[0].adapter
        self._filling = False
        self.loading = False
        self._fills = 0
        self._played = 0
        self._idle_us = None
        self._settle = 0
        self._cap = None
        self._fitted = 0
        self._raised = False
        self._read = None
        self._refused = None
        self._mix = None

    def strike(self, part, notes, fills=0):
        """Play *notes* on *part*, as the MIDI timer does, with *fills* after each."""
        for note in notes:
            part.adapter.instrument.note_on(note)
            self._played = 2
            self.run(fills)

    def lift(self, part, notes):
        for note in notes:
            part.adapter.instrument.note_off(note)

    def run(self, fills):
        for _ in range(fills):
            self._fill()


def main():
    synth = Part(Instrument(6, 400), 6)
    organ = Part(Instrument(16, 300), 16)
    kit = Part(Kit(16, 120), 1)
    rig = Rig([synth, organ, kit])
    s, o, k = synth.adapter.instrument, organ.adapter.instrument, kit.adapter.instrument
    rig.run(20)  # idle reads first, as when the app opens

    # Six keys on the synth, five on the organ, the kick and the hat: uncapped,
    # that takes longer than a block lasts.
    loud = IDLE_US + len(SYNTH_CHORD) * 400 + len(ORGAN_CHORD) * 300 + len(PADS) * 120
    check(loud > BLOCK_US, "the chords uncapped overrun (%d of %d us)" % (loud, BLOCK_US))
    worst = 0
    for bar in range(8):
        rig.strike(synth, SYNTH_CHORD, 1)
        rig.strike(organ, ORGAN_CHORD, 1)
        rig.strike(kit, PADS)
        rig.run(30)
        if bar:
            # Once the cap has had a bar to read, the chords fit.
            worst = max(worst, rig.output.cost())
        rig.lift(synth, SYNTH_CHORD)
        rig.lift(organ, ORGAN_CHORD)
        rig.lift(kit, PADS)
        rig.run(5)
    check(worst <= BLOCK_US, "the chords fit once the cap is shared (%d of %d us)" % (worst, BLOCK_US))
    check(s.voices + o.voices < 6 + 16, "the cap came down across the instruments (%d + %d)" % (s.voices, o.voices))
    check(s.dropped and o.dropped, "both instruments gave up voices (%d, %d)" % (s.dropped, o.dropped))
    check(k.voices == 16 and not k.dropped, "the kit keeps every sound (%d, %d dropped)" % (k.voices, k.dropped))

    # The keys come up and the synth plays alone: its whole chord fits again.
    rig.run(20)
    rig.strike(synth, SYNTH_CHORD, 3)
    rig.run(60)
    check(len(s.held) == len(SYNTH_CHORD), "the synth's chord alone sounds whole again (%d of 6)" % len(s.held))
    check(rig.output.cost() <= BUDGET_US, "and fits (%d of %d us)" % (rig.output.cost(), BUDGET_US))

    # One instrument on its own is capped as before.
    lone = Part(Instrument(16, 900), 16)
    rig = Rig([lone])
    rig.run(10)
    rig.strike(lone, range(60, 72), 1)
    rig.run(40)
    check(rig.output.cost() <= BLOCK_US, "one instrument alone fits (%d of %d us)" % (rig.output.cost(), BLOCK_US))
    check(lone.adapter.instrument.voices == 3, "and gets the voices that fit (%d)" % lone.adapter.instrument.voices)

    if failures:
        print("%d failed" % len(failures))
        sys.exit(1)
    print("RESULT OK")


main()
