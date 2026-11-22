# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the desk shows of a song, with no screen: its form and a part's steps.

`blocks` lays a song's parts out in the order a song goes through them,
for the song-form strip. The step functions read a part's notes as a grid
of drums by steps, and turn a tap on a cell into the songmodel op that
makes it so. Tapping a cell walks it through four levels: off, on, loud,
soft, and off again.

Imports on CPython and MicroPython with nothing but songmodel, so a check
can run it with numbers alone.
"""

from songmodel import model

from .engine import label, meter

BAR = model.BAR
TRACK = "/tracks/0"
#: The velocity each level of a cell plays at: off, on, loud and soft.
LEVELS = (0, 96, 124, 56)
#: The drums every grid shows when the kit has them, used or not.
CORE = (36, 38, 42, 46, 49)
SHORT = {"intro": "INTRO", "main": "MAIN", "fill": "FILL", "transition": "TRANS", "outro": "OUTRO"}


def blocks(doc):
    """The song's parts in the order it plays them: intro, then each main
    with its fill (the transition before the main it leads into), then the
    outro. Each is ``{"role", "number", "pattern", "bars", "label", "short"}``."""
    parts = doc.get("parts") or {}
    patterns = doc["tracks"][0]["patterns"]
    out = []

    def add(role, number, pattern):
        if pattern is None or not 0 <= pattern < len(patterns):
            return
        short = SHORT[role] + ("" if number is None or role == "transition" else " %d" % (number + 1))
        out.append({"role": role, "number": number, "pattern": pattern,
                    "bars": max(1, patterns[pattern].get("bars", 1)),
                    "label": label((role, number)), "short": short})

    mains = list(parts.get("mains") or [0])
    fills = list(parts.get("fills") or [])
    trans = parts.get("transitions", parts.get("transition"))
    trans = list(trans) if isinstance(trans, list) else ([] if trans is None else [trans])
    each = len(trans) == len(mains)
    add("intro", None, parts.get("intro"))
    for n, main in enumerate(mains):
        if n and trans:
            add("transition", n, trans[n] if each else trans[0])
        add("main", n, main)
        if n < len(fills):
            add("fill", n, fills[n])
    if each and len(mains) > 1:
        add("transition", 0, trans[0])
    add("outro", None, parts.get("outro"))
    return out


def find(blocks_, role, number):
    """The index of the block for ``role`` and ``number``, or -1."""
    for i, b in enumerate(blocks_):
        if b["role"] == role and (b["number"] == number or role in ("intro", "outro")):
            return i
    return -1


def columns(doc):
    """``(columns, ticks)``: a bar's steps on the grid and the ticks in one.
    Sixteenths for a song whose beat is one segment (4/4), else one column
    a segment (12/8's eighths)."""
    steps, group = meter(doc)
    cols = steps * (4 if group == 1 else 1)
    return cols, BAR // cols


def beat_columns(doc):
    """How many grid columns make a beat."""
    steps, group = meter(doc)
    return 4 if group == 1 else group


def rows(voices, doc):
    """``[(pitch, name)]``, highest first: the kit's drums that the song
    plays or that every grid shows, and any drum the song plays that the kit
    names nothing for."""
    names = dict((int(p), n) for p, n in voices)
    used = set()
    for pat in doc["tracks"][0]["patterns"]:
        for n in pat["notes"]:
            used.add(n[2])
    want = set(p for p in CORE if p in names) | used
    out = []
    for p in sorted(want, reverse=True):
        out.append((p, names.get(p) or "Note %d" % p))
    return out


def level(velocity):
    """Which of `LEVELS` a velocity shows as: 1 on, 2 loud, 3 soft."""
    if velocity <= 0:
        return 0
    if velocity < 80:
        return 3
    if velocity < 112:
        return 1
    return 2


def cell(notes, pitch, step, ticks):
    """The index in ``notes`` of the note in a cell, or -1."""
    lo = step * ticks
    hi = lo + ticks
    for i, n in enumerate(notes):
        if n[2] == pitch and lo <= n[0] < hi:
            return i
    return -1


def levels(pattern, pitches, ticks):
    """``{(pitch, step): level}`` for every note on the grid of ``pattern``."""
    out = {}
    want = set(pitches)
    for n in pattern["notes"]:
        if n[2] in want:
            key = (n[2], int(n[0] // ticks))
            out[key] = max(out.get(key, 0), level(n[3]))
    return out


def tap(doc, index, pitch, step, ticks):
    """The op a tap on cell ``(pitch, step)`` of pattern ``index`` sends:
    ``(op, path, value)``. Off becomes on, on loud, loud soft, soft off."""
    pat = doc["tracks"][0]["patterns"][index]
    base = "%s/patterns/%d/notes" % (TRACK, index)
    i = cell(pat["notes"], pitch, step, ticks)
    if i < 0:
        return "add", base + "/-", [step * ticks, ticks, pitch, LEVELS[1]]
    now = level(pat["notes"][i][3])
    if now == 3:
        return "remove", "%s/%d" % (base, i), None
    return "replace", "%s/%d/3" % (base, i), LEVELS[2 if now == 1 else 3]
