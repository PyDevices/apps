# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Put a place and the chameleon on an LVGL screen, and keep them moving.

A `Stage` draws the place once, in bands, into one RGB565 buffer behind an
``lv.image``. The chameleon is a second image over it: each pose is drawn by
svgio into its own RGB565A8 buffer the first time it is wanted and kept, so a
walk, a blink or a wave is a change of picture and a move, which LVGL blends.
Everything is a step in one timer tick, so nothing holds the screen for long.
"""

import gc
import time

import lvgl as lv
import svgio

from . import chameleon_props, chameleon_shift, chameleon_views, mascot_chameleon, scene_bench, scene_coast, scene_desk
from .vec import Doc, at

TICK_MS = 40
SCENE_W, SCENE_H = 800, 480
NAVY = 0x0B2A4A
BANDS = 4  # the place is drawn in this many strips, one a tick
CACHE_BYTES = 6 * 1024 * 1024  # poses kept, beside the one on screen and the one just drawn
STRIDE = 63.3  # how far a full turn of the walk carries the body, in its own units

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
# walk, and what it does there.
PLACES = {
    "coast": {
        "variants": ("summer", "autumn", "winter", "night", "spring"),
        "build": _coast,
        "schemes": {"spring": "blossom", "summer": "leaf", "autumn": "sunset", "winter": "snow", "night": "night"},
        "at": (322, 404, 0.6),
        "walk": (-36, 44),
        "life": "stroll",
    },
    "bench": {
        "variants": ("board", "brand", "copper", "leaf"),
        "build": _bench,
        "schemes": None,
        "at": (scene_bench.HUE_X, scene_bench.HUE_Y, scene_bench.HUE_SCALE),
        "walk": None,
        "life": "work",
    },
    "desk": {
        "variants": ("day", "evening", "night"),
        "build": _desk,
        "schemes": {"day": "leaf", "evening": "sunset", "night": "night"},
        "at": scene_desk.SPOTS["books"],
        "walk": (-22, 26),
        "life": "desk",
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
        return chameleon_props.hold(doc, "iron", lean=80, look=look, look_far=far, blink=spec[2], colors=scheme, perch=None, nod=nod), _HOLD
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
        #: Microseconds spent building SVG text, collecting garbage before a
        #: parse, parsing and drawing; how many poses and bands were drawn and
        #: the slowest of each; and the most bytes of picture ever held.
        self.stats = {"text": 0, "tidy": 0, "parse": 0, "draw": 0, "poses": 0, "bands": 0, "band_us": 0, "pose_us": 0, "peak": 0}
        self._decoder = svgio.SvgDecoder()
        self._frames = {}  # (spec, flip, scheme) -> (descriptor, buffer, x offset, y offset)
        self._order = []  # the same keys, least lately used first
        self._bytes = 0
        self._shown = None
        self._life = None
        self._wait = 0
        self._facing = 1
        self._walked = 0.0  # along the perch, in the chameleon's units
        self._air = []
        self._air_kind = None
        self._ticks = 0
        #: True while a place, a variant or a view is being changed.
        self.busy = True

        # the place: one buffer, navy until its first band lands
        self._ground = bytearray(self.w * (self.h + 2) * 2)
        c = ((NAVY >> 8) & 0xF800) | ((NAVY >> 5) & 0x07E0) | ((NAVY >> 3) & 0x1F)
        row = bytes((c & 255, c >> 8)) * self.w
        rows = memoryview(self._ground)
        for y in range(self.h + 2):
            rows[y * self.w * 2 : (y + 1) * self.w * 2] = row
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
        total = len(self._ground) + self._bytes
        if self._bug_frame:
            total += len(self._bug_frame[1])
        return total

    def _tidy(self):
        # MicroPython looks for free memory from the first gap on, past everything
        # used or dropped since the last collection. svgio's parse asks hundreds of
        # times, so collecting first makes it several times faster.
        t0 = time.ticks_us()
        gc.collect()
        self.stats["tidy"] += time.ticks_diff(time.ticks_us(), t0)

    def _sprite(self, text, width):
        """SVG text drawn *width* pixels wide into one RGB565A8 buffer."""
        text = text.encode()
        self._tidy()
        t0 = time.ticks_us()
        w, h = self._decoder.open(text, width=max(2, width))
        t1 = time.ticks_us()
        data = bytearray(w * h * 3)
        planes = memoryview(data)
        self._decoder.decode(planes[: w * h * 2], planes[w * h * 2 :])
        self.stats["parse"] += time.ticks_diff(t1, t0)
        self.stats["draw"] += time.ticks_diff(time.ticks_us(), t1)
        return self._descriptor(data, w, h, lv.COLOR_FORMAT.RGB565A8), data, w, h

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

    def _frame(self, spec, scheme=None, keep=True):
        """The pose *spec* as a picture, drawn now if it hasn't been."""
        scheme = scheme or self.scheme
        flip = self._facing < 0
        key = (spec, flip, scheme)
        frame = self._frames.get(key)
        if frame is not None:
            self._order.remove(key)
            self._order.append(key)
            return frame
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
        text = doc.svg((rx, ry, rw, rh))
        self.stats["text"] += time.ticks_diff(time.ticks_us(), t0)
        dsc, data, w, h = self._sprite(text, int(rw * k * s + 0.5))
        self.stats["poses"] += 1
        self.stats["pose_us"] = max(self.stats["pose_us"], time.ticks_diff(time.ticks_us(), t0))
        frame = (dsc, data, round(rx * k * s), round(ry * k * s))
        if keep:
            self._frames[key] = frame
            self._order.append(key)
            self._bytes += len(data)
            while self._bytes > CACHE_BYTES and len(self._order) > 2:
                old = self._order[0]
                if self._frames[old] is self._shown:
                    old = self._order[1]
                self._drop(old)
        self.stats["peak"] = max(self.stats["peak"], self.held_bytes() + (0 if keep else len(data)))
        return frame

    def _drop(self, key):
        frame = self._frames.pop(key)
        self._order.remove(key)
        self._bytes -= len(frame[1])
        # LVGL may remember a picture by its address, which the next one could be given
        lv.image.cache_drop(frame[0])
        lv.image.header_cache_drop(frame[0])

    def _forget(self, keep_scheme=None):
        """Drop the kept poses, all of them or all but one scheme's."""
        for key in list(self._order):
            if self._frames[key] is self._shown:
                continue
            if keep_scheme is None or key[2] != keep_scheme:
                self._drop(key)

    def _show(self, spec, scheme=None, keep=True):
        frame = self._frame(spec, scheme, keep)
        self._shown = frame
        self.hue.set_src(frame[0])
        self._place_hue()
        self.hue.remove_flag(lv.obj.FLAG.HIDDEN)

    def _place_hue(self):
        if self._shown is None:
            return
        ox, oy = self._origin()
        self.hue.set_pos(round(ox) + self._shown[2], round(oy) + self._shown[3])

    # -- the place ------------------------------------------------------

    def _paint(self):
        """Draw the place into its buffer, a band a step, top to bottom."""
        t0 = time.ticks_us()
        doc = Doc()
        PLACES[self.place]["build"](doc, self.variant)
        vx, vy, vw, vh = self._rect
        s = self.w / vw
        self.stats["text"] += time.ticks_diff(time.ticks_us(), t0)
        yield
        for i in range(BANDS):
            y0, y1 = i * self.h // BANDS, (i + 1) * self.h // BANDS
            t0 = time.ticks_us()
            text = doc.svg((vx, vy + y0 / s, vw, (y1 - y0) / s))
            text = text.encode()
            t1 = time.ticks_us()
            self._tidy()
            self.stats["text"] += time.ticks_diff(t1, t0)
            t1 = time.ticks_us()
            self._decoder.open(text, width=self.w)
            t2 = time.ticks_us()
            self._decoder.decode(self._ground, x=0, y=y0, stride=self.w)
            t3 = time.ticks_us()
            self.stats["parse"] += time.ticks_diff(t2, t1)
            self.stats["draw"] += time.ticks_diff(t3, t2)
            self.stats["band_us"] = max(self.stats["band_us"], time.ticks_diff(t3, t0))
            self.stats["bands"] += 1
            self.ground.invalidate()
            yield
        self._painted = (self.place, self._ground_key(), self.view)

    def _ground_key(self):
        # the bench is the same bench whatever colours the chameleon wears
        return self.variant if PLACES[self.place]["schemes"] else None

    def _rest(self):
        """The pose it comes back to in this place."""
        life = PLACES[self.place]["life"]
        if life == "work":
            return ("work", 0, 0)
        if life == "desk" and self.variant == "night":
            return ("sleep",)
        return ("stand", 0, 0)

    def _change(self, place, variant, view):
        """Go to a place, a variant of it and a view: the steps, one a tick."""
        self.busy = True
        self._life = None
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        old_scheme = self.scheme
        schemes = PLACES[place]["schemes"]
        new_scheme = schemes[variant] if schemes else variant
        moved = place != self.place or view != self.view
        was_asleep = self.place is not None and self._rest() == ("sleep",)
        if moved:
            # somewhere else, or seen from somewhere else: it leaves, and comes back there
            self.hue.add_flag(lv.obj.FLAG.HIDDEN)
            self._shown = None
            self._forget()
            self._bug_frame = None
            self._walked = 0.0
            self._facing = 1
        self.place, self.variant, self.view = place, variant, view
        self._rect = self._fit(place, view)
        self._set_air()
        painting = None
        if self._painted != (place, self._ground_key(), view):
            painting = self._paint()
        rest = self._rest()
        blends = []
        if not moved and old_scheme and old_scheme != new_scheme and rest[0] != "sleep" and not was_asleep:
            blends = [chameleon_shift.between(old_scheme, new_scheme, t) for t in (0.25, 0.5, 0.75)]
        if old_scheme != new_scheme:
            # nothing drawn in the old colours will be wanted again
            self._forget()
        # the new colours come over it while the place is redrawn around it
        while painting is not None or blends:
            if blends:
                self._show(rest, blends.pop(0), keep=False)
                yield
                yield
            if painting is not None:
                try:
                    next(painting)
                except StopIteration:
                    painting = None
                yield
        for name in list(mascot_chameleon.COLORS):
            if ">" in name:
                del mascot_chameleon.COLORS[name]
        self.scheme = new_scheme
        self._forget(new_scheme)
        self._show(rest)
        self.busy = False
        self._life = self._live()
        self._wait = 6

    # -- what it does ---------------------------------------------------

    def _live(self):
        """Its life in this place: one thing after another, for ever."""
        life = PLACES[self.place]["life"]
        rest = self._rest()
        can_walk = PLACES[self.place]["walk"] is not None and self.view == "wide" and rest[0] == "stand"
        while True:
            self._show(rest)
            yield 12 + self.random.below(30)
            if self.cues:
                what = self.cues.pop(0)
            else:
                what = _CHOICES[self.random.below(len(_CHOICES))]
            if rest[0] == "sleep":
                continue
            if what == "blink":
                self._show((rest[0], rest[1], 1))
                yield 3
            elif what == "look":
                if life == "work":
                    self._show(("work", 1 + self.random.below(2), 0))
                else:
                    self._show(("stand", 1 + self.random.below(len(_LOOKS) - 1), 0))
                yield 20 + self.random.below(25)
            elif what == "stroll" and can_walk:
                yield from self._stroll()
            elif what == "tongue" and rest[0] == "stand" and self.view != "close" and self._facing > 0:
                yield from self._catch()
            elif what == "turn" and life == "desk":
                yield from self._greet()
            elif what == "hold" and rest[0] == "stand" and self._facing > 0:
                prop = _HELD[self.random.below(len(_HELD))]
                self._show(("hold", prop, 0))
                yield 30
                self._show(("hold", prop, 1))
                yield 45

    def _stroll(self):
        """A walk to the other end of the perch."""
        low, high = PLACES[self.place]["walk"]
        goal = high if self._walked < (low + high) / 2 else low
        facing = 1 if goal > self._walked else -1
        if facing != self._facing:
            self._facing = facing
            self._show(("stand", 0, 0))
            yield 6
        # the walk's pictures, one a tick, before the first step
        for n in range(8):
            self._frame(("walk", n))
            yield 1
        phase = 0
        per_tick = STRIDE / 8 / 3  # three ticks a picture, eight pictures a stride
        while (goal - self._walked) * facing > 0:
            self._show(("walk", (phase // 3) % 8))
            self._walked += per_tick * facing
            self._place_hue()
            phase += 1
            yield 1
        self._show(("stand", 0, 0))
        yield 8

    def _catch(self):
        """A bug drifts in ahead of it, and the tongue takes it."""
        x, y, k = PLACES[self.place]["at"]
        s = self.w / self._rect[2]
        if self._bug_frame is None:
            doc = Doc()
            doc.add(mascot_chameleon._bug(0, 0, 1.4))
            self._bug_frame = self._sprite(doc.svg((-30, -30, 60, 60)), int(60 * k * s + 0.5))
            self.bug.set_src(self._bug_frame[0])
        half = self._bug_frame[2] // 2
        ox, oy = self._origin()
        bx = ox + (_BUG[0] + 4) * k * s
        by = oy + (_BUG[1] + 22 + 4) * k * s
        self.bug.remove_flag(lv.obj.FLAG.HIDDEN)
        for i in range(24, -1, -1):
            # it wanders in from up and to the right
            wobble = ((i * 7) % 9 - 4) * (i / 24)
            self.bug.set_pos(int(bx + i * 5 * s + wobble) - half, int(by - i * 3.2 * s + wobble * 2) - half)
            if i == 14:
                self._show(("aim",))
            elif i == 8:
                self._frame(("tongue", 0.5))
            elif i == 4:
                self._frame(("tongue", 1))
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
        yield 22

    def _greet(self):
        """It turns to face you, waves, and turns back."""
        self._show(("front", 0, 0))
        yield 10
        self._show(("front", 1, 0))
        yield 26
        self._show(("front", 1, 1))
        yield 3
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
            self._show(("work", 2, 0))
            yield 30
        else:
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
                # a slow wander, and a glow that comes and goes
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
        """One step: a band or a pose drawn, a picture changed, the air moved."""
        self._ticks += 1
        if self._loader is not None:
            try:
                next(self._loader)
            except StopIteration:
                self._loader = None
        elif self._life is not None:
            if self._wait > 0:
                self._wait -= 1
            else:
                try:
                    self._wait = (next(self._life) or 1) - 1
                except StopIteration:
                    self._life = self._live()
        self._move_air()

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
        self.bug.add_flag(lv.obj.FLAG.HIDDEN)
        return True

    def close(self):
        """Let go of every buffer, once the images are deleted or about to be."""
        self._loader = self._life = None
        self._frames = {}
        self._order = []
        self._shown = self._bug_frame = None
        self._bytes = 0
        self._air = []
