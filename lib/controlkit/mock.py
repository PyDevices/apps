# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A stand-in adapter: an instrument with patches and macros, and no sound.

It keeps the same contract a real one does, so the panel can be built,
driven and tested anywhere. ``host_program`` and ``host_parameter`` play
the part of a host or a sequencer changing things from outside.

``ENVELOPES`` and ``ROUTINGS`` are shapes and graphs to show in an
`EnvelopeView` and a `RoutingDiagram`, and ``MockEnvelope`` plays the part
of an engine reporting where its envelope has got to.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Env Amt", "Drive",
    "Attack", "Decay", "Sustain", "Release",
    "LFO Rate", "LFO Depth", "Detune", "Sub Osc",
    "Chorus", "Delay", "Reverb", "Volume",
)

_NAMES = (
    "Init", "Fat Bass", "Acid Line", "Rubber Sub", "Glass Keys", "Warm Pad",
    "Brass Stab", "Sync Lead", "Pluck Box", "Choir Air", "Wobble", "Bell Tree",
    "Dark Drone", "Hoover", "Soft Saw", "Zap Perc", "Tape Strings", "Organ 7",
    "Ice Arp", "Saw Swarm", "Noise Hit", "Mono Grit", "Detroit", "Sine Sub",
    "Vox Formant", "Clav Funk", "Juno Pad", "Laser", "Duck Bass", "Hollow",
    "Ring Mod", "Dust Keys", "Space Lead", "Pulse 25", "Rave Stab", "Mellow",
    "Metal Bell", "Big Room", "Lo-Fi Pad", "Last Light",
)

#: Envelopes of four stages, as (name, rates, levels), each 0 to 127. The
#: third stage's level is the one that holds.
ENVELOPES = (
    ("Pluck", (127, 80, 50, 70), (127, 70, 0, 0)),
    ("Organ", (127, 127, 127, 110), (127, 127, 127, 0)),
    ("Pad", (40, 50, 40, 45), (100, 127, 105, 0)),
    ("Brass", (90, 60, 75, 80), (127, 100, 95, 0)),
    ("Swell", (25, 127, 127, 50), (127, 127, 127, 0)),
    ("Dip", (100, 90, 65, 75), (127, 25, 115, 0)),
)

#: Small modulation graphs, as (name, nodes, edges, carriers, feedback).
ROUTINGS = (
    ("Stack", ("A", "B", "C"), (("C", "B"), ("B", "A")), ("A",), ("C", "C")),
    ("Pairs", ("A", "B", "C", "D"), (("B", "A"), ("D", "C")), ("A", "C"), ("D", "D")),
    ("Fan", ("A", "B", "C", "D"), (("D", "A"), ("D", "B"), ("D", "C")), ("A", "B", "C"), None),
    ("Loop", ("A", "B", "C", "D"), (("C", "B"), ("B", "A")), ("A", "D"), ("A", "C")),
    ("Organ", ("A", "B", "C", "D"), (), ("A", "B", "C", "D"), None),
)


class MockEnvelope:
    """An engine's envelope, as far as a playhead goes: where it is as time passes.

    Each of *stages* takes *stage_ms*, and the level of stage *sustain*
    holds for *hold_ms* before the rest run. Then it starts again.
    """

    def __init__(self, stages=4, sustain=None, stage_ms=600, hold_ms=900):
        self.stages = stages
        self.sustain = sustain
        self.stage_ms = stage_ms
        self.hold_ms = hold_ms if sustain is not None else 0
        self.elapsed = 0

    def tick(self, ms):
        """Let *ms* pass; returns ``(stage, fraction)`` for ``EnvelopeView.set_position()``."""
        self.elapsed = (self.elapsed + ms) % (self.stages * self.stage_ms + self.hold_ms)
        left = self.elapsed
        for stage in range(self.stages):
            if left < self.stage_ms:
                return stage, left / self.stage_ms
            left -= self.stage_ms
            if stage == self.sustain:
                if left < self.hold_ms:
                    return stage, 1.0 + left / self.hold_ms
                left -= self.hold_ms
        return self.stages - 1, 1.0


def _patch_values(index):
    """Sixteen repeatable values for patch *index*, spread over the range."""
    values = []
    seed = 2654435761 * (index + 7) & 0xFFFFFFFF
    for _ in range(16):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        values.append((seed >> 8) % 128)
    return values


class MockAdapter:
    """An adapter with *patch_count* patches and *macro_count* labelled macros.

    *echo* says whether a patch change reports each macro it moved, the way
    an engine does; with False it only reports the patch, the way a simpler
    adapter might, and the panel must still follow.
    """

    def __init__(self, name="Demo Synth", patch_count=40, macro_count=16, echo=True):
        self.script_name = name
        self.macro_labels = list(MACRO_LABELS[:macro_count])
        self.macro_count = macro_count
        self.patches = [_NAMES[i] if i < len(_NAMES) else "Patch %03d" % (i + 1) for i in range(patch_count)]
        self.patch_index = 0
        self.macro_values = _patch_values(0)
        self.bypass = False
        self.engine_ready = True
        self.engine_error = 0
        self.echo = echo
        self.edits = []
        self.reloads = 0
        self._listeners = []

    def on_external_change(self, callback):
        self._listeners.append(callback)

    def _notify(self, kind, index, value):
        for listener in self._listeners:
            listener(kind, index, value)

    def _load(self, index):
        for macro, value in enumerate(_patch_values(index)):
            if self.macro_values[macro] == value:
                continue
            self.macro_values[macro] = value
            if self.echo:
                self._notify("macro", macro, value)

    # ---- the panel's calls ----

    def set_macro(self, index, value):
        self.macro_values[index] = value
        self.edits.append(("macro", index, value))

    def set_patch(self, index):
        self.patch_index = index
        self.edits.append(("patch", index, index))
        self._load(index)

    def set_bypass(self, enabled):
        self.bypass = bool(enabled)
        self.edits.append(("bypass", 0, self.bypass))

    def request_reload(self):
        self.reloads += 1

    def tick(self):
        pass

    def close_all(self):
        pass

    # ---- the outside world ----

    def host_program(self, index):
        """A host or sequencer picks patch *index*: patch first, then macros."""
        if index == self.patch_index:
            return
        self.patch_index = index
        self._notify("patch", index, index)
        self._load(index)

    def host_parameter(self, index, value):
        """A host's automation moves macro *index* to *value*."""
        if self.macro_values[index] == value:
            return
        self.macro_values[index] = value
        self._notify("macro", index, value)
