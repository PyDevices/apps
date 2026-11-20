# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A pretend phone, for running the receiver on a computer with no radio.

`DemoSink` answers like ``btclassic.AudioSink``: the same properties, the
same ``changes()`` bits and the same transport. It pairs a few seconds after
the app opens, plays a short list of made-up tracks, moves their position
along and follows play, pause, next, previous, volume, repeat and shuffle. Its covers are
drawn by svgio and made into JPEGs by jpegio, so the app decodes them the
way it decodes a phone's. `DemoHandsFree` answers like
``btclassic.HandsFree``: the phone's battery and signal, and its calls.

``BTRECEIVER_DEMO`` holds it in one state, for screenshots: ``pairing``,
``idle``, ``playing``, ``paused``, ``nocover`` (a podcast with no cover, from
a sender with no hands-free link), ``long`` (a long title, with every line
filled in, and a low battery), ``incoming`` (a call ringing) or ``call`` (a
call answered on the board). Without it the demo runs through pairing,
connecting and playing on its own.
"""

import os
import time

CONNECTION = 1
STREAM = 2
FORMAT = 4
TRACK = 8
PLAYING = 16
VOLUME = 32
POSITION = 64
PEER = 128
COVER = 256
SETTINGS = 1 << 26
PHONE = 512
CALL = 1024
AUDIO = 2048

PAIR_MS = 4000  # how long the demo waits to be paired, from the app opening
PLAY_MS = 2500  # and then before it plays

# Made-up tracks; a cover is two colours and a shape, or None for no cover.
TRACKS = (
    {"title": "Neon Tides", "artist": "Halcyon Drive", "album": "Afterglow Coast", "genre": "Synthwave",
     "track_number": 3, "track_count": 11, "duration": 252000, "cover": (0xFF6B3D, 0x7B2CBF, "sun")},
    {"title": "Glass Orchard", "artist": "Mira Quell", "album": "Small Hours", "genre": "Indie Pop",
     "track_number": 7, "track_count": 9, "duration": 218000, "cover": (0x2EC4B6, 0x0B3954, "rings")},
    {"title": "Paper Satellites (Extended Mix)", "artist": "The Low Hum", "album": "Orbit Theory",
     "genre": "Electronic", "track_number": 1, "track_count": 14, "duration": 365000,
     "cover": (0xF2C14E, 0x1D3461, "orbit")},
    {"title": "Episode 42: Signals in the Noise", "artist": "Field Notes", "album": "", "genre": "",
     "track_number": None, "track_count": None, "duration": 2712000, "cover": None},
)

_SHAPES = {
    "sun": '<circle cx="100" cy="112" r="58" fill="url(#g)"/>'
    '<rect x="0" y="128" width="200" height="72" fill="#%06x" opacity=".92"/>'
    '<g stroke="#%06x" stroke-width="3" opacity=".6"><path d="M0 146h200M0 162h200M0 178h200M0 194h200"/></g>',
    "rings": '<g fill="none" stroke="url(#g)" stroke-width="10">'
    '<circle cx="70" cy="80" r="44"/><circle cx="130" cy="120" r="44"/></g>'
    '<circle cx="100" cy="100" r="12" fill="#%06x"/><circle cx="100" cy="100" r="5" fill="#%06x"/>',
    "orbit": '<g fill="none" stroke="#%06x" stroke-width="2" opacity=".75">'
    '<ellipse cx="100" cy="100" rx="78" ry="30" transform="rotate(-24 100 100)"/>'
    '<ellipse cx="100" cy="100" rx="78" ry="30" transform="rotate(36 100 100)"/></g>'
    '<circle cx="100" cy="100" r="30" fill="url(#g)"/><circle cx="160" cy="60" r="8" fill="#%06x"/>',
}


def cover_jpeg(spec):
    """A 200 by 200 JPEG of *spec*, ``(light, dark, shape)``."""
    import jpegio
    import svgio

    light, dark, shape = spec
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#%06x"/><stop offset="1" stop-color="#%06x"/></linearGradient>'
        '<linearGradient id="b" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#%06x"/><stop offset="1" stop-color="#0b0b12"/></linearGradient></defs>'
        '<rect width="200" height="200" fill="url(#b)"/>' % (light, dark, dark)
        + _SHAPES[shape] % (dark, light)
        + "</svg>"
    )
    dec = svgio.SvgDecoder()
    w, h = dec.open(svg.encode(), width=200)
    px = bytearray(w * h * 2)
    dec.decode(px, bytearray(w * h))
    return jpegio.JpegEncoder(quality=88).encode(px, w, h)


def _env(name):
    fn = getattr(os, "getenv", None)
    return fn(name) if fn is not None else None


def _now():
    return time.monotonic() if hasattr(time, "monotonic") else time.ticks_ms() / 1000


class DemoRadio:
    """Stands in for ``btclassic.Bluetooth``: its name, and nothing else."""

    def __init__(self, name="pydevices-speaker"):
        self._name = name

    def config(self, *names, **settings):
        if names == ("name",):
            return self._name
        if names == ("pin",):
            return "0000"
        if "name" in settings:
            self._name = settings["name"]
        return None

    def active(self, active=None):
        return True


class DemoSink:
    """A pretend ``btclassic.AudioSink`` with a phone on the other end."""

    def __init__(self, state=None):
        self.state = state if state is not None else _env("BTRECEIVER_DEMO") or None
        self._t0 = _now()
        self._bits = 0
        self._covers = {}
        self.connected = False
        self.streaming = False
        self.playing = False
        self.status = None
        self.sample_rate = 0
        self.channel_count = 2
        self.bits_per_sample = 16
        self._volume = 92
        self.peer = None
        self.peer_name = ""
        self._index = 0
        self._pos = 0
        self._pos_at = self._t0
        self._rate = 1  # how fast the position moves: 8 or -8 while seeking
        # The phone's battery, as AVRCP reports it; the states show each one.
        self.battery = {"idle": "external", "paused": "full", "long": "warning", "nocover": None}.get(self.state, "normal")
        # The player's modes; the long title's phone doesn't report them.
        self.repeat, self.shuffle = {"playing": ("off", "all"), "paused": ("single", "off"),
                                     "long": (None, None)}.get(self.state, ("off", "off"))
        self._clear_track()
        st = self.state
        if st in ("idle", "playing", "paused", "nocover", "long", "incoming", "call"):
            self._connect()
            if st != "idle":
                self._load({"nocover": 3, "long": 2}.get(st, 0))
                self._pos = 1385000 if st == "nocover" else 102000
                self._set_playing(st != "paused")
                self.sample_rate = 44100  # it streamed before it paused

    # -- the properties btclassic has -----------------------------------

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, v):
        self._volume = max(0, min(127, int(v)))
        self._bits |= VOLUME

    @property
    def position(self):
        if not self.connected or self.duration is None:
            return None
        pos = self._pos
        if self.playing or self._rate != 1:
            pos += int((_now() - self._pos_at) * 1000 * self._rate)
        return max(0, min(pos, self.duration))

    @property
    def cover_size(self):
        c = self._cover()
        return len(c) if c else 0

    @property
    def cover(self):
        return self._cover()

    def cover_into(self, buf):
        c = self._cover()
        if not c:
            return 0
        if len(buf) < len(c):
            raise ValueError("buffer smaller than the cover")
        buf[: len(c)] = c
        return len(c)

    def changes(self):
        self._advance()
        bits, self._bits = self._bits, 0
        return bits

    def levels(self):
        return (12000, 11000) if self.playing else (0, 0)

    def link(self):
        if not self.connected:
            return {"address": None, "name": ""}
        return {"address": self.peer, "name": self.peer_name, "rssi_delta": 0, "codec": "SBC",
                "sample_rate": self.sample_rate, "channels": 2, "channel_mode": "joint stereo",
                "battery": self.battery, "cover_art": True}

    def stats(self):
        return {}

    # -- transport ------------------------------------------------------

    def play(self):
        if self.connected:
            if self.title == "":
                self._load(self._index)
            self._set_playing(True)

    def pause(self):
        if self.connected:
            self._set_playing(False)

    def stop(self):
        self.pause()

    def next(self):
        if self.connected:
            self._load((self._index + 1) % len(TRACKS))
            self._set_playing(True)

    def previous(self):
        if self.connected:
            if (self.position or 0) > 3000:
                self._pos, self._pos_at = 0, _now()
                self._bits |= POSITION
            else:
                self._load((self._index - 1) % len(TRACKS))
            self._set_playing(True)

    def seek(self, direction):
        if not self.connected or not self.title:
            return
        self._pos = self.position or 0
        self._pos_at = _now()
        self._rate = 8 * direction if direction else 1
        self.status = {1: "seeking forward", -1: "seeking back"}.get(direction, "playing" if self.playing else "paused")
        self._bits |= PLAYING | POSITION

    def refresh(self):
        self._bits |= POSITION

    def setting(self, name, value):
        if name not in ("equalizer", "repeat", "shuffle", "scan"):
            raise ValueError("setting is equalizer, repeat, shuffle or scan")
        if self.connected and name in ("repeat", "shuffle") and getattr(self, name) is not None:
            setattr(self, name, value)
            self._bits |= SETTINGS

    def disconnect(self):
        self.connected = False
        self._clear_track()
        self._bits |= CONNECTION | TRACK | COVER | PEER | PLAYING

    def deinit(self):
        self.disconnect()

    # -- the pretend phone ----------------------------------------------

    def _advance(self):
        if self.state is not None:
            return
        age = (_now() - self._t0) * 1000
        if not self.connected and age >= PAIR_MS:
            self._connect()
        elif self.connected and not self.title and age >= PAIR_MS + PLAY_MS:
            self._load(0)
            self._set_playing(True)
        elif self.playing and self.duration and self.position >= self.duration:
            self.next()

    def _connect(self):
        self.connected = True
        self.peer = b"\x5c\xcb\x99\x1a\x2e\x07"
        self.peer_name = "Galaxy S21"
        self._bits |= CONNECTION | PEER

    def _clear_track(self):
        self.title = ""
        self.artist = ""
        self.album = ""
        self.genre = ""
        self.track_number = None
        self.track_count = None
        self.duration = None
        self.playing = False
        self.streaming = False
        self.status = None

    def _load(self, i):
        self._index = i
        t = TRACKS[i]
        for k in ("title", "artist", "album", "genre", "track_number", "track_count", "duration"):
            setattr(self, k, t[k])
        self._pos, self._pos_at = 0, _now()
        self._bits |= TRACK | COVER | POSITION

    def _set_playing(self, on):
        self._pos = self.position or 0
        self._pos_at = _now()
        self.playing = on
        self.status = "playing" if on else "paused"
        if on and not self.streaming:
            self.streaming = True
            self.sample_rate = 44100
            self._bits |= STREAM | FORMAT
        self._bits |= PLAYING | POSITION

    def _cover(self):
        if not self.connected or not self.title:
            return None
        spec = TRACKS[self._index]["cover"]
        if spec is None:
            return None
        c = self._covers.get(self._index)
        if c is None:
            c = self._covers[self._index] = cover_jpeg(spec)
        return c


# The phone's battery and signal, 0 to 5, in each held state. A sender with no
# hands-free link, such as a computer, reports neither.
_PHONE = {"idle": (3, 4), "playing": (4, 3), "paused": (5, 4), "long": (1, 1), "incoming": (4, 3), "call": (4, 3)}
CALLER = "+1 206 555 0143"


class DemoHandsFree:
    """A pretend ``btclassic.HandsFree`` that follows *sink*'s phone.

    It links when the sink connects, reports a battery and a signal, and in
    the ``incoming`` and ``call`` states has a call. The phone pauses its
    music for a call and plays it again after, as a real one does.
    """

    def __init__(self, sink, state=None, call_audio=True):
        self.sink = sink
        # False is a board whose Bluetooth can't carry a call's audio: the
        # call stays on the phone.
        self.call_audio = call_audio
        self.state = state if state is not None else sink.state
        self._bits = 0
        self.connected = False
        self.peer = None
        self.battery = None
        self.signal = None
        self.service = None
        self.operator = ""
        self.call = None
        self.caller = ""
        self.audio = False
        self.sample_rate = 0
        self.mic = None  # what uplink() was last given
        self._resume = False
        self._followed = False  # the sink's connection, as last seen
        if self.state == "incoming":
            self._follow()
            self._ring()
        elif self.state == "call":
            self._follow()
            self._ring()
            self.answer()

    def changes(self):
        self._follow()
        bits, self._bits = self._bits, 0
        return bits

    def answer(self):
        if self.call == "incoming":
            self.call = "active"
            self._audio(True)
            self._bits |= CALL

    def hangup(self):
        if self.call in ("incoming", "dialing", "alerting", "active", "held"):
            self.call = "idle"
            self._audio(False)
            self._bits |= CALL
            if self._resume:
                self._resume = False
                self.sink.play()

    def connect_audio(self):
        if not self.call_audio:
            raise OSError("this board doesn't take calls' audio")
        if self.call in ("active", "dialing", "alerting"):
            self._audio(True)

    def disconnect_audio(self):
        self._audio(False)

    def uplink(self, mic):
        self.mic = mic

    def stats(self):
        return {"sent": 0, "unsent": 0}

    def deinit(self):
        self._audio(False)
        self.connected = False
        self.call = None

    # -- the pretend phone ----------------------------------------------

    def _follow(self):
        # The hands-free link comes up and goes down with the music's.
        if self.sink.connected == self._followed:
            return
        self._followed = self.sink.connected
        # A computer has no hands-free side: the nocover state's sender.
        self.connected = self._followed and self.state != "nocover"
        level = _PHONE.get(self.state, (4, 3)) if self.connected else (None, None)
        self.battery, self.signal = level
        self.service = None if level[1] is None else True
        self.operator = "Northwind" if self.connected else ""
        self.peer = self.sink.peer if self.connected else None
        self.call = "idle" if self.connected else None
        self._bits |= CONNECTION | PHONE | CALL

    def _ring(self):
        self.call = "incoming"
        self.caller = CALLER
        self._bits |= CALL
        if self.sink.playing:
            self._resume = True
            self.sink.pause()

    def _audio(self, on):
        if on == self.audio or (on and not self.call_audio):
            return
        self.audio = on
        self.sample_rate = 16000 if on else 0
        self._bits |= AUDIO
