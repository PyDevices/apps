# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Turn a keyboard's notes into notes in the song, for Vamp's take.

`Take` watches note-ons and note-offs from the track that is armed while the
song plays, and says where each finished note goes. `place` works out which
pattern a note played at some tick belongs to, and returns the song-model op
that adds it, so a box with no screen attached can record, and every screen
that is attached sees the note arrive.

Runs on MicroPython and CPython.
"""

from songmodel import model


class Take:
    """The notes held down since the take began.

    Attributes:
        armed (int): Id of the track that records, or ``None``.
        recording (bool): Whether a take is running.
    """

    def __init__(self, tick_at):
        self.tick_at = tick_at        # a frame's tick in the song
        self.armed = None
        self.recording = False
        self.open = {}                # pitch -> (tick, velocity)

    def start(self):
        self.recording = True
        self.open = {}

    def stop(self):
        self.recording = False
        self.open = {}

    def on(self, track, pitch, velocity, frame):
        """A key went down on ``track`` at ``frame``."""
        if self.recording and track == self.armed:
            self.open[pitch] = (self.tick_at(frame), velocity)

    def off(self, track, pitch, frame):
        """A key came up. Returns ``(start, end, pitch, velocity)`` in ticks for a
        note this take saw go down, else ``None``."""
        if track != self.armed or pitch not in self.open:
            return None
        start, velocity = self.open.pop(pitch)
        return start, self.tick_at(frame), pitch, velocity


def place(project, track_id, start, end, pitch, velocity):
    """The op that adds a played note to the song, or ``None`` if it has no place.

    A note played in the count-in (more than half a step before the song's
    start) has none, nor has one on a track that is silent in the scene it was
    played in. Notes snap to sixteenths when the song's ``quantise`` is on.
    """
    if start < -model.STEP / 2:
        return None
    track = model.find_track(project, track_id)
    if track is None:
        return None
    tick = max(0.0, start)
    found = model.segments(project, tick, tick + 1)
    if not found:
        return None
    _, _, base, patterns = found[0]
    index = patterns[track_id]
    if isinstance(index, tuple):
        index, base = index
    if index < 0 or index >= len(track["patterns"]):
        return None
    length = track["patterns"][index]["bars"] * model.BAR
    offset = start - base
    if project.get("quantise", True):
        at = int(round(offset / model.STEP)) * model.STEP % length
        size = max(model.STEP, int(round((end - start) / model.STEP)) * model.STEP)
    else:
        at = int(round(max(0.0, offset))) % length
        size = max(model.STEP // 4, int(round(end - start)))
    return {"op": "insert",
            "path": model.track_path(track_id, "patterns", index, "notes", -1),
            "value": [at, min(size, length), pitch, velocity]}
