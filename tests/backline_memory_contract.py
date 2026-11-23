# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What Backline's views hold, on a box's own screen at 800x480 and 720x720:
the floor view, then the desk view in its place (`backline.app.Views`) with
its prompt sheet open, then the floor again, a few times over.

Each size: the floor's art holds under four bytes a screen pixel, and no
one picture needs a block bigger than an eighth of a screen at two bytes a
pixel, so a heap in pieces still has room for each; while the desk shows,
the floor holds no art, and while the floor shows, the desk's face holds
none; and the floor drawn again looks as it did, pixel for pixel. On
MicroPython, the heap the views take on top of the box's own, with the
desk and its prompt sheet open and after going back and forth, stays under
a budget (`HEAP_BUDGET`); CPython has no heap to read, so that one skips.

    python tests/backline_memory_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the views one way (``PLANTS``) and a check must
then fail.
"""

import gc
import sys
from binascii import crc32

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import app, art, floor  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline.desk import Desk  # noqa: E402

PLANTS = ("keep-floor", "keep-face", "alpha-panel", "whole-panel", "all-digits", "stale-return")
SIZES = ((800, 480), (720, 720))
#: The most heap the views may take on top of the box's own, in bytes a
#: screen pixel: at 800x480 they took 8.2 a pixel when the desk drew beside
#: the floor, and 4.6 once one view's art was held at a time.
HEAP_BUDGET = 6.0
RESULTS = [0, 0]


def check(name, ok, detail=""):
    if ok:
        RESULTS[0] += 1
        print("ok   " + name)
    else:
        RESULTS[1] += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "keep-floor":
        floor.Floor.hide = lambda self: self.base.add_flag(lv.obj.FLAG.HIDDEN)
    elif name == "keep-face":
        Desk.hide = lambda self: self.base.add_flag(lv.obj.FLAG.HIDDEN)
    elif name == "alpha-panel":
        def bands(parent, svg, width, height, decoder=None):
            return [art.Picture(parent, svg, width, height, decoder=decoder)]
        art.bands = bands
    elif name == "whole-panel":
        def bands(parent, svg, width, height, decoder=None):
            return [art.Picture(parent, svg, width, height, alpha=False, decoder=decoder)]
        art.bands = bands
    elif name == "all-digits":
        old = floor.Floor._draw

        def draw(self):
            old(self)
            for ch in "0123456789- ":
                self._big(ch)
        floor.Floor._draw = draw
    elif name == "stale-return":
        old = floor.Floor.show

        def show(self):
            old(self)
            self.beat_digit.set_src(self._big("-").dsc)
        floor.Floor.show = show
    else:
        raise SystemExit("no such plant: %r" % name)


def heap():
    """The heap in use now, after a collection; None where it can't be read."""
    gc.collect()
    fn = getattr(gc, "mem_alloc", None)
    return fn() if fn is not None else None


def biggest(view):
    """The bytes of the biggest picture ``view`` holds."""
    return max([p.bytes for p in view.pictures + view.ring_pictures] or [0])


def run_size(w, h):
    tag = "%dx%d" % (w, h)
    frame = _headless.display(w, h)
    scr = lv.obj(None)
    lv.screen_load(scr)
    frames = [0]
    box = boxmod.Box(lambda: frames[0], song="rock", now_ms=lambda: 0)
    box.device._tele_ms = 0
    listener = box.device.add(local.serve())
    panel = hmilink.Panel(local.connect(listener))
    box.poll()
    panel.poll()
    base = heap()
    desk_panels = []

    def make_desk(on_switch):
        desk_panels.append(hmilink.Panel(local.connect(listener)))
        box.poll()
        desk_panels[-1].poll()
        return Desk(scr, (w, h), desk_panels[-1], on_switch=on_switch)

    views = app.Views(lambda on_switch: floor.Floor(scr, (w, h), panel, on_switch=on_switch), make_desk)
    box.engine.gesture(0, "tap")
    for _ in range(40):          # into the song, so the ring and the digits are lit
        box.service()
        frames[0] += 2048
    peak = [0]

    def settle():
        for _ in range(3):
            box.poll()
            box.device._telemetry()
            views.floor.poll()
            if views.desk is not None:
                views.desk.poll()
            _headless.advance(30)
        _headless.refresh()
        used = heap()
        if used is not None and base is not None:
            peak[0] = max(peak[0], used - base)

    settle()
    held = views.floor.bytes()
    check(tag + ": the floor's art holds under four bytes a screen pixel", held < 4 * w * h,
          "%d bytes, %.2f a pixel" % (held, held / float(w * h)))
    most = biggest(views.floor)
    check(tag + ": no picture of the floor needs a block over an eighth of a screen", most <= w * h // 4,
          "%d bytes in one picture" % most)
    before = crc32(frame)        # not a copy: that would be a screen's worth of heap
    for _ in range(3):
        views.show("desk")
        settle()
        check(tag + ": while the desk shows, the floor holds no art", views.floor.bytes() == 0,
              "%d bytes" % views.floor.bytes())
        face = views.desk.perform.floor
        check(tag + ": no picture of the desk's face needs a block over an eighth of a screen",
              biggest(face) <= w * h // 4, "%d bytes in one picture" % biggest(face))
        views.desk.toggle_prompt()
        settle()
        views.desk.toggle_prompt()
        views.show("floor")
        settle()
        check(tag + ": while the floor shows, the desk's face holds no art", face.bytes() == 0,
              "%d bytes" % face.bytes())
    check(tag + ": the floor drawn again looks as it did", crc32(frame) == before)
    if base is None:
        print("skip %s: the heap the views take (this Python has no heap to read)" % tag)
    else:
        print("     %s: the views took %d bytes of heap at most, the floor's art %d" % (tag, peak[0], held))
        check(tag + ": the views take under %.1f bytes of heap a screen pixel" % HEAP_BUDGET,
              peak[0] < HEAP_BUDGET * w * h, "%d bytes at most, %.2f a pixel" % (peak[0], peak[0] / float(w * h)))
    scr.delete()
    for p in desk_panels + [panel]:
        p.close()
    box.close()


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    print("on " + sys.implementation.name)
    for w, h in SIZES:
        run_size(w, h)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
