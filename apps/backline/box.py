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
  at once, even while playing. Every panel hears ``kit`` back, with the
  notes the new kit plays (``voices``).
- ``stop {}``: stop now.
- ``action {"name": "fill"}``: one of the actions a MIDI switch can be
  bound to (`midipedal.BINDINGS`): start, fill, next, outro, stop or
  tap_tempo.
- ``pedals {"learn": n}`` (-1 stops), ``pedals {"slot": n, "bind": "fill"}``
  or ``pedals {"slot": n, "clear": true}``: the MIDI switches' map. Every
  panel hears ``pedals`` back with the whole map, and again when a slot
  learns its switch.

Edits are songmodel ops on the document, and they reach the sound while it
plays: a step added or removed plays from its next pass, a new tempo keeps
the playhead where it is, ``/tracks/0/volume`` is the kit's level and
``/tracks/0/mix/<group>`` (0 to 100) turns one group of drums up or down
(`engine.GROUPS`).

Telemetry is `engine.Engine.telemetry`: bar, beat, part, next part,
pedals, tempo and kit.

No LVGL and no audio output here: the app gives the box its clock and plays
the box's ``bus``, so a check can run a box and pull the sound itself.
"""

import json
import os

import hmilink
from hmilink import local
from songmodel.link import SongModel

from . import engine as eng
from . import kits
from . import midipedal

LEVEL = 0.9          # the kit's level at track volume 100
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
            out["titles"] = box.titles()
            out["kits"] = list(box.kits)
            out["kit_list"] = kits.describe(box.kits)
            out["kit"] = box.kit_spec()
            out["voices"] = box.voices()
            out["groups"] = [[n, list(p)] for n, p in eng.GROUPS] + [[eng.OTHER, []]]
            out["pedals"] = box.midi.describe()
        return out


class Box:
    """The engine, its kit and the device. ``clock()`` is the output's frame."""

    def __init__(self, clock, song=None, kit=None, rate=kits.RATE, songs=None, now_ms=None, pedal_map=None):
        self.rate = rate
        self.songs = song_files() if songs is None else songs
        self.kits = kits.available()
        self.song_index = 0
        self._titles = None
        if isinstance(song, str):
            for i, (n, _p) in enumerate(self.songs):
                if n == song:
                    self.song_index = i
        project = load_song(self.songs[self.song_index][1]) if song is None or isinstance(song, str) else song
        self.bus = kits.Bus(rate)
        kw = {} if now_ms is None else {"now_ms": now_ms}
        self.engine = eng.Engine(project, None, clock, rate, **kw)
        self.error = None
        self.cast = ""            # where the desk view is cast, while it is
        #: The MIDI switches' map, and the input it reads (`midipedal.open_input`).
        self.midi = midipedal.MidiPedal(pedal_map, on_pedal=self.pedal, on_action=self.action,
                                        on_change=self._pedals_changed)
        self.midi_in = None
        self.taps = midipedal.TapTempo()
        self.model = BacklineModel(project, forward=self.forward, host=self)
        self.device = hmilink.Device(self.model, telemetry_hz=30)
        self.use_kit(kit or project["tracks"][0].get("instrument") or kits.MACHINES[0])
        self._level()

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

    def titles(self):
        """Each starter song's own name, read once."""
        if self._titles is None:
            found = []
            for name, path in self.songs:
                try:
                    found.append(load_song(path).get("name") or name)
                except (OSError, ValueError):
                    found.append(name)
            self._titles = found
        return self._titles

    def kit_spec(self):
        kit = self.engine.kit
        return kit.spec if kit is not None else None

    def voices(self):
        """``[[pitch, name]]``: the drums the kit playing now has, by General
        MIDI's short names where it has one, so a row reads the same on every kit."""
        kit = self.engine.kit
        if kit is None or not hasattr(kit, "voices"):
            return []
        short = dict(kits.GM_DRUMS)
        return [[int(p), short.get(int(p), n)] for p, n in kit.voices()]

    def _level(self):
        vol = self.engine.track.get("volume", 100)
        self.bus.level(LEVEL * vol / 100.0)

    def forward(self, op):
        """An op the song took from a panel: the engine follows it.

        A step's notes are read as they play, so a note edit needs nothing
        here. A pattern's length or the song's parts make a new plan that
        keeps what plays now and what is queued."""
        if op.get("op") == "replace":
            self.engine.load(self.model.doc)
            self._level()
            return
        path = op.get("path", ())
        if path == ["tempo"]:
            self.engine.retempo()
        elif path[:1] == ["parts"] or (len(path) >= 3 and path[2] == "patterns" and "notes" not in path):
            self.engine.reform()
        elif path == ["tracks", 0, "volume"]:
            self._level()

    def service(self):
        """One pass: the pedals' timing, the notes due, the kit's fill, the panels."""
        e = self.engine
        if self.midi_in is not None:
            try:
                self.midi.read_port(self.midi_in)
            except Exception as err:  # noqa: BLE001 - said on the screen, the song plays on
                self.error = "MIDI in stopped: %s" % (err,)
                self.midi_in = None
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
        t["cast"] = self.cast
        # Panels on another screen: a browser, another computer or board.
        t["desks"] = sum(1 for link in self.device.links if not isinstance(link, local.Link))
        return t

    def pedal(self, which, down):
        """Footswitch ``which`` (0 or 1) went down or up. Every source of a
        pedal comes in here: a panel's lamp or key, and a switch on a pin or
        a MIDI note or controller on a box that has one."""
        if down:
            self.engine.press(which)
        else:
            self.engine.release(which)

    def action(self, name, now=None):
        """Do one of a MIDI switch's actions (`midipedal.BINDINGS`); returns
        what the song did, as `engine.Engine.gesture` says it, or the new tempo.

        Each is a gesture of pedal A where the song is: start only starts a
        stopped song, and fill, next and outro only change one that plays."""
        e = self.engine
        playing = e.transport["playing"]
        if name == "start":
            return e.gesture(0, "tap") if not playing else None
        if name in ("fill", "next", "outro"):
            return e.gesture(0, {"fill": "tap", "next": "hold", "outro": "double"}[name]) if playing else None
        if name == "stop":
            e.stop()
            e.last = "stop"
            return "stop"
        if name == "tap_tempo":
            bpm = self.taps.tap(e.now_ms() if now is None else now)
            if bpm is not None:
                self.set("/tempo", bpm)
            return bpm
        if name == "none":
            return None
        raise ValueError("no action %r" % (name,))

    def set(self, path, value):
        """Change the song from the box itself, as a panel's op would, and
        tell every panel."""
        dev = self.device
        op = self.model.apply({"op": "replace", "path": path, "value": value})
        dev.seq += 1
        msg = {"t": "op", "seq": dev.seq, "op": op["op"], "path": op["path"], "value": op.get("value")}
        dev.broadcast(msg)

    def _pedals_changed(self):
        self.device.event("pedals", **self.midi.describe())

    def command(self, name, args):
        e = self.engine
        if name == "pedal":
            self.pedal(int(args.get("pedal", 0)), bool(args.get("down")))
            return None
        if name == "gesture":
            did = e.gesture(int(args.get("pedal", 0)), args["gesture"])
            return {"name": "gesture", "did": did}
        if name == "stop":
            e.stop()
            return None
        if name == "action":
            did = self.action(args["name"])
            return {"name": "action", "action": args["name"], "did": did}
        if name == "pedals":
            m = self.midi
            if "learn" in args:
                m.learn(int(args["learn"]))
            elif args.get("clear"):
                m.clear(int(args["slot"]))
            elif "bind" in args:
                m.bind(int(args["slot"]), args["bind"])
            return None               # the map changed: `_pedals_changed` told every panel
        if name == "song":
            if e.transport["playing"]:
                raise ValueError("stop the song first")
            n = len(self.songs)
            i = args["index"] if "index" in args else self.song_index + int(args.get("step", 1))
            self.song_index = i % n
            project = load_song(self.songs[self.song_index][1])
            self.model.load(project)
            self.use_kit(project["tracks"][0].get("instrument") or kits.MACHINES[0])
            return {"name": "song", "index": self.song_index, "kit": self.kit_spec(), "voices": self.voices()}
        if name == "kit":
            spec = args.get("spec")
            if spec is None:
                cur = e.kit.spec if e.kit is not None else None
                i = self.kits.index(cur) if cur in self.kits else -1
                spec = self.kits[(i + int(args.get("step", 1))) % len(self.kits)]
            self.use_kit(spec)
            return {"name": "kit", "spec": self.kit_spec(), "error": self.error, "voices": self.voices()}
        raise ValueError("unknown command %r" % name)

    def close(self):
        port = self.midi_in
        self.midi_in = None
        if port is not None and hasattr(port, "close"):
            port.close()
        self.device.close()
        self.bus.close()
