# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Vamp's front panel without its screen: join a box, edit its song and follow
what it plays.

`Front` is an hmilink panel that knows the song. It keeps what a small touch
screen needs (the selected track, the bar and octave on show, where the
playhead is) and turns a press into the op or command the box takes::

    from vamp.panel import Front, join

    front = Front(lambda: join("192.168.1.50", 9100))
    while True:
        front.poll()                 # the link, and a new try when it's gone
        if front.take("grid"):
            ...                      # draw front.cells() again

Nothing here draws: `vamp.panel_view` is the 800x480 screen on LVGL. Runs on
MicroPython and CPython.
"""

import socket

import hmilink
from hmilink import tcp

from songmodel import model as song

#: The kit's rows, top to bottom: General MIDI pitch and name.
DRUMS = ((49, "Crash"), (46, "Open"), (42, "Hat"), (39, "Clap"), (38, "Snare"), (36, "Kick"))
NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
BLACK = (1, 3, 6, 8, 10)

STEPS = 16          # sixteenths on show: one bar
OCTAVE = 12         # a melodic track's rows on show
RETRY_MS = 4000     # between tries for a box that isn't there
JOIN_S = 3          # how long one try waits for the box to answer
VOLUME_MS = 80      # a dragged volume is sent this often at most
PRESS_MS = 500      # after Play or Stop, the box's older reports don't undo the button

EMPTY, START, HELD = 0, 1, 2


def note_name(pitch):
    """A MIDI pitch as ``C3`` (60 is C4)."""
    return "%s%d" % (NAMES[pitch % 12], pitch // 12 - 1)


def join(host, port=9100, seconds=JOIN_S):
    """A link to the box at ``host``. Unlike ``hmilink.tcp.connect`` it gives
    up after ``seconds``, so a screen waiting for a box doesn't freeze.

    Raises:
        OSError: the box didn't answer.
    """
    s = socket.socket()
    s.settimeout(seconds)
    try:
        s.connect(socket.getaddrinfo(host, port)[0][-1])
    except OSError:
        s.close()
        raise
    link = tcp.Link(s)
    link.ws = False               # a panel's own link speaks lines from the start
    return link


def playing_at(doc, track, tick):
    """What ``track`` plays at ``tick``: its pattern's index and the tick within
    it, or (-1, 0) when the song has it silent there."""
    if doc.get("song_mode") and doc.get("song"):
        _a, _b, start, patterns = song.segments(doc, tick, tick + 1)[0]
        index = patterns.get(track["id"], -1)
    else:
        index, start = song.pattern_at(track, tick)
    if not 0 <= index < len(track["patterns"]):
        return -1, 0
    return index, (tick - start) % (track["patterns"][index]["bars"] * song.BAR)


class Front:
    """The song a box holds, as a front panel sees and changes it.

    Args:
        connect: a call that returns a new hmilink link to the box, and raises
            OSError when the box isn't there. It's called again, every
            ``RETRY_MS``, after the link is lost.

    Attributes:
        selected: the index of the track on show.
        bar: the bar of its pattern on show, from 0.
        low: the lowest pitch on show for a melodic track.
        follow: True while the bar on show follows the playhead.
        armed: True when the next Play starts a take on the selected track.
        playing: True while the box plays.
        head: the step the playhead is on in the pattern on show, or None.
        status: one line about the link, for the screen.
    """

    def __init__(self, connect):
        self.connect = connect
        self.panel = None
        self.selected = 0
        self.bar = 0
        self.low = 48
        self.follow = True
        self.armed = False
        self.playing = False
        self.tick = None
        self.head = None
        self.status = "Looking for the box"
        self.errors = 0
        self._dirty = {"all"}
        self._retry_at = None
        self._volume_at = hmilink.ticks_ms()
        self._pressed_at = None

    # -- the link --

    @property
    def doc(self):
        """The song, or None until the box has sent it."""
        return self.panel.doc if self.panel is not None else None

    def poll(self):
        """Pass messages both ways; try for the box again when it has gone."""
        panel = self.panel
        if panel is not None and panel.closed:
            self.panel = panel = None
            self.playing = False
            self.tick = self.head = None
            self._say("The box went away")
            self.mark("all")
            self._retry_at = hmilink.ticks_ms()
        if panel is None:
            now = hmilink.ticks_ms()
            if self._retry_at is not None and hmilink.ticks_diff(now, self._retry_at) < RETRY_MS:
                return
            self._retry_at = now
            try:
                link = self.connect()
            except OSError:
                self._say("Looking for the box")
                return
            panel = self.panel = hmilink.Panel(link)
            panel.on_doc = self._on_doc
            panel.on_op = self._on_op
            panel.on_tele = self._on_tele
            panel.on_event = self._on_event
            panel.on_error = self._on_error
            self._say("Joining")
        try:
            panel.poll()
        except OSError:
            panel.close()

    def close(self):
        if self.panel is not None:
            self.panel.close()

    def mark(self, what):
        """Note that part of the screen is out of date: ``all``, ``top``,
        ``tracks``, ``grid``, ``head`` or ``status``."""
        self._dirty.add(what)

    def take(self, what):
        """True, once, when ``what`` is out of date."""
        if what in self._dirty:
            self._dirty.discard(what)
            return True
        return False

    def _say(self, text):
        if text != self.status:
            self.status = text
            self.mark("status")

    def _on_doc(self, doc, desc):
        if self.selected >= len(doc["tracks"]):
            self.selected = 0
        self._clamp()
        self._say("Joined")
        self.mark("all")
        self._tell_selected()

    def _on_op(self, op):
        path = op["path"]
        keys = hmilink.split_pointer(path)
        if len(keys) == 1:
            self.mark("top")
            if keys[0] in ("song_mode", "song", "loop_scene"):
                self._place_head()
        elif keys[0] == "tracks" and len(keys) == 3 and keys[2] in ("mute", "solo", "volume", "name", "patch"):
            self.mark("tracks")
        elif keys[0] == "tracks" and len(keys) > 2:
            if keys[1] == str(self.selected):
                self._clamp()
                self.mark("grid")
                self._place_head()
        else:
            # A track added or removed, or something this panel doesn't draw.
            if self.selected >= len(self.doc["tracks"]):
                self.selected = 0
            self._clamp()
            self.mark("all")

    def _on_tele(self, values):
        playing = bool(values.get("playing"))
        if playing != self.playing:
            # A report sent before the box heard this panel's Play or Stop.
            if self._pressed_at is not None and hmilink.ticks_diff(hmilink.ticks_ms(), self._pressed_at) < PRESS_MS:
                return
            self._set_playing(playing)
        self._pressed_at = None
        self.tick = values.get("tick") if playing else None
        self._place_head()

    def _on_event(self, msg):
        if msg.get("name") == "transport":
            self._pressed_at = None
            self._set_playing(bool(msg.get("playing")))

    def _set_playing(self, playing):
        if playing != self.playing:
            self.playing = playing
            self.mark("top")
        if not playing:
            self.tick = None
            self._place_head()

    def _on_error(self, msg):
        self.errors += 1
        if msg.get("t") == "err":
            self._say("The box said no: %s" % (msg.get("msg"),))
            self.mark("all")

    # -- what is on show --

    def track(self):
        """The selected track, or None."""
        doc = self.doc
        if doc is None or not doc["tracks"]:
            return None
        return doc["tracks"][self.selected]

    def pattern(self):
        """The index and the pattern on show for the selected track."""
        track = self.track()
        index = song.shown_pattern(track)
        return index, track["patterns"][index]

    def rows(self):
        """The grid's rows, top to bottom: ``(pitch, label, is a black key)``."""
        track = self.track()
        if track is None:
            return []
        if track["kind"] == "drums":
            return [(pitch, name, False) for pitch, name in DRUMS]
        return [(p, note_name(p), p % 12 in BLACK) for p in range(self.low + OCTAVE - 1, self.low - 1, -1)]

    def cells(self):
        """The bar on show as ``len(rows()) * STEPS`` bytes, row by row: START
        where a note begins, HELD while it lasts, EMPTY elsewhere."""
        rows = self.rows()
        out = bytearray(len(rows) * STEPS)
        if not rows:
            return out
        where = {}
        for i, row in enumerate(rows):
            where[row[0]] = i
        first = self.bar * STEPS
        for start, length, pitch, _velocity in self.pattern()[1]["notes"]:
            row = where.get(pitch)
            if row is None:
                continue
            step = start // song.STEP
            last = step + max(1, (length + song.STEP - 1) // song.STEP)
            for s in range(max(step, first), min(last, first + STEPS)):
                at = row * STEPS + s - first
                if s == step:
                    out[at] = START
                elif out[at] == EMPTY:
                    out[at] = HELD
        return out

    def bars(self):
        track = self.track()
        return self.pattern()[1]["bars"] if track is not None else 1

    def _clamp(self):
        if self.track() is None:
            self.bar = 0
            return
        self.bar = max(0, min(self.bar, self.bars() - 1))

    def _place_head(self):
        """The playhead's step in the pattern on show, from the box's tick."""
        head = None
        track = self.track()
        if self.tick is not None and track is not None:
            index, tick = playing_at(self.doc, track, self.tick)
            if index == song.shown_pattern(track):
                head = int(tick // song.STEP)
        if head != self.head:
            self.head = head
            self.mark("head")
            if head is not None and self.follow and head // STEPS != self.bar:
                self.bar = head // STEPS
                self.mark("grid")

    # -- what a press does --

    def _send(self, kind, path, value=None):
        if self.panel is None or self.doc is None:
            return False
        try:
            self.panel.send(kind, path, value)
        except OSError:
            self.panel.close()
            return False
        return True

    def _command(self, name, **args):
        if self.panel is None or self.doc is None:
            return False
        try:
            self.panel.command(name, by=self.panel.me, **args)
        except OSError:
            self.panel.close()
            return False
        return True

    def _tell_selected(self):
        """The box's keyboard plays the selected track, and a take goes to it."""
        track = self.track()
        if track is not None:
            self._command("engines", msg={"t": "select", "track": track["id"],
                                          "armed": track["id"] if self.armed else None})

    def play(self):
        """Start the song from its top; with `armed` set, a take with it."""
        if self.armed:
            self._tell_selected()
            sent = self._command("engines", msg={"t": "transport", "play": True, "tick": 0.0, "record": True})
        else:
            sent = self._command("play", tick=0.0)
        if sent:
            self._pressed_at = hmilink.ticks_ms()
            self._set_playing(True)

    def stop(self):
        if self._command("stop"):
            self._pressed_at = hmilink.ticks_ms()
            self._set_playing(False)

    def toggle_play(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def toggle_armed(self):
        """Arm the selected track for a take, or disarm it. While the box
        plays, the take starts or ends at once."""
        self.armed = not self.armed
        self._tell_selected()
        if self.playing:
            self._command("engines", msg={"t": "record", "on": self.armed})
        self.mark("top")

    def tempo(self, delta):
        doc = self.doc
        if doc is not None:
            value = max(40.0, min(240.0, float(round(doc["tempo"]) + delta)))
            if self._send("replace", "/tempo", value):
                self.mark("top")

    def swing(self, delta):
        doc = self.doc
        if doc is not None:
            value = max(0, min(100, int(doc.get("swing", 0)) + delta))
            if self._send("replace", "/swing", value):
                self.mark("top")

    def select(self, index):
        doc = self.doc
        if doc is None or not 0 <= index < len(doc["tracks"]) or index == self.selected:
            return
        self.selected = index
        self._clamp()
        self._tell_selected()
        self.mark("tracks")
        self.mark("grid")
        self._place_head()

    def mute(self, index):
        self._flip(index, "mute")

    def solo(self, index):
        self._flip(index, "solo")

    def _flip(self, index, key):
        doc = self.doc
        if doc is not None and 0 <= index < len(doc["tracks"]):
            if self._send("replace", "/tracks/%d/%s" % (index, key), not doc["tracks"][index].get(key)):
                self.mark("tracks")

    def volume(self, index, value, last=True):
        """Set a track's volume, 0 to 127. A drag passes ``last=False`` until
        the finger lifts, and only some of those are sent."""
        doc = self.doc
        if doc is None or not 0 <= index < len(doc["tracks"]):
            return
        now = hmilink.ticks_ms()
        if not last and hmilink.ticks_diff(now, self._volume_at) < VOLUME_MS:
            return
        self._volume_at = now
        value = max(0, min(127, int(value)))
        if value != doc["tracks"][index]["volume"]:
            self._send("replace", "/tracks/%d/volume" % index, value)

    def toggle(self, row, step):
        """A press on the grid: put a sixteenth there, or take away the note
        that starts there."""
        rows = self.rows()
        if not (0 <= row < len(rows) and 0 <= step < STEPS):
            return
        pitch = rows[row][0]
        index, pattern = self.pattern()
        at = self.bar * STEPS + step
        base = "/tracks/%d/patterns/%d/notes/" % (self.selected, index)
        notes = pattern["notes"]
        for i in range(len(notes)):
            if notes[i][2] == pitch and notes[i][0] // song.STEP == at:
                if self._send("remove", base + str(i)):
                    self.mark("grid")
                return
        if self._send("add", base + "-", [at * song.STEP, song.STEP, pitch, 100]):
            self.mark("grid")
            if not self.playing:
                self._command("engines", msg={"t": "audition", "track": self.track()["id"], "pitch": pitch,
                                              "velocity": 100, "seconds": 0.25})

    def page(self, delta):
        """Show the next or the last bar, and stop following the playhead."""
        bar = max(0, min(self.bar + delta, self.bars() - 1))
        self.follow = False
        if bar != self.bar:
            self.bar = bar
            self.mark("grid")
        self.mark("head")

    def toggle_follow(self):
        """Follow the playhead from bar to bar, or stay on this one."""
        self.follow = not self.follow
        if self.follow and self.head is not None and self.head // STEPS != self.bar:
            self.bar = self.head // STEPS
        self.mark("grid")

    def octave(self, delta):
        """Show the octave above or below, for a melodic track."""
        low = max(0, min(self.low + delta * OCTAVE, 108))
        if low != self.low:
            self.low = low
            self.mark("grid")
