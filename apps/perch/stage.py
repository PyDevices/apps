# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Put a place and the chameleon on an LVGL screen, and keep them moving.

A `Stage` draws the place once into one RGB565 buffer behind an ``lv.image``.
The chameleon is a second image over it: each pose is drawn by svgio into its
own RGB565A8 buffer and kept, so a walk, a blink or a wave is a change of
picture and a move, which LVGL blends. The poses it will want are drawn ahead,
a step a tick, while it stands there. Building the shapes, parsing them and
drawing them are separate steps, each in its own timer tick, so nothing holds
the screen for long; `Stage.stats` says how long each took.
"""

import gc
import time

import lvgl as lv
import svgio

from . import chameleon_props, chameleon_shift, chameleon_views, mascot_chameleon, scene_bench, scene_coast, scene_desk
from .vec import Doc, at, circle

TICK_MS = 40
SCENE_W, SCENE_H = 800, 480
NAVY = 0x0B2A4A
DOCS_KEPT = 3  # places whose shapes are kept, so going back to one skips building it
CACHE_BYTES = 6 * 1024 * 1024  # poses kept, beside the one on screen and the one just drawn
STRIDE = 63.3  # how far a full turn of the walk carries the body, in its own units
# Working memory for the two decoders, where this svgio gives a decoder its
# own: a place at 800 pixels wide wants about 600 KB, a pose about 150.
PLACE_MEMORY = 768 * 1024
POSE_MEMORY = 256 * 1024
BAND_ROWS = 120  # a place is painted about this many rows a tick, where svgio draws bands

# Where each kind of pose reaches, in the chameleon's units: x, y, width, height.
_BODY = (-222, -224, 416, 246)
_REACH = (-222, -224, 540, 246)
_HOLD = (-222, -250, 536, 274)
_FRONT = (-184, -296, 340, 318)
_SLEEP = (-222, -226, 506, 248)

# Where its eyes go when it looks about: the near eye, the far eye.
_LOOKS = (
    ((0.5, 0.1), (0.5, 0.1)),
    ((-0.6, 0.2), (0.7, -0.4)),
    ((0.9, 0.4), (-0.5, -0.6)),
    ((0.1, -0.7), (0.8, 0.3)),
)
# at the bench: on the joint, one eye up at you, both on you
_WORK_LOOKS = (((0.9, 0.55), (0.75, 0.35)), ((0.9, 0.55), (-0.6, -0.3)), ((-0.5, 0.1), (0.75, 0.35)))
_BUG = (300, -150)  # where a bug hovers and the tongue strikes, in the head's units
# the solder joint on the workbench's board, in the chameleon's units: x, y, radius
_JOINT = (
    (scene_bench.BOARD_X + 34 - scene_bench.HUE_X) / scene_bench.HUE_SCALE,
    (scene_bench.BOARD_Y + 97.5 - scene_bench.HUE_Y) / scene_bench.HUE_SCALE,
    7 / scene_bench.HUE_SCALE,
)
_HELD = ("flower", "flag", "sparkler", "magnifier", "balloon", "mug")
_CHOICES = ("blink", "blink", "look", "look", "stroll", "tongue", "turn", "hold")


def _coast(doc, variant):
    night = variant == "night"
    scene_coast.draw(doc, season="summer" if night else variant, night=night, who="stage", drift=False)


def _bench(doc, variant):
    scene_bench.draw(doc, who="stage")


def _desk(doc, variant):
    scene_desk.draw(doc, who="stage", time=variant)


# Each place: its variants (the first is where it opens), how to draw one, the
# colours the chameleon takes there (None when the variant is the scheme),
# where its perch is and how large it stands, how far along the perch it may
# walk, what it does there, and what it does first.
PLACES = {
    "coast": {
        "variants": ("summer", "autumn", "winter", "night", "spring"),
        "build": _coast,
        "schemes": {"spring": "blossom", "summer": "leaf", "autumn": "sunset", "winter": "snow", "night": "night"},
        "at": (322, 404, 0.6),
        "walk": (-40, 76),
        "life": "stroll",
        "first": ("blink", "stroll", "tongue"),
    },
    "bench": {
        "variants": ("board", "brand", "copper", "leaf"),
        "build": _bench,
        "schemes": None,
        "at": (scene_bench.HUE_X, scene_bench.HUE_Y, scene_bench.HUE_SCALE),
        "walk": None,
        "life": "work",
        "first": ("blink", "look"),
    },
    "desk": {
        "variants": ("day", "evening", "night"),
        "build": _desk,
        "schemes": {"day": "leaf", "evening": "sunset", "night": "night"},
        "at": scene_desk.SPOTS["books"],
        "walk": (-22, 26),
        "life": "desk",
        "first": ("blink", "turn", "stroll"),
    },
}
ORDER = ("coast", "bench", "desk")
VIEWS = ("wide", "mid", "close")
_ZOOM = {"wide": 1.0, "mid": 1.75, "close": 3.3}
# what the air carries, per place and variant: kind, how many
_AIR = {
    ("coast", "spring"): ("petal", 14),
    ("coast", "autumn"): ("leaf", 14),
    ("coast", "winter"): ("snow", 26),
    ("coast", "night"): ("firefly", 10),
    ("desk", "night"): ("firefly", 4),
}
_AIR_COLORS = {
    "petal": (0xFFA9C4, 0xFFD3E0, 0xFFFFFF),
    "leaf": (0xFFC83D, 0xF58B2A, 0xC9482B),
    "snow": (0xFFFFFF, 0xFFFFFF, 0xE6F0F8),
    "firefly": (0xE8FF8A, 0xFDFFE0, 0xC4DC4C),
}

# one turn of a sine in 64 steps, so moving the air costs no math calls
_SIN = (
    0.0, 0.098, 0.195, 0.29, 0.383, 0.471, 0.556, 0.634, 0.707, 0.773, 0.831, 0.882, 0.924, 0.957, 0.981, 0.995,
    1.0, 0.995, 0.981, 0.957, 0.924, 0.882, 0.831, 0.773, 0.707, 0.634, 0.556, 0.471, 0.383, 0.29, 0.195, 0.098,
    0.0, -0.098, -0.195, -0.29, -0.383, -0.471, -0.556, -0.634, -0.707, -0.773, -0.831, -0.882, -0.924, -0.957, -0.981, -0.995,
    -1.0, -0.995, -0.981, -0.957, -0.924, -0.882, -0.831, -0.773, -0.707, -0.634, -0.556, -0.471, -0.383, -0.29, -0.195, -0.098,
)  # fmt: skip


def _decoder(memory):
    """A decoder that works in *memory* bytes of its own, where this svgio has that.

    Its parses and draws then ask the heap for nothing, so they take the same
    time whatever the heap holds. An older svgio gives a plain decoder.
    """
    try:
        return svgio.SvgDecoder(memory=memory)
    except TypeError:
        return svgio.SvgDecoder()


class _Random:
    # the same choices on every runtime and every run
    def __init__(self, seed):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.state >> 8) / 8388608.0

    def below(self, n):
        return int(self.next() * n) % n


def _pose(doc, spec, scheme):
    """The chameleon's shapes for a pose, and the box they fit in."""
    kind = spec[0]
    draw = mascot_chameleon.draw
    if kind == "stand":
        look, far = _LOOKS[spec[1]]
        return draw(doc, look=look, look_far=far, blink=spec[2], colors=scheme, perch=None), _BODY
    if kind == "walk":
        return draw(doc, step=spec[1] / 8, colors=scheme, perch=None), _BODY
    if kind == "happy":
        return draw(doc, mood="happy", hand=1, look=(-0.2, 0.1), colors=scheme, perch=None), _BODY
    if kind == "aim":
        return draw(doc, look=(1, 0.0), look_far=(1, 0.3), nod=-4, colors=scheme, perch=None), _BODY
    if kind == "tongue":
        return draw(doc, look=(1, 0.0), look_far=(1, 0.3), nod=-4, tongue=spec[1], target=_BUG, colors=scheme, perch=None), _REACH
    if kind == "work":
        look, far = _WORK_LOOKS[spec[1]]
        nod = 0 if spec[1] == 2 else 6
        body = chameleon_props.hold(doc, "iron", lean=80, look=look, look_far=far, blink=spec[2], colors=scheme, perch=None, nod=nod)
        # the joint glows where the iron's tip rests on the board
        glow = doc.radial([(0, 0xFFF3B0, 0.9), (0.5, 0xFFB26B, 0.45), (1, 0xFFB26B, 0)])
        return body + circle(_JOINT[0], _JOINT[1], _JOINT[2], glow), _HOLD
    if kind == "hold":
        mood = "happy" if spec[2] else "calm"
        return chameleon_props.hold(doc, spec[1], look=(0.4, -0.2), look_far=(-0.5, 0.1), mood=mood, colors=scheme, perch=None), _HOLD
    if kind == "front":
        mood = "happy" if spec[1] else "calm"
        return chameleon_views.front(doc, look=(0.0, 0.1), hand=spec[1], blink=spec[2], mood=mood, colors=scheme, perch=None), _FRONT
    if kind == "sleep":
        return mascot_chameleon.draw_sleep(doc, colors=scheme, perch=None), _SLEEP
    raise ValueError("no such pose: %r" % (spec,))


class Stage:
    """The picture on *root*, *size* pixels: a place, the chameleon, the air.

    Call `tick` every `TICK_MS`. `go`, `next_place`, `next_variant` and
    `next_view` change what is shown, and `tap` is a finger on the picture.
    `cues` is a list of things for the chameleon to do next ("stroll",
    "tongue", "blink", "look", "turn", "hold"), ahead of its own choices.
    """

    def __init__(self, root, size, place="coast", variant=None, view="wide", seed=7):
        self.w, self.h = size
        self.root = root
        self.random = _Random(seed)
        self.cues = []
        #: What the work cost, for whoever is timing it. Microseconds in
        #: ``build`` (the shapes and their text, in Python), ``tidy`` (the
        #: collection as a place or the colours change), ``alloc`` (finding a
        #: pose's buffer), ``parse`` and ``draw`` (svgio), with the longest
        #: parse and draw of a pose; how many ``scenes`` and ``poses`` were
        #: drawn; the longest tick while a place was loading and while it was
        #: showing, how many showing ticks took over 150 ms, and what the
        #: slowest was doing; milliseconds from the last change being asked for
        #: to its picture and to the chameleon standing in it, and from opening
        #: to the first tick, place, pose and step of a walk; and the most
        #: bytes of picture ever held, and the most working memory a place
        #: and a pose took in their decoders (0 from an svgio without it).
        self.stats = {
            "build": 0,
            "tidy": 0,
            "alloc": 0,
            "parse_max": 0,
            "draw_max": 0,
            "parse": 0,
            "draw": 0,
            "scenes": 0,
            "poses": 0,
            "tick_load_us": 0,
            "tick_show_us": 0,
            "slow_ticks": 0,
            "slowest": None,
            "picture_ms": None,
            "change_ms": None,
            "first_tick_ms": None,
            "first_picture_ms": None,
            "first_pose_ms": None,
            "first_walk_ms": None,
            "peak": 0,
            "place_memory": 0,
            "pose_memory": 0,
        }
        self._born = time.ticks_ms()
        self._asked = self._born  # when the change being drawn was asked for
        self._decoder = _decoder(PLACE_MEMORY)
        self._poser = _decoder(POSE_MEMORY)
        # an svgio whose decoders have memory of their own also draws in bands
        self._bands = hasattr(self._decoder, "memory")
        self._docs = {}  # (place, what the ground shows) -> its shapes
        self._doc_order = []
        self._frames = {}  # (spec, flip, scheme) -> (descriptor, buffer, x offset, y offset)
        self._order = []  # the same keys, least lately used first
        self._bytes = 0
        self._shown = None
        self._made = None  # the last pose drawn that isn't kept
        self._loose = None  # the pose on screen, when it isn't one of the kept
        self._pool = {}  # size -> buffers let go, to draw into again
        self._pooled = 0
        self._wanted = []  # poses to draw ahead, soonest first
        self._maker = None  # the pose being drawn, a step a tick
        self._making = None
        self._quiet = False  # nothing is drawn while it walks or strikes
        self._life = None
        self._wait = 0
        self._facing = 1
        self._walked = 0.0  # along the perch, in the chameleon's units
        self._air = []
        self._air_kind = None
        self._ticks = 0
        self._step = None  # what the pose being drawn did this tick, for `stats`
        #: True while a place, a variant or a view is being changed.
        self.busy = True
        #: The pose on screen, as `Stage` names poses, or None.
        self.pose = None

        # the place: one buffer, navy until the first one is drawn
        # svgio fills it: a row at a time from Python takes seconds on a board
        self._ground = bytearray(self.w * (self.h + 2) * 2)
        fill = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"><rect width="%d" height="%d" fill="#%06x"/></svg>'
        self._decoder.open((fill % (self.w, self.h, self.w, self.h, NAVY)).encode())
        self._decoder.decode(self._ground, stride=self.w)
        self._ground_dsc = self._descriptor(self._ground, self.w, self.h, lv.COLOR_FORMAT.RGB565)
        self.ground = lv.image(root)
        self.ground.set_src(self._ground_dsc)
        self.ground.set_pos(0, 0)
        self.ground.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._air_layer = lv.obj(root)
        self._air_layer.remove_style_all()
        self._air_layer.set_size(self.w, self.h)
        self._air_layer.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._air_layer.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.hue = lv.image(root)
        self.hue.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.hue.add_flag(lv.obj.FLAG.HIDDEN)
        self.bug = lv.image(root)
        self.bug.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        self._bug_frame = None

        self.place = self.variant = self.view = self.scheme = None
        self._rect = None
        self._painted = None
        self._loader = self._change(place, variant or PLACES[place]["variants"][0], view)

    # -- buffers --------------------------------------------------------

    def _descriptor(self, data, w, h, cf):
        d = lv.image_dsc_t()
        d.header.magic = lv.IMAGE_HEADER_MAGIC
        d.header.cf = cf
        d.header.w = w
        d.header.h = h
        d.header.stride = w * 2
        d.data_size = w * h * (3 if cf == lv.COLOR_FORMAT.RGB565A8 else 2)
        d.data = data
        return d

    def held_bytes(self):
        """Bytes of picture held now: the place, the poses, the bug."""
        total = len(self._ground) + self._bytes + self._pooled
        if self._loose is not None:
            total += len(self._loose[1])
        if self._bug_frame:
            total += len(self._bug_frame[1])
        if self._made is not None:
            total += len(self._made[1])
        return total

    def _since(self, t0, phase):
        """Add the microseconds since *t0* to a phase of `stats`; return now."""
        now = time.ticks_us()
        self.stats[phase] += time.ticks_diff(now, t0)
        return now

    def _roomiest(self, what, decoder):
        peak = getattr(decoder, "memory_peak", 0)
        if peak > self.stats[what]:
            self.stats[what] = peak

    def _first(self, what):
        if self.stats[what] is None:
            self.stats[what] = time.ticks_diff(time.ticks_ms(), self._born)

    def _tidy(self):
        # svgio asks MicroPython for memory hundreds of times in a parse, and
        # each request is looked for from the first free block on, past every
        # picture held and everything dropped since the last collection: on an
        # ESP32-P4 a place parsed in 0.8 s just after one and in 5 s without.
        # A collection also reads every picture held (0.4 s for six megabytes
        # of them), so the poses and spare buffers are let go first.
        t0 = time.ticks_us()
        self._pool = {}
        self._pooled = 0
        gc.collect()
        self._since(t0, "tidy")

    def _buffer(self, size):
        """A buffer of *size* bytes for a picture: one let go earlier, if there is one.

        Poses of one kind are all one size, so taking them from a pool leaves
        the heap as it was, where new megabytes each time would fill it with gaps.
        """
        spare = self._pool.get(size)
        if spare:
            self._pooled -= size
            return spare.pop()
        return bytearray(size)

    def _spare(self, data):
        size = len(data)
        if self._pooled + size <= CACHE_BYTES:
            self._pool.setdefault(size, []).append(data)
            self._pooled += size

    # -- where things are -----------------------------------------------

    def _fit(self, place, view):
        """The part of the place this screen shows: x, y, width, height."""
        x, y, k = PLACES[place]["at"]
        aspect = self.w / self.h
        vw = SCENE_W / _ZOOM[view]
        vh = vw / aspect
        if vh > SCENE_H:
            vh = SCENE_H
            vw = vh * aspect
        # keep the chameleon in the picture, and its face when close
        if view == "close":
            fx, fy = x + 118 * k, y - 118 * k
        elif view == "mid" or vw < SCENE_W * 0.7:
            fx, fy = x + 10 * k, y - 100 * k
        else:
            fx, fy = SCENE_W / 2, SCENE_H / 2
        vx = min(max(fx - vw / 2, 0), SCENE_W - vw)
        vy = min(max(fy - vh / 2, 0), SCENE_H - vh)
        return vx, vy, vw, vh

    def _origin(self):
        """The chameleon's own origin on the screen, in pixels."""
        x, y, k = PLACES[self.place]["at"]
        vx, vy, vw, _ = self._rect
        s = self.w / vw
        return (x + self._walked * k - vx) * s, (y - vy) * s

    # -- poses ----------------------------------------------------------

    def _key(self, spec, scheme=None):
        return (spec, self._facing < 0, scheme or self.scheme)

    def _make(self, spec, scheme=None, keep=True):
        """Draw the pose *spec* in four steps: its shapes, the parse, its buffer, the picture.

        A generator: each ``next`` does one step. The pose is kept under its
        key, or left in ``_made`` when it isn't to be kept.
        """
        scheme = scheme or self.scheme
        flip = self._facing < 0
        key = (spec, flip, scheme)
        if keep and key in self._frames:
            return
        self._making = key
        x, y, k = PLACES[self.place]["at"]
        vx, vy, vw, vh = self._rect
        s = self.w / vw
        t0 = time.ticks_us()
        doc = Doc()
        body, (rx, ry, rw, rh) = _pose(doc, spec, scheme)
        if flip:
            body = at(0, 0, body, flip=True)
            rx = -rx - rw
        if self.view != "wide":
            # zoomed in, it stays put, so only what the screen shows is drawn
            left = max(rx, (vx - x) / k - self._walked)
            top = max(ry, (vy - y) / k)
            right = min(rx + rw, (vx + vw - x) / k - self._walked)
            bottom = min(ry + rh, (vy + vh - y) / k)
            rx, ry, rw, rh = left, top, max(right - left, 1), max(bottom - top, 1)
        doc.add(body)
        text = doc.svg((rx, ry, rw, rh)).encode()
        doc = body = None
        self._since(t0, "build")
        self._step = ("build", spec)
        yield
        t0 = time.ticks_us()
        # not the place's decoder: a place may be parsed between these steps
        decoder = self._poser
        w, h = decoder.open(text, width=max(2, int(rw * k * s + 0.5)))
        text = None
        self.stats["parse_max"] = max(self.stats["parse_max"], time.ticks_diff(time.ticks_us(), t0))
        self._since(t0, "parse")
        self._step = ("parse", spec)
        yield
        self._step = ("alloc", spec)
        t0 = time.ticks_us()
        data = self._buffer(w * h * 3)
        self._since(t0, "alloc")
        yield
        self._step = ("draw", spec)
        t0 = time.ticks_us()
        planes = memoryview(data)
        decoder.decode(planes[: w * h * 2], planes[w * h * 2 :])
        self._roomiest("pose_memory", decoder)
        planes = decoder = None
        self.stats["draw_max"] = max(self.stats["draw_max"], time.ticks_diff(time.ticks_us(), t0))
        self._since(t0, "draw")
        self.stats["poses"] += 1
        frame = (self._descriptor(data, w, h, lv.COLOR_FORMAT.RGB565A8), data, round(rx * k * s), round(ry * k * s))
        self._making = None
        if not keep:
            self._made = frame
        elif key not in self._frames:
            self._frames[key] = frame
            self._order.append(key)
            self._bytes += len(data)
            while self._bytes > CACHE_BYTES and len(self._order) > 2:
                old = self._order[0]
                if self._frames[old] is self._shown:
                    old = self._order[1]
                self._drop(old)
        self.stats["peak"] = max(self.stats["peak"], self.held_bytes())

    def _frame(self, spec):
        """The kept pose *spec*, drawn here and now if it hasn't been."""
        key = self._key(spec)
        if key not in self._frames:
            for _ in self._make(spec):
                pass
        else:
            self._order.remove(key)
            self._order.append(key)
        return self._frames[key]

    def _have(self, spec):
        return self._key(spec) in self._frames

    def _ready(self, *specs):
        """Wait, a tick at a time, until every pose in *specs* is drawn.

        A generator for the chameleon's life to ``yield from``. It puts the
        poses at the head of the queue and gives True once they are all
        there, or False if they can't all be kept at once.
        """
        for _ in range(40 + 12 * len(specs)):
            missing = [spec for spec in specs if not self._have(spec)]
            if not missing:
                return True
            for spec in reversed(missing):
                if self._key(spec) != self._making:
                    if spec in self._wanted:
                        self._wanted.remove(spec)
                    self._wanted.insert(0, spec)
            yield 1
        return False

    def _work(self):
        """One step of drawing a pose ahead: the next in the queue, or the one begun."""
        if self._maker is None:
            while self._wanted:
                spec = self._wanted.pop(0)
                if not self._have(spec):
                    self._maker = self._make(spec)
                    break
            else:
                return
        try:
            next(self._maker)
        except StopIteration:
            self._maker = None

    def _drop(self, key):
        frame = self._frames.pop(key)
        self._order.remove(key)
        self._bytes -= len(frame[1])
        self._spare(frame[1])
        # LVGL may remember a picture by its address, which the next one could be given
        lv.image.cache_drop(frame[0])
        lv.image.header_cache_drop(frame[0])

    def _forget(self, keep_scheme=None):
        """Drop the kept poses, all of them or all but one scheme's."""
        self._wanted = []
        self._maker = self._making = None
        for key in list(self._order):
            if self._frames[key] is self._shown:
                continue
            if keep_scheme is None or key[2] != keep_scheme:
                self._drop(key)

    def _show(self, spec):
        """Put the kept pose *spec* on the screen."""
        self._put(self._frame(spec), spec)
        if spec[0] == "walk":
            self._first("first_walk_ms")

    def _put(self, frame, spec):
        if self._loose is not None and self._loose is not frame:
            # the pose it was showing wasn't kept: its buffer can be used again
            lv.image.cache_drop(self._loose[0])
            lv.image.header_cache_drop(self._loose[0])
            self._spare(self._loose[1])
            self._loose = None
        if frame not in self._frames.values():
            self._loose = frame
        self._shown = frame
        self.pose = spec
        self.hue.set_src(frame[0])
        self._place_hue()
        self.hue.remove_flag(lv.obj.FLAG.HIDDEN)
        self._first("first_pose_ms")

    def _place_hue(self):
        if self._shown is None:
            return
        ox, oy = self._origin()
        self.hue.set_pos(round(ox) + self._shown[2], round(oy) + self._shown[3])

    # -- the place ------------------------------------------------------

    def _ground_key(self):
        # the bench is the same bench whatever colours the chameleon wears
        return self.variant if PLACES[self.place]["schemes"] else None

    def _shapes(self):
        """The place's shapes, built now or kept from the last time it was shown."""
        key = (self.place, self._ground_key())
        doc = self._docs.get(key)
        if doc is None:
            t0 = time.ticks_us()
            doc = Doc()
            PLACES[self.place]["build"](doc, self.variant)
            self._since(t0, "build")
            self._docs[key] = doc
            while len(self._doc_order) >= DOCS_KEPT:
                del self._docs[self._doc_order.pop(0)]
        else:
            self._doc_order.remove(key)
        self._doc_order.append(key)
        return doc

    def _rest(self):
        """The pose it comes back to in this place."""
        life = PLACES[self.place]["life"]
        if life == "work":
            return ("work", 0, 0)
        if life == "desk" and self.variant == "night":
            return ("sleep",)
        return ("stand", 0, 0)

    def _blend(self, rest, scheme):
        """Draw the resting pose in a scheme part way to the next, and show it."""
        yield from self._make(rest, scheme, keep=False)
        self._put(self._made, rest)
        self._made = None
        yield

    def _change(self, place, variant, view):
        """Go to a place, a variant of it and a view: the steps, one a tick.

        After a collection the place takes three: its shapes are built,
        parsed, then drawn over the old picture in one go. Where only the colours change, the
        chameleon is then redrawn part way to the new ones, twice, on its way
        to them.
        """
        self.busy = True
        self._life = None
        self._quiet = False
        # a pose half drawn is dropped: the poses share one decoder
        self._maker = self._making = None
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        old_scheme = self.scheme
        schemes = PLACES[place]["schemes"]
        new_scheme = schemes[variant] if schemes else variant
        moved = place != self.place or view != self.view
        was_asleep = self.place is not None and self._rest() == ("sleep",)
        if moved:
            # somewhere else, or seen from somewhere else: it stays in the old
            # picture until the new one is drawn, then comes back there
            self._forget()
            self._bug_frame = None
            self._walked = 0.0
            self._facing = 1
        self.place, self.variant, self.view = place, variant, view
        self._rect = self._fit(place, view)
        rest = self._rest()
        blends = []
        if not moved and old_scheme and old_scheme != new_scheme and rest[0] != "sleep" and not was_asleep:
            blends = [chameleon_shift.between(old_scheme, new_scheme, t) for t in (0.33, 0.67)]
        if old_scheme != new_scheme:
            # nothing drawn in the old colours will be wanted again
            self._forget()
        if moved or old_scheme != new_scheme:
            self._tidy()
            yield
        if self._painted != (place, self._ground_key(), view):
            doc = self._shapes()
            yield
            t0 = time.ticks_us()
            text = doc.svg(self._rect).encode()
            doc = None
            t0 = self._since(t0, "build")
            self._decoder.open(text, width=self.w)
            text = None
            self._since(t0, "parse")
            yield
            if self._bands:
                # a band a tick, so the picture arrives down the screen and
                # no tick waits for all of it. Bands are whole strips of
                # svgio's, so no row is drawn twice.
                strip = max(1, 65536 // (4 * self.w))
                band = strip * max(1, (BAND_ROWS + strip - 1) // strip)
                for y0 in range(0, self.h, band):
                    t0 = time.ticks_us()
                    self._decoder.decode(self._ground, stride=self.w, rows=(y0, min(y0 + band, self.h)))
                    self._since(t0, "draw")
                    self.ground.invalidate()
                    if y0 + band < self.h:
                        yield
            else:
                t0 = time.ticks_us()
                self._decoder.decode(self._ground, stride=self.w)
                self._since(t0, "draw")
            self._roomiest("place_memory", self._decoder)
            self.stats["scenes"] += 1
            self.ground.invalidate()
            if moved:
                self.hue.add_flag(lv.obj.FLAG.HIDDEN)
                self._shown = self.pose = None
            self._painted = (place, self._ground_key(), view)
            self._first("first_picture_ms")
            self.stats["picture_ms"] = time.ticks_diff(time.ticks_ms(), self._asked)
            self._set_air()
            yield
        else:
            self._set_air()
        while blends:
            yield from self._blend(rest, blends.pop(0))
        for name in list(mascot_chameleon.COLORS):
            if ">" in name:
                del mascot_chameleon.COLORS[name]
        self.scheme = new_scheme
        yield from self._make(rest)
        self._show(rest)
        self.stats["change_ms"] = time.ticks_diff(time.ticks_ms(), self._asked)
        self._forget(new_scheme)
        self.stats["peak"] = max(self.stats["peak"], self.held_bytes())
        # what it will want next, drawn ahead while it stands there
        wide = view == "wide"
        ahead = []
        if rest[0] != "sleep":
            ahead.append((rest[0], rest[1], 1))
            if PLACES[place]["walk"] is not None and wide and rest[0] == "stand":
                ahead.extend(("walk", n) for n in range(8))
            if rest[0] == "work":
                ahead.extend((("work", 1, 0), ("work", 2, 0)))
            else:
                ahead.extend(("stand", n, 0) for n in range(1, len(_LOOKS)))
                if wide:
                    ahead.extend((("aim",), ("tongue", 0.5), ("tongue", 1), ("happy",)))
        self._wanted = ahead
        if not self.cues:
            self.cues.extend(PLACES[place]["first"])
        self.busy = False
        self._life = self._live()
        self._wait = 4

    # -- what it does ---------------------------------------------------

    def _live(self):
        """Its life in this place: one thing after another, for ever."""
        life = PLACES[self.place]["life"]
        rest = self._rest()
        can_walk = PLACES[self.place]["walk"] is not None and self.view == "wide" and rest[0] == "stand"
        pause = 6
        while True:
            self._quiet = False
            if rest[0] == "stand" and not self._have(rest):
                # it has turned round: the same pose, facing the other way
                yield from self._ready(rest)
            self._show(rest)
            yield pause
            # what it was asked to do comes promptly; its own ideas take their time
            pause = 6 if self.cues else 12 + self.random.below(30)
            if self.cues:
                what = self.cues.pop(0)
            else:
                what = _CHOICES[self.random.below(len(_CHOICES))]
            if rest[0] == "sleep":
                continue
            if what == "blink":
                shut = (rest[0], rest[1], 1)
                if (yield from self._ready(shut)):
                    self._show(shut)
                    yield 4
            elif what == "look":
                if life == "work":
                    spec = ("work", 1 + self.random.below(2), 0)
                else:
                    spec = ("stand", 1 + self.random.below(len(_LOOKS) - 1), 0)
                if (yield from self._ready(spec)):
                    self._show(spec)
                    yield 20 + self.random.below(25)
            elif what == "stroll" and can_walk:
                yield from self._stroll()
            elif what == "tongue" and rest[0] == "stand" and self.view != "close" and self._facing > 0:
                yield from self._catch()
            elif what == "turn" and life == "desk":
                yield from self._greet()
            elif what == "hold" and rest[0] == "stand" and self._facing > 0:
                prop = _HELD[self.random.below(len(_HELD))]
                if (yield from self._ready(("hold", prop, 0), ("hold", prop, 1))):
                    self._show(("hold", prop, 0))
                    yield 30
                    self._show(("hold", prop, 1))
                    yield 45

    def _stroll(self):
        """A walk to the other end of the perch, once every step of it is drawn."""
        low, high = PLACES[self.place]["walk"]
        goal = high if self._walked < (low + high) / 2 else low
        facing = 1 if goal > self._walked else -1
        if facing != self._facing:
            self._facing = facing
            if not (yield from self._ready(("stand", 0, 0))):
                return
            self._show(("stand", 0, 0))
            yield 6
        if not (yield from self._ready(*[("walk", n) for n in range(8)])):
            return
        self._quiet = True
        phase = 0
        per_tick = STRIDE / 8 / 3  # three ticks a picture, eight pictures a stride
        while (goal - self._walked) * facing > 0:
            self._show(("walk", (phase // 3) % 8))
            self._walked += per_tick * facing
            self._place_hue()
            phase += 1
            yield 1
        self._show(("stand", 0, 0))
        self._quiet = False
        yield 8

    def _catch(self):
        """A bug drifts in ahead of it, and the tongue takes it."""
        if not (yield from self._ready(("aim",), ("tongue", 0.5), ("tongue", 1), ("happy",))):
            return
        x, y, k = PLACES[self.place]["at"]
        s = self.w / self._rect[2]
        if self._bug_frame is None:
            t0 = time.ticks_us()
            doc = Doc()
            doc.add(mascot_chameleon._bug(0, 0, 1.4))
            text = doc.svg((-30, -30, 60, 60)).encode()
            t0 = self._since(t0, "build")
            w, h = self._decoder.open(text, width=max(2, int(60 * k * s + 0.5)))
            t0 = self._since(t0, "parse")
            data = bytearray(w * h * 3)
            planes = memoryview(data)
            self._decoder.decode(planes[: w * h * 2], planes[w * h * 2 :])
            self._since(t0, "draw")
            self._bug_frame = (self._descriptor(data, w, h, lv.COLOR_FORMAT.RGB565A8), data, w, h)
            self.bug.set_src(self._bug_frame[0])
            yield 1
        self._quiet = True
        half = self._bug_frame[2] // 2
        ox, oy = self._origin()
        bx = ox + (_BUG[0] + 4) * k * s
        by = oy + (_BUG[1] + 22 + 4) * k * s
        self.bug.remove_flag(lv.obj.FLAG.HIDDEN)
        for i in range(24, -1, -1):
            # it perchs in from up and to the right
            wobble = ((i * 7) % 9 - 4) * (i / 24)
            self.bug.set_pos(int(bx + i * 5 * s + wobble) - half, int(by - i * 3.2 * s + wobble * 2) - half)
            if i == 14:
                self._show(("aim",))
            yield 1
        yield 6
        self._show(("tongue", 0.5))
        yield 1
        self._show(("tongue", 1))
        yield 4
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        self._show(("tongue", 0.5))
        yield 1
        self._show(("happy",))
        self._quiet = False
        yield 22

    def _greet(self):
        """It turns to face you, waves, and turns back."""
        if not (yield from self._ready(("front", 0, 0), ("front", 1, 0), ("front", 1, 1))):
            return
        self._show(("front", 0, 0))
        yield 10
        self._show(("front", 1, 0))
        yield 26
        self._show(("front", 1, 1))
        yield 4
        self._show(("front", 1, 0))
        yield 18

    def _react(self):
        """A finger found it: it is pleased, then goes back to what it was doing."""
        life = PLACES[self.place]["life"]
        if self._rest()[0] == "sleep":
            yield 1
        elif life == "desk":
            yield from self._greet()
        elif life == "work":
            if (yield from self._ready(("work", 2, 0))):
                self._show(("work", 2, 0))
                yield 30
        elif (yield from self._ready(("happy",))):
            self._show(("happy",))
            yield 34
        self._life = self._live()
        yield 1

    # -- the air --------------------------------------------------------

    def _set_air(self):
        kind, count = _AIR.get((self.place, self.variant), (None, 0))
        self._air_kind = kind
        while len(self._air) > count:
            self._air.pop()[0].delete()
        colors = _AIR_COLORS.get(kind, ())
        unit = max(self.h / 480, 0.5)
        for i in range(count):
            if i >= len(self._air):
                dot = lv.obj(self._air_layer)
                dot.remove_style_all()
                dot.remove_flag(lv.obj.FLAG.CLICKABLE)
                self._air.append([dot, 0.0, 0.0, 0.0, 0.0])
            item = self._air[i]
            dot = item[0]
            if kind == "snow":
                size = int((3 + i % 4) * unit)
                dot.set_size(size, size)
            elif kind == "firefly":
                size = int((5 + i % 3) * unit)
                dot.set_size(size, size)
            else:
                dot.set_size(int((8 + i % 4) * unit), int((4 + i % 2) * unit))
            dot.set_style_radius(lv.RADIUS_CIRCLE, 0)
            dot.set_style_bg_color(lv.color_hex(colors[i % 3]), 0)
            dot.set_style_bg_opa(255, 0)
            item[1] = self.random.next() * self.w
            item[2] = self.random.next() * self.h
            item[3] = 0.3 + self.random.next() * 0.7  # how fast this one goes
            item[4] = self.random.next() * 6.28
            if kind == "firefly":
                # low and to the right, where the picture has its own
                item[1] = self.w * (0.45 + 0.5 * self.random.next())
                item[2] = self.h * (0.45 + 0.45 * self.random.next())

    def _move_air(self):
        kind = self._air_kind
        if not kind:
            return
        t = self._ticks
        unit = self.h / 480
        for i, item in enumerate(self._air):
            dot, x, y, speed, phase = item
            if kind == "firefly":
                # a slow perch, and a glow that comes and goes
                turn = int(t * speed * 0.6 + phase * 10)
                x += _SIN[turn & 63] * 0.5 * unit
                y += _SIN[(turn * 2 + 16) & 63] * 0.3 * unit
                dot.set_style_bg_opa(int(150 + 100 * _SIN[(t * 2 + i * 9) & 63]), 0)
            else:
                fall = 1.6 if kind == "snow" else 1.1
                drift = 0.5 if kind == "snow" else 1.3
                y += fall * speed * unit
                x += (drift * speed - 0.9 * _SIN[(t + int(phase * 10)) & 63]) * unit
                if y > self.h:
                    y, x = -8.0, self.random.next() * self.w
                if x > self.w:
                    x = -8.0
            item[1], item[2] = x, y
            dot.set_pos(int(x), int(y))

    # -- from outside ---------------------------------------------------

    def tick(self, timer=None):
        """One step: part of a place or a pose drawn, a picture changed, the air moved."""
        t0 = time.ticks_us()
        self._ticks += 1
        self._first("first_tick_ms")
        loading = self._loader is not None
        if loading:
            try:
                next(self._loader)
            except StopIteration:
                self._loader = None
        else:
            if not self._quiet:
                self._work()
            if self._life is not None:
                if self._wait > 0:
                    self._wait -= 1
                else:
                    try:
                        self._wait = (next(self._life) or 1) - 1
                    except StopIteration:
                        self._life = self._live()
        self._move_air()
        spent = time.ticks_diff(time.ticks_us(), t0)
        longest = "tick_load_us" if loading else "tick_show_us"
        if spent > self.stats[longest]:
            self.stats[longest] = spent
        if spent > 150000 and not loading:
            self.stats["slow_ticks"] += 1
        if not loading and spent == self.stats["tick_show_us"]:
            self.stats["slowest"] = (self._step, self.pose)
        self._step = None

    def go(self, place=None, variant=None, view=None):
        """Show *place* (its first variant unless given), or another *view* of this one.

        Returns:
            False while an earlier change is still being drawn, and nothing happens.
        """
        if self._loader is not None:
            return False
        place = place or self.place
        if variant is None:
            variant = self.variant if place == self.place else PLACES[place]["variants"][0]
        self._asked = time.ticks_ms()
        self._loader = self._change(place, variant, view or self.view)
        return True

    def next_place(self):
        return self.go(ORDER[(ORDER.index(self.place) + 1) % len(ORDER)])

    def next_variant(self):
        variants = PLACES[self.place]["variants"]
        return self.go(variant=variants[(variants.index(self.variant) + 1) % len(variants)])

    def next_view(self):
        return self.go(view=VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)])

    def hit(self, x, y):
        """True when (*x*, *y*) on the screen is on the chameleon."""
        if self._shown is None:
            return False
        ox, oy = self._origin()
        left, top = ox + self._shown[2], oy + self._shown[3]
        header = self._shown[0].header
        return left <= x < left + header.w and top <= y < top + header.h

    def tap(self, x, y):
        """A finger at (*x*, *y*): True when it was on the chameleon, which answers."""
        if self._loader is not None or not self.hit(x, y):
            return False
        self._life = self._react()
        self._wait = 0
        self._quiet = False
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        return True

    def close(self):
        """Let go of every buffer, once the images are deleted or about to be."""
        self._loader = self._life = self._maker = None
        self._frames = {}
        self._order = []
        self._wanted = []
        self._docs = {}
        self._doc_order = []
        self._shown = self._made = self._loose = self._bug_frame = self.pose = None
        self._pool = {}
        self._pooled = 0
        self._bytes = 0
        self._air = []
