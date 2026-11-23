# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The SVG text Backline's views draw their art from, on a box's own screen
at 800x480 and 720x720: the floor view, then the desk view in its place
(`backline.app.Views`), back and forth, then a song in another meter.

Each size: the text is written once for each view's size and meter, so
switching views writes none (on a board, writing it took longer than
drawing it); each view's text is for its own size; another meter writes the
ring's text again, the same as written fresh, and the views show it; and
what the text keeps, after the floor's ring has shown many meters, stays
under a budget (`TEXT_BUDGET`) and holds no pixels.

    python tests/backline_text_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the text one way (``PLANTS``) and a check must
then fail.
"""

import sys

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
import svgio  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import app, art, floor  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline.desk import Desk  # noqa: E402

PLANTS = ("rewrite-every-show", "stale-meter", "one-size", "keep-pixels", "keep-every-meter")
SIZES = ((800, 480), (720, 720))
#: The most bytes the floor's and the desk face's text may keep together:
#: they kept 82 KB at 800x480 in 12/8, against the megabyte or more of
#: pixels drawn from it.
TEXT_BUDGET = 100 * 1024
#: Meters the floor's ring is shown in, one after another, before the
#: budget is checked: (steps, group).
METERS = ((4, 1), (3, 1), (6, 3), (12, 3), (5, 1), (7, 1), (9, 3), (2, 1))
BUILDERS = ("panel_top", "panel_ring", "panel_bottom", "segment_svg", "digit_svg", "glow_svg")
SWITCHES = 3
RESULTS = [0, 0]
WRITTEN = {}


def check(name, ok, detail=""):
    if ok:
        RESULTS[0] += 1
        print("ok   " + name)
    else:
        RESULTS[1] += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def _counted(name, fn):
    def counted(*args, **kwargs):
        WRITTEN[name] = WRITTEN.get(name, 0) + 1
        return fn(*args, **kwargs)
    return counted


def count_builders():
    """Count each call of the functions that write the art's text."""
    for name in BUILDERS:
        setattr(art, name, _counted(name, getattr(art, name)))


def written():
    """How many times the text was written since the last call."""
    n = sum(WRITTEN.values())
    WRITTEN.clear()
    return n


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "rewrite-every-show":
        old_show = floor.Floor.show

        def show(self):
            if self.hidden:
                self.texts = art.Texts(self.lay)
            old_show(self)
        floor.Floor.show = show
    elif name == "stale-meter":
        old_ring = art.Texts.ring

        def ring(self, steps, group):
            if self.meter is not None:
                steps, group = self.meter
            return old_ring(self, steps, group)
        art.Texts.ring = ring
    elif name == "one-size":
        made = []
        real = art.Texts

        def texts(lay):
            if not made:
                made.append(real(lay))
            return made[0]
        art.Texts = texts
    elif name == "keep-pixels":
        old_hide = floor.Floor.hide

        def hide(self):
            if not self.hidden:
                self.texts.pixels = self.pictures + self.ring_pictures
            old_hide(self)
        floor.Floor.hide = hide
    elif name == "keep-every-meter":
        old_ring = art.Texts.ring

        def ring(self, steps, group):
            if self.meter is not None and self.meter != (steps, group):
                old = self.ring(*self.meter)
                self.old = getattr(self, "old", []) + [[bytes(old[0])] + [bytes(t) for t in old[1]]]
            return old_ring(self, steps, group)
        art.Texts.ring = ring
    else:
        raise SystemExit("no such plant: %r" % name)


def held(x):
    """The bytes ``x`` keeps: text, and the pixels of any picture in it."""
    if isinstance(x, (bytes, bytearray, str, memoryview, svgio.Buffer)):
        return len(x)
    if isinstance(x, (list, tuple)):
        return sum(held(v) for v in x)
    if isinstance(x, dict):
        return sum(held(v) for v in x.values())
    if isinstance(x, art.Picture):
        return x.bytes
    return 0


def own_size(view):
    """Whether ``view``'s kept text is for its own size: its layout, and a
    panel whose head says its width and height."""
    t = view.texts
    if t.lay is not view.lay or t.meter is None:
        return False
    panel, _segments = t.ring(*t.meter)
    return bytes(panel[:art.HEAD_ROOM]) == art._room_head(view.lay.w, view.lay.h, 0)


def fresh(view):
    """Whether ``view``'s ring text is what its meter writes fresh."""
    lay, (steps, group) = view.lay, view.meter
    t = view.texts
    if t.meter != (steps, group) or len(view.segments) != steps:
        return False
    panel, segments = t.ring(steps, group)
    if bytes(panel) != bytes(art.panel_text(art.panel_svg(lay, steps, group), lay.w, lay.h)):
        return False
    return all(bytes(segments[b]) == art.segment_svg(lay, b, steps, group).encode() for b in range(steps))


def run_size(w, h):
    tag = "%dx%d" % (w, h)
    _headless.display(w, h)
    scr = lv.obj(None)
    lv.screen_load(scr)
    frames = [0]
    box = boxmod.Box(lambda: frames[0], song="rock", now_ms=lambda: 0)
    box.device._tele_ms = 0
    listener = box.device.add(local.serve())
    panel = hmilink.Panel(local.connect(listener))
    box.poll()
    panel.poll()
    desk_panels = []
    views = None

    def make_desk(on_switch):
        desk_panels.append(hmilink.Panel(local.connect(listener)))
        box.poll()
        desk_panels[-1].poll()
        return Desk(scr, (w, h), desk_panels[-1], on_switch=on_switch)

    def settle():
        for _ in range(3):
            box.poll()
            box.device._telemetry()
            views.floor.poll()
            if views.desk is not None:
                views.desk.poll()
            _headless.advance(30)
        _headless.refresh()

    def play():
        box.engine.gesture(0, "tap")
        for _ in range(40):
            box.service()
            frames[0] += 2048

    def switches():
        for _ in range(SWITCHES):
            views.show("desk")
            settle()
            views.show("floor")
            settle()

    try:
        views = app.Views(lambda on_switch: floor.Floor(scr, (w, h), panel, on_switch=on_switch), make_desk)
        settle()
        play()
        settle()
        views.show("desk")       # the desk's face writes its own text, once
        settle()
        views.show("floor")
        settle()
        face = views.desk.perform.floor
        written()
        switches()
        n = written()
        check(tag + ": %d switches between the views write no text" % (2 * SWITCHES), n == 0,
              "the text was written %d times" % n)
        check(tag + ": the floor's text is for its size", own_size(views.floor))
        check(tag + ": the desk face's text is for its size", own_size(face))

        box.command("stop", {})
        settle()
        slow = [i for i, (_n, p) in enumerate(box.songs) if "ballad_68" in p][0]
        box.command("song", {"index": slow})     # 12/8, while the desk hides
        settle()
        play()
        settle()
        check(tag + ": another meter writes the floor's ring again, as fresh",
              views.floor.meter == (12, 3) and fresh(views.floor), "the floor shows %r" % (views.floor.meter,))
        views.show("desk")
        settle()
        check(tag + ": the desk face writes its ring for the meter too", face.meter == (12, 3) and fresh(face),
              "the face shows %r" % (face.meter,))
        views.show("floor")
        settle()
        written()
        switches()
        n = written()
        check(tag + ": in the new meter, %d switches write no text" % (2 * SWITCHES), n == 0,
              "the text was written %d times" % n)

        for steps, group in METERS:
            views.floor._ring(steps, group)
            settle()
        views.floor._ring(12, 3)
        views.show("desk")
        settle()
        views.show("floor")
        settle()
        kept = held(views.floor.texts.__dict__) + held(face.texts.__dict__)
        print("     %s: the views keep %d bytes of text" % (tag, kept))
        check(tag + ": the views keep under %d KB of text, after %d meters" % (TEXT_BUDGET // 1024, len(METERS)),
              kept < TEXT_BUDGET, "%d bytes" % kept)
    except Exception as e:  # noqa: BLE001 - a view that won't draw fails the contract
        check(tag + ": the views draw", False, "%s: %s" % (type(e).__name__, e))
    scr.delete()
    for p in desk_panels + [panel]:
        p.close()
    box.close()


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    count_builders()
    plant(p)
    print("on " + sys.implementation.name)
    for w, h in SIZES:
        run_size(w, h)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
