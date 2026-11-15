# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What each control sends, what the user changed, and what comes back.

This is the controller without a screen: the mapping from each control to
a note or a CC, the channel, the velocity, the pad bank and the keyboard's
octave, and the MIDI bytes each touch makes. The screen calls `Surface.press`,
`Surface.release` and `Surface.move`, and hands what arrives on the input to
`Surface.feed`, which says which controls should move to match.

A control is named by an id: ``pad0`` to ``pad15`` (``pad0`` at the bottom
left, as on a pad controller), ``knob0`` to ``knob15``, ``fader0`` to
``fader15``, the mixer's ``mix0`` to ``mix7`` with ``mute0`` to ``mute7``
and ``solo0`` to ``solo7``, the XY pad's ``x`` and ``y``, the transport's
``tr0`` to ``tr5`` and the keyboard's ``mod`` wheel. Each maps to
``(kind, number)``, where kind is ``"note"`` or ``"cc"``. The mixer's strips
play on the channel plus the strip's number, so strip 1 is on the channel
and strip 8 seven above it: with the channel at 1, the faders are the
volumes of a synth's first eight parts.
"""

NOTE = "note"
CC = "cc"

#: The defaults, which a saved file only overrides. Pads start at 36, the
#: drum kit's kick; knobs on 70 to 85, a synth's sound controllers (74 is
#: the filter's cutoff); faders on 102 to 117, which nothing else uses.
PADS = 16
KNOBS = 16
FADERS = 16
STRIPS = 8
TRANSPORT = ("Rewind", "Forward", "Stop", "Play", "Record", "Loop")
BANKS = "ABCD"


def _defaults():
    d = {}
    for i in range(PADS):
        d["pad%d" % i] = (NOTE, 36 + i)
    for i in range(KNOBS):
        d["knob%d" % i] = (CC, 70 + i)
    for i in range(FADERS):
        d["fader%d" % i] = (CC, 102 + i)
    for i in range(STRIPS):
        d["mix%d" % i] = (CC, 7)
        d["mute%d" % i] = (CC, 14)
        d["solo%d" % i] = (CC, 15)
    d["x"] = (CC, 16)
    d["y"] = (CC, 17)
    for i in range(len(TRANSPORT)):
        d["tr%d" % i] = (CC, 20 + i)
    d["mod"] = (CC, 1)
    return d


DEFAULT_MAP = _defaults()

#: The settings a file can hold, and their defaults. ``velocity`` 0 means
#: from the touch; 1 to 127 is a fixed velocity.
DEFAULTS = {"channel": 1, "velocity": 0, "bank": 0, "octave": 4, "output": None, "view": "pads"}

#: Controls that are pressed and let go; the rest move through 0 to 127.
_BUTTONS = ("pad", "mute", "solo", "tr")
#: Buttons that stay on until pressed again.
_TOGGLES = ("mute", "solo")
#: How long a control ignores what comes in after a hand moved it, in ms,
#: so a port that echoes (a loopback, a DAW) doesn't pull it back.
HOLD_MS = 300

NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(n):
    """Note *n* as a name and octave, middle C (60) as ``C4``."""
    return "%s%d" % (NAMES[n % 12], n // 12 - 1)


def family(cid):
    """The id without its number: ``"pad"`` for ``"pad12"``."""
    i = len(cid)
    while i and cid[i - 1] in "0123456789":
        i -= 1
    return cid[:i]


def index(cid):
    """The id's number: 12 for ``"pad12"``; 0 for ``"x"``."""
    f = family(cid)
    return int(cid[len(f):]) if len(cid) > len(f) else 0


def is_button(cid):
    return family(cid) in _BUTTONS


def touch_velocity(frac):
    """A velocity from where a finger landed: *frac* is 0 at the soft edge
    and 1 at the hard one. A touch panel reads no pressure, so this is the
    one thing a finger can choose."""
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    return 32 + int(95 * frac + 0.5)


class Surface:
    """The controller's state, and the bytes each touch sends to *out*.

    *out* has ``write(buf, nbytes)`` (a MIDI output port) or is None, when
    the touches are only counted.
    """

    def __init__(self, config=None, out=None):
        self.settings = dict(DEFAULTS)
        self.map = dict(DEFAULT_MAP)
        self.values = {}
        self.out = out
        self.sent = 0
        self.last = None  # the last message, for the status line
        self.error = None
        self.changed = False  # something to save
        self._index = None
        self._moved = {}
        if config:
            self.load(config)

    # -- settings and the mapping --------------------------------------------

    def load(self, config):
        """Take a saved file's dict; anything it lacks keeps its default."""
        for k in DEFAULTS:
            if k in config:
                self.settings[k] = config[k]
        for cid, entry in (config.get("map") or {}).items():
            if cid in DEFAULT_MAP and isinstance(entry, (list, tuple)) and len(entry) == 2:
                kind, num = entry
                if kind in (NOTE, CC) and 0 <= int(num) <= 127:
                    self.map[cid] = (kind, int(num))
        self._clamp()
        self._index = None

    def config(self):
        """What to save: only what differs from the defaults."""
        out = {k: v for k, v in self.settings.items() if v != DEFAULTS[k]}
        edits = {cid: list(m) for cid, m in self.map.items() if m != DEFAULT_MAP[cid]}
        if edits:
            out["map"] = edits
        return out

    def _clamp(self):
        s = self.settings
        s["channel"] = min(16, max(1, int(s["channel"])))
        s["velocity"] = min(127, max(0, int(s["velocity"])))
        s["bank"] = min(len(BANKS) - 1, max(0, int(s["bank"])))
        s["octave"] = min(8, max(-1, int(s["octave"])))

    def set(self, key, value):
        """Change one setting, kept within its range."""
        self.settings[key] = value
        self._clamp()
        self.changed = True
        self._index = None

    def remap(self, cid, kind=None, number=None):
        """Point control *cid* at another note or CC. A control that moves
        through a range stays a CC."""
        old_kind, old_num = self.map[cid]
        kind = kind or old_kind
        if not is_button(cid):
            kind = CC
        number = old_num if number is None else min(127, max(0, int(number)))
        self.map[cid] = (kind, number)
        self.changed = True
        self._index = None

    def reset(self, cid=None):
        """Put one control, or every one, back to its default."""
        if cid is None:
            self.map = dict(DEFAULT_MAP)
        else:
            self.map[cid] = DEFAULT_MAP[cid]
        self.changed = True
        self._index = None

    def channel_of(self, cid):
        """The 0-based channel *cid* plays on."""
        ch = self.settings["channel"] - 1
        if family(cid) in ("mix", "mute", "solo"):
            ch = (ch + index(cid)) % 16
        return ch

    def target(self, cid):
        """``(kind, number, channel)`` for *cid* now, with the pad bank
        applied; the number is None for a pad the bank pushed past 127."""
        kind, num = self.map[cid]
        if family(cid) == "pad" and kind == NOTE:
            num += 16 * self.settings["bank"]
            if num > 127:
                num = None
        return kind, num, self.channel_of(cid)

    def describe(self, cid):
        """What *cid* sends, for its label: ``C1``, ``CC 74``."""
        kind, num, _ = self.target(cid)
        if num is None:
            return "-"
        return note_name(num) if kind == NOTE else "CC %d" % num

    def key_note(self, k):
        """The note of the keyboard's key *k* (0 is the strip's first C)."""
        return 12 * (self.settings["octave"] + 1) + k

    # -- touches ---------------------------------------------------------------

    def velocity(self, frac=None):
        """The fixed velocity, or one from the touch's *frac*."""
        v = self.settings["velocity"]
        if v:
            return v
        return touch_velocity(0.75 if frac is None else frac)

    def _send(self, status, a, b):
        msg = bytes((status, a, b))
        self.last = msg
        out = self.out
        if out is None:
            return msg
        try:
            out.write(msg, 3)
            self.sent += 1
            self.error = None
        except Exception as e:  # noqa: BLE001 - a port that went away says so on the status line
            self.error = str(e) or type(e).__name__
        return msg

    def press(self, cid, frac=None):
        """A button went down (a toggle flips). *frac* says where the finger
        landed, for the velocity. Returns the bytes sent, or None."""
        kind, num, ch = self.target(cid)
        if num is None:
            return None
        if family(cid) in _TOGGLES:
            on = not self.values.get(cid)
            self.values[cid] = 127 if on else 0
            if kind == NOTE:
                return self._send((0x90 if on else 0x80) | ch, num, 127 if on else 0)
            return self._send(0xB0 | ch, num, 127 if on else 0)
        vel = 127 if family(cid) == "tr" else self.velocity(frac)
        self.values[cid] = vel
        return self._send((0x90 if kind == NOTE else 0xB0) | ch, num, vel)

    def release(self, cid):
        """A momentary button let go. Toggles send nothing."""
        if family(cid) in _TOGGLES:
            return None
        kind, num, ch = self.target(cid)
        if num is None:
            return None
        self.values[cid] = 0
        if kind == NOTE:
            return self._send(0x80 | ch, num, 0)
        return self._send(0xB0 | ch, num, 0)

    def move(self, cid, value, now=None):
        """A knob, fader or the XY pad moved to *value* (0 to 127).
        *now* in ms keeps what comes back from moving it again for a while."""
        value = min(127, max(0, int(value)))
        self.values[cid] = value
        if now is not None:
            self._moved[cid] = now
        kind, num, ch = self.target(cid)
        if kind == NOTE:
            return self._send((0x90 if value else 0x80) | ch, num, value)
        return self._send(0xB0 | ch, num, value)

    def key(self, k, down, frac=None):
        """Key *k* of the keyboard strip pressed or let go."""
        n = self.key_note(k)
        if not 0 <= n <= 127:
            return None
        ch = self.settings["channel"] - 1
        if down:
            return self._send(0x90 | ch, n, self.velocity(frac))
        return self._send(0x80 | ch, n, 0)

    def panic(self):
        """All notes off on the channel, and on the mixer's channels."""
        seen = []
        for cid in ["pad0"] + ["mix%d" % i for i in range(STRIPS)]:
            ch = self.channel_of(cid)
            if ch not in seen:
                seen.append(ch)
                self._send(0xB0 | ch, 123, 0)

    # -- what comes in ----------------------------------------------------------

    def _build_index(self):
        idx = {}
        for cid in self.map:
            kind, num, ch = self.target(cid)
            if num is None:
                continue
            idx.setdefault((kind, ch, num), []).append(cid)
        self._index = idx

    def feed(self, data, now=None, since=None):
        """Read whole MIDI messages in *data*; return ``[(cid, value), ...]``
        for each control that should move to match. A note's value is its
        velocity, 0 when it ends. *now* and *since* (``ticks_diff``) skip
        controls a hand moved within `HOLD_MS`."""
        if self._index is None:
            self._build_index()
        out = []
        i = 0
        n = len(data)
        while i < n:
            status = data[i]
            if status < 0x80:
                i += 1  # a stray data byte: the ports hand out whole messages
                continue
            hi = status & 0xF0
            if status >= 0xF0:
                i += 1
                continue
            size = 2 if hi in (0xC0, 0xD0) else 3
            if i + size > n:
                break
            ch = status & 0x0F
            if hi in (0x80, 0x90, 0xB0):
                a, b = data[i + 1], data[i + 2]
                if hi == 0xB0:
                    key = (CC, ch, a)
                    value = b
                else:
                    key = (NOTE, ch, a)
                    value = b if hi == 0x90 else 0
                for cid in self._index.get(key, ()):
                    if now is not None and since is not None and cid in self._moved:
                        if since(now, self._moved[cid]) < HOLD_MS:
                            continue
                    self.values[cid] = value
                    out.append((cid, value))
            i += size
        return out
