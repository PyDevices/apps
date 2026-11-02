# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Pads that play a drum kit, and pads that play notes when there's no keyboard.

A kit's General MIDI notes leave gaps and repeats under a keyboard's pads, so
:data:`KIT_PADS` lays each kit out as one pad per sound. :func:`pad_notes` is
what a pad note plays on an instrument.

:class:`NotePads` stands between the panel and the instrument's adapter.
Bank A's sixteen pads become notes: a drum machine's voices, or two octaves
of a C major scale. The instrument's patches move up to bank B onwards, so
they're still a press away.
"""

PADS = 16
#: Two octaves of C major from C3, for anything that isn't a drum machine.
SCALE = (48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72, 74)
NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
#: The note a keyboard's first pad sends, and how many pads it has: three banks
#: of eight on a Donner DMK-25 PRO.
FIRST_PAD = 36
PAD_COUNT = 24
#: Each drum machine's sounds in pad order, so a sound stays under the same
#: finger from kit to kit: kick, snare, closed hat, open hat, clap, rim, toms
#: from low to high, cymbals, then percussion. A kit moves up over what it
#: doesn't have. Its other notes repeat these sounds exactly.
KIT_PADS = {
    "rhythm808": (
        (36, "Bass Drum"), (38, "Snare Drum"), (42, "Closed Hi-Hat"), (46, "Open Hi-Hat"),
        (39, "Hand Clap"), (37, "Rim Shot"), (41, "Low Tom"), (45, "Mid Tom"),
        (48, "High Tom"), (49, "Cymbal"), (56, "Cowbell"), (62, "High Conga"),
        (63, "Mid Conga"), (64, "Low Conga"), (70, "Maracas"), (75, "Claves"),
    ),
    "rhythm909": (
        (36, "Bass Drum"), (38, "Snare Drum"), (42, "Closed Hi-Hat"), (46, "Open Hi-Hat"),
        (39, "Hand Clap"), (37, "Rim Shot"), (41, "Low Tom"), (45, "Mid Tom"),
        (48, "High Tom"), (49, "Crash Cymbal"), (51, "Ride Cymbal"),
    ),
    "rhythm606": (
        (36, "Bass Drum"), (38, "Snare Drum"), (42, "Closed Hi-Hat"), (46, "Open Hi-Hat"),
        (41, "Low Tom"), (48, "High Tom"), (49, "Cymbal"),
    ),
    "rhythm78": (
        (36, "Bass Drum"), (38, "Snare Drum"), (42, "Hi-Hat"), (46, "Open Hi-Hat"),
        (37, "Rim Shot"), (49, "Cymbal"), (54, "Tambourine"), (56, "Cowbell"),
        (60, "High Bongo"), (61, "Low Bongo"), (62, "Low Conga"), (70, "Maracas"),
        (73, "Guiro Short"), (74, "Guiro Long"), (75, "Claves"),
    ),
    "electronic_drums5": (
        (36, "Bass Drum"), (38, "Snare Drum"), (41, "Tom 3"), (45, "Tom 2"), (48, "Tom 1"),
    ),
}
#: A SoundFont's kits differ, so its pads are the first of these General MIDI
#: keys that the kit playing has a sound for, in the same order.
SOUNDFONT_KIT = "soundfont_drums"
SOUNDFONT_ORDER = (
    36, 38, 42, 46, 39, 37, 41, 43, 45, 47, 48, 50, 49, 51, 57, 59,
    35, 40, 44, 52, 53, 55, 54, 56, 58, 60, 61, 62, 63, 64, 65, 66,
    67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81,
)


def note_name(note):
    return "%s%d" % (NAMES[note % 12], note // 12 - 1)


def pad_notes(name, instrument):
    """The note each pad plays on instrument *name*, or None if it isn't laid out."""
    kit = KIT_PADS.get(name)
    if kit is not None:
        return tuple(note for note, _ in kit)
    if name != SOUNDFONT_KIT:
        return None
    bank, program = instrument.preset
    font = instrument.bank
    return tuple(key for key in SOUNDFONT_ORDER if font.regions(bank, program, key, 100))[:PAD_COUNT]


def notes_for(face):
    """``((note, label), ...)`` for bank A: a kit's sounds, or the scale."""
    kit = KIT_PADS.get(getattr(face, "NAME", None))
    if kit is not None:
        return kit
    note_map = getattr(face, "NOTE_MAP", None)
    if note_map:
        return tuple((note, label) for note, label in tuple(note_map)[:PADS])
    return tuple((note, note_name(note)) for note in SCALE)


class NotePads:
    """The panel's adapter, with bank A playing *notes*.

    *adapter* is the instrument's own adapter. *play(note)* sounds a note
    for a pad press; everything else passes straight through, with patch
    numbers moved up a bank each way.
    """

    def __init__(self, adapter, notes, play):
        self.adapter = adapter
        self.notes = notes
        self._play = play
        self._listeners = []
        labels = [label for _, label in notes]
        self._labels = labels + ["-"] * (PADS - len(labels))
        adapter.on_external_change(self._relay)

    # ---- what the panel reads ------------------------------------------------

    @property
    def script_name(self):
        return self.adapter.script_name

    @property
    def macro_labels(self):
        return self.adapter.macro_labels

    @property
    def macro_count(self):
        return self.adapter.macro_count

    @property
    def macro_values(self):
        return self.adapter.macro_values

    @property
    def patches(self):
        return self._labels + list(self.adapter.patches)[: 128 - PADS]

    @property
    def patch_index(self):
        return self.adapter.patch_index + PADS

    @property
    def bypass(self):
        return self.adapter.bypass

    @bypass.setter
    def bypass(self, value):
        self.adapter.bypass = value

    @property
    def engine_ready(self):
        return self.adapter.engine_ready

    @property
    def engine_error(self):
        return self.adapter.engine_error

    # ---- what the panel calls ------------------------------------------------

    def set_macro(self, index, value):
        self.adapter.set_macro(index, value)

    def set_patch(self, index):
        if index < PADS:
            if index < len(self.notes):
                self._play(self.notes[index][0])
            return
        self.adapter.set_patch(index - PADS)

    def set_bypass(self, enabled):
        self.adapter.set_bypass(enabled)

    def request_reload(self):
        self.adapter.request_reload()

    def on_external_change(self, callback):
        self._listeners.append(callback)

    def _relay(self, kind, index, value):
        if kind == "patch":
            index += PADS
            value += PADS
        for listener in self._listeners:
            listener(kind, index, value)
