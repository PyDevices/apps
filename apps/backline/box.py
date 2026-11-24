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
- ``ask {"text": "a slow 12-bar blues at 72"}``: ask the chat server for a
  song (`ask`). Telemetry's ``ask`` says ``"asking"``, then ``"ready"`` or
  ``"failed"`` (with ``ask_error``), and every panel hears ``proposal``
  with the song's `ask.preview`, also in the description for a panel that
  joins later.
- ``proposal {"do": "play"}``, ``{"do": "keep"}`` or ``{"do": "discard"}``:
  play the song that came back (the song playing stops first), keep it
  among the songs (saved in the box's own songs folder), or let it go and
  have back the song from before.

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

import gc
import json
import os

import hmilink
from hmilink import local
from songmodel.link import SongModel

from . import ask as askmod
from . import engine as eng
from . import kits
from . import midipedal

LEVEL = 0.9          # the kit's level at track volume 100
_NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"
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
            out["proposal"] = box.proposal_preview
            out["can_ask"] = box.ask_settings is not None
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

    def __init__(self, clock, song=None, kit=None, rate=kits.RATE, songs=None, now_ms=None, pedal_map=None,
                 worker=None, ask_settings=None, user_songs=None, post=None):
        self.rate = rate
        self.songs = song_files() if songs is None else songs
        #: Where kept songs are saved, and listed after the starters.
        self.user_songs = user_songs
        if user_songs:
            self.songs = self.songs + song_files(user_songs)
        self.kits = kits.available()
        #: What runs a blocking call off the main thread (``scope.worker``); None runs it here.
        self.worker = worker
        self.ask_settings = ask_settings
        self._post = post
        self.asker = None
        self.ask_state = ""
        self.ask_error = ""
        self.proposal = None          # the song that came back, not yet kept or let go
        self.proposal_preview = None
        self._before = None           # (song index, the song) the proposal took the place of
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
        #: Switches on pins (`footswitch.Footswitch`), read each `service` pass.
        self.switches = []
        self.model = BacklineModel(project, forward=self.forward, host=self)
        self.device = hmilink.Device(self.model, telemetry_hz=30)
        self.use_kit(kit or project["tracks"][0].get("instrument") or kits.MACHINES[0])
        self._level()

    # -- the sound --------------------------------------------------------------

    def use_kit(self, spec):
        """Play kit ``spec`` from now on. A kit that won't open leaves the one
        before playing and says why in ``error``. The kit playing already
        isn't built again.

        While the song is stopped, the kit before goes first and the heap is
        collected, so the new one is built in the room it left: on a heap in
        pieces, a kit built beside the old one took nearly twice as long."""
        if spec == self.kit_spec():
            self.error = None
            return True
        before = None
        if not self.engine.transport["playing"] and self.bus.kit is not None:
            before = self.bus.kit.spec
            self.engine.set_kit(None)
            self.bus.detach()
            gc.collect()
        try:
            kit = kits.open_kit(spec, self.rate)
        except Exception as e:  # noqa: BLE001 - said on the screen, the old kit plays on
            if before is not None:
                self.use_kit(before)
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
        if self.switches:
            now = e.now_ms()
            for sw in self.switches:
                sw.poll(now)
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
        # -1 while a song that came back from `ask` plays: it isn't one of the songs yet
        t["song_index"] = -1 if self._before is not None else self.song_index
        t["songs"] = len(self.songs)
        t["cast"] = self.cast
        t["ask"] = self.ask_state
        t["ask_error"] = self.ask_error
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
            # The kit first, so the document every panel gets says the kit it plays.
            self.use_kit(project["tracks"][0].get("instrument") or kits.MACHINES[0])
            self.model.load(project)
            return {"name": "song", "index": self.song_index, "kit": self.kit_spec(), "voices": self.voices()}
        if name == "ask":
            return self.ask(args.get("text", ""))
        if name == "proposal":
            return self.proposal_do(args.get("do"))
        if name == "kit":
            spec = args.get("spec")
            if spec is None:
                cur = e.kit.spec if e.kit is not None else None
                i = self.kits.index(cur) if cur in self.kits else -1
                spec = self.kits[(i + int(args.get("step", 1))) % len(self.kits)]
            self.use_kit(spec)
            return {"name": "kit", "spec": self.kit_spec(), "error": self.error, "voices": self.voices()}
        raise ValueError("unknown command %r" % name)

    # -- a song asked for in words ------------------------------------------------

    def ask(self, text):
        """Ask the chat server for a song for ``text``, from the worker."""
        text = " ".join(str(text).split())
        if not text:
            raise ValueError("say what to play")
        if self.ask_settings is None:
            raise ValueError("this box has no chat server set up")
        if self.ask_state == "asking":
            raise ValueError("still asking for the last one")
        if self.asker is None:
            starters = []
            for name, path in song_files():
                try:
                    starters.append((name, load_song(path)))
                except (OSError, ValueError):
                    pass
            choices = [k for k in self.kits if k in kits.MACHINES or k == kits.SOUNDFONT]
            self.asker = askmod.Asker(self.ask_settings, choices, starters, self._post)
        self.ask_state = "asking"
        self.ask_error = ""
        asker = self.asker
        if self.worker is None:
            try:
                found = asker.ask(text)
            except Exception as e:  # noqa: BLE001 - said on every panel
                self._asked(None, e)
            else:
                self._asked(found, None)
        else:
            self.worker.submit(lambda: asker.ask(text), self._asked, key="backline-ask")
        return {"name": "asking", "text": text}

    def _asked(self, found, error):
        """The worker's answer, on the main thread."""
        if error is not None:
            self.ask_state = "failed"
            self.ask_error = str(error) or error.__class__.__name__
            self.device.event("proposal", preview=None, error=self.ask_error)
            return
        project, preview = found
        preview["kit_name"] = kits.title(preview["kit"]) if preview["kit"] in self.kits else preview["kit"]
        self.proposal = project
        self.proposal_preview = preview
        self.ask_state = "ready"
        self.device.event("proposal", preview=preview, error="")

    def proposal_do(self, what):
        """``"play"``, ``"keep"`` or ``"discard"`` the song that came back."""
        if self.proposal is None:
            raise ValueError("no song to %s: ask for one first" % what)
        e = self.engine
        if what == "play":
            if self._before is None:
                self._before = (self.song_index, json.loads(json.dumps(self.model.doc)))
            e.stop()
            self.model.load(json.loads(json.dumps(self.proposal)))
            self.use_kit(self.proposal["tracks"][0]["instrument"])
            e.gesture(0, "tap")
            return {"name": "proposal", "did": "play", "kit": self.kit_spec(), "voices": self.voices()}
        if what == "keep":
            if not self.user_songs:
                raise ValueError("this box has nowhere to keep songs")
            path = self._save(self.proposal)
            self.songs = self.songs + [(path[path.rfind("/") + 1:-5], path)]
            self._titles = None
            if self._before is not None:   # it is the song loaded now
                self.song_index = len(self.songs) - 1
            self._before = None
            self._clear()
            self.device.reset_doc()
            return {"name": "proposal", "did": "keep", "index": len(self.songs) - 1}
        if what == "discard":
            self._clear()
            if self._before is not None:
                index, project = self._before
                e.stop()
                self.song_index = index
                self.model.load(project)
                self.use_kit(project["tracks"][0].get("instrument") or kits.MACHINES[0])
            self._before = None
            return {"name": "proposal", "did": "discard", "kit": self.kit_spec(), "voices": self.voices()}
        raise ValueError("play, keep or discard, not %r" % (what,))

    def _clear(self):
        self.proposal = None
        self.proposal_preview = None
        self.ask_state = ""
        self.ask_error = ""

    def _save(self, project):
        """Write ``project`` into the box's songs folder, under a name of its own."""
        folder = self.user_songs
        try:
            os.mkdir(folder)
        except OSError:
            pass  # there already
        stem = "".join(c if c in _NAME_CHARS else "_" for c in project.get("name", "song").lower()).strip("_") or "song"
        taken = set(n for n, _p in self.songs)
        name, n = stem, 2
        while name in taken:
            name, n = "%s_%d" % (stem, n), n + 1
        path = folder + "/" + name + ".json"
        with open(path, "w") as f:
            json.dump(project, f)
        return path

    def close(self):
        port = self.midi_in
        self.midi_in = None
        if port is not None and hasattr(port, "close"):
            port.close()
        self.device.close()
        self.bus.close()
