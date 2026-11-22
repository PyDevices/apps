# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's box: the song, the engine, the kit, and the hmilink device
every view draws from.

`BacklineModel` is songmodel's `SongModel` with Backline's facts added to
what it describes (the song's parts, the songs and kits there are). `Box`
is its host: it answers the commands any panel sends and the telemetry
every panel reads.

Commands, from any panel:

- ``pedal {"pedal": 0 or 1, "down": true or false}``: a footswitch moved.
- ``gesture {"pedal": 0 or 1, "gesture": "tap", "hold" or "double"}``: a
  gesture made elsewhere, as a panel with its own timing would send it.
- ``song {"index": n}`` or ``song {"step": 1 or -1}``: another starter song,
  while stopped.
- ``kit {"spec": "rhythm909"}`` or ``kit {"step": 1 or -1}``: another kit,
  at once, even while playing.
- ``stop {}``: stop now.

Telemetry is `engine.Engine.telemetry`: bar, beat, part, next part,
pedals, tempo and kit.

No LVGL and no audio output here: the app gives the box its clock and plays
the box's ``bus``, so a check can run a box and pull the sound itself.
"""

import json
import os

import hmilink
from songmodel.link import SongModel

from . import engine as eng
from . import kits

here = __file__.replace("\\", "/")
SONGS = here[: here.rfind("/")] + "/songs"


def song_files(folder=SONGS):
    """The starter songs, ``[(name, path)]``, in name order."""
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        return []
    return [(n[:-5], folder + "/" + n) for n in names]


def load_song(path):
    with open(path) as f:
        return json.load(f)


class BacklineModel(SongModel):
    """The song a Backline box holds, as an hmilink model."""

    def describe(self):
        out = SongModel.describe(self)
        out["kind"] = "backline"
        out["parts"] = self.doc.get("parts")
        box = self.host
        if box is not None:
            out["songs"] = [n for n, _p in box.songs]
            out["kits"] = list(box.kits)
        return out


class Box:
    """The engine, its kit and the device. ``clock()`` is the output's frame."""

    def __init__(self, clock, song=None, kit=None, rate=kits.RATE, songs=None, now_ms=None):
        self.rate = rate
        self.songs = song_files() if songs is None else songs
        self.kits = kits.available()
        self.song_index = 0
        if isinstance(song, str):
            for i, (n, _p) in enumerate(self.songs):
                if n == song:
                    self.song_index = i
        project = load_song(self.songs[self.song_index][1]) if song is None or isinstance(song, str) else song
        self.bus = kits.Bus(rate)
        kw = {} if now_ms is None else {"now_ms": now_ms}
        self.engine = eng.Engine(project, None, clock, rate, **kw)
        self.error = None
        self.model = BacklineModel(project, forward=self.forward, host=self)
        self.device = hmilink.Device(self.model, telemetry_hz=30)
        self.use_kit(kit or project["tracks"][0].get("instrument") or kits.MACHINES[0])

    # -- the sound --------------------------------------------------------------

    def use_kit(self, spec):
        """Play kit ``spec`` from now on. A kit that won't open leaves the one
        before playing and says why in ``error``."""
        try:
            kit = kits.open_kit(spec, self.rate)
        except Exception as e:  # noqa: BLE001 - said on the screen, the old kit plays on
            self.error = "kit %s: %s" % (spec, e)
            return False
        self.bus.attach(kit)
        self.engine.set_kit(kit)
        # A kit that can hold a note back gets it early, and plays it on its frame.
        self.engine.lookahead = 2 * kits.BLOCK if kit.timed else 0
        self.error = None
        return True

    def forward(self, op):
        """An op the song took from a panel: the engine follows it."""
        if op.get("op") == "replace":
            self.engine.load(self.model.doc)
            return
        if op.get("path") == ["tempo"]:
            self.engine.retempo()
        elif "patterns" in op.get("path", ()) or op.get("path", [None])[0] == "parts":
            self.engine.form.__init__(self.model.doc)
            self.engine.changes += 1

    def service(self):
        """One pass: the pedals' timing, the notes due, the kit's fill, the panels."""
        e = self.engine
        e.poll()
        e.sequence()
        self.bus.fill()

    def poll(self):
        self.device.poll()

    # -- what panels ask --------------------------------------------------------

    def telemetry(self):
        t = self.engine.telemetry()
        t["error"] = self.error or ""
        t["song_index"] = self.song_index
        t["songs"] = len(self.songs)
        return t

    def command(self, name, args):
        e = self.engine
        if name == "pedal":
            which = int(args.get("pedal", 0))
            if args.get("down"):
                e.press(which)
            else:
                e.release(which)
            return None
        if name == "gesture":
            did = e.gesture(int(args.get("pedal", 0)), args["gesture"])
            return {"name": "gesture", "did": did}
        if name == "stop":
            e.stop()
            return None
        if name == "song":
            if e.transport["playing"]:
                raise ValueError("stop the song first")
            n = len(self.songs)
            i = args["index"] if "index" in args else self.song_index + int(args.get("step", 1))
            self.song_index = i % n
            project = load_song(self.songs[self.song_index][1])
            self.model.load(project)
            self.use_kit(project["tracks"][0].get("instrument") or kits.MACHINES[0])
            return {"name": "song", "index": self.song_index}
        if name == "kit":
            spec = args.get("spec")
            if spec is None:
                cur = e.kit.spec if e.kit is not None else None
                i = self.kits.index(cur) if cur in self.kits else -1
                spec = self.kits[(i + int(args.get("step", 1))) % len(self.kits)]
            self.use_kit(spec)
            return {"name": "kit", "spec": spec, "error": self.error}
        raise ValueError("unknown command %r" % name)

    def close(self):
        self.device.close()
        self.bus.close()
