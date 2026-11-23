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
none; and the floor drawn again looks as it did, pixel for pixel.

The views keep their pictures in a cache (`art.Cache`) in a folder of its
own under ``--tmp``, as the app does in its data folder: the first time a
view shows it draws them, and every time after it reads them all back and
draws none. The cache keeps nothing in memory: a view hiding gives the
heap back its art's bytes.

On MicroPython, the heap the views take on top of the box's own, with the
desk and its prompt sheet open and after going back and forth, stays under
a budget (`HEAP_BUDGET`). CPython reads its heap with tracemalloc, which
sees the pictures but not what LVGL holds, so there it checks instead that
a view hiding gives its art's bytes back, and that nothing reachable from
art.py, its cache included, holds pixels.

    python tests/backline_memory_contract.py [--plant=NAME] [--tmp FOLDER]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the views one way (``PLANTS``) and a check must
then fail.
"""

import gc
import os
import sys
from binascii import crc32

try:
    import tracemalloc
except ImportError:
    tracemalloc = None

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

PLANTS = ("keep-floor", "keep-face", "alpha-panel", "whole-panel", "all-digits", "stale-return", "keep-both",
          "keep-nothing")
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
        def bands(parent, svg, width, height):
            return [art.Picture(parent, svg, width, height)]
        art.bands = bands
    elif name == "whole-panel":
        def bands(parent, svg, width, height):
            return [art.Picture(parent, svg, width, height, alpha=False)]
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
    elif name == "keep-both":
        # A cache that holds on to every picture it has read or drawn.
        held = {}
        load, save = art.Cache.load, art.Cache.save

        def keep_load(self, path, buf):
            if path in held:
                buf[:] = held[path]
                self.hits += 1
                return True
            return load(self, path, buf)

        def keep_save(self, path, buf):
            held[path] = bytes(buf)
            return save(self, path, buf)
        art.Cache.load, art.Cache.save = keep_load, keep_save
    elif name == "keep-nothing":
        art.Cache.save = lambda self, path, buf: False
    else:
        raise SystemExit("no such plant: %r" % name)


def heap():
    """The heap in use now, after a collection; None where it can't be read."""
    gc.collect()
    fn = getattr(gc, "mem_alloc", None)
    return fn() if fn is not None else None


def python_heap():
    """What the heap holds now: MicroPython's, or on CPython what
    tracemalloc has seen allocated (the pictures, not LVGL's own)."""
    used = heap()
    if used is None and tracemalloc is not None:
        gc.collect()
        used = tracemalloc.get_traced_memory()[0]
    return used


def art_reach():
    """On CPython, the bytes of every buffer reachable from art.py: its
    module, its classes and their functions' closures, and its cache. The
    pictures belong to the views, so this is what a cache keeps in memory.
    None on MicroPython, whose heap budget sees that."""
    get = getattr(gc, "get_referents", None)
    if get is None:
        return None
    import types

    seen = set()
    total = 0
    stack = [art]
    while stack:
        o = stack.pop()
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, (bytes, bytearray)):
            total += len(o)
        elif isinstance(o, memoryview):
            total += o.nbytes
        elif isinstance(o, types.ModuleType):
            if o is art:
                stack.extend(vars(o).values())
        elif isinstance(o, types.FunctionType):
            stack.extend(c.cell_contents for c in o.__closure__ or ())
            stack.extend(o.__defaults__ or ())
        elif isinstance(o, type):
            if o.__module__ == art.__name__:
                stack.extend(vars(o).values())
        else:
            stack.extend(get(o))
    return total


def art_held(tag, view):
    """Check art.py holds no pixels of its own while ``view`` shows."""
    now = art_reach()
    if now is not None:
        check(tag + ": while the " + view + " shows, art.py and its cache hold no pixels", now < 4096,
              "%d bytes" % now)


def gives_back(view):
    """How many bytes the heap gets back when ``view`` hides (None where
    it can't be read). The view stays hidden: showing the other view hides
    it again, which does nothing the second time."""
    before = python_heap()
    view.hide()
    after = python_heap()
    return None if before is None else before - after


def empty_folder(path):
    """``path``, made if missing, with nothing in it."""
    try:
        os.mkdir(path)
    except OSError:
        pass
    for name in os.listdir(path):
        os.remove(path + "/" + name)
    return path


def biggest(view):
    """The bytes of the biggest picture ``view`` holds."""
    return max([p.bytes for p in view.pictures + view.ring_pictures] or [0])


def run_size(w, h, tmp):
    tag = "%dx%d" % (w, h)
    kept = art.use_cache(empty_folder(tmp + "/backline-art-" + tag))
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
    drawn = kept.misses
    for rnd in range(3):
        given = gives_back(views.floor)
        check(tag + ": the floor hiding gives its art's bytes back to the heap",
              given is None or given >= held * 0.9, "%s of %d bytes" % (given, held))
        views.show("desk")
        settle()
        check(tag + ": while the desk shows, the floor holds no art", views.floor.bytes() == 0,
              "%d bytes" % views.floor.bytes())
        face = views.desk.perform.floor
        check(tag + ": no picture of the desk's face needs a block over an eighth of a screen",
              biggest(face) <= w * h // 4, "%d bytes in one picture" % biggest(face))
        if rnd == 0:
            drawn = kept.misses
        art_held(tag, "desk")
        views.desk.toggle_prompt()
        settle()
        views.desk.toggle_prompt()
        face_held = face.bytes()
        given = gives_back(views.desk)
        check(tag + ": the desk hiding gives its face's art's bytes back to the heap",
              given is None or given >= face_held * 0.9, "%s of %d bytes" % (given, face_held))
        views.show("floor")
        settle()
        art_held(tag, "floor")
        check(tag + ": while the floor shows, the desk's face holds no art", face.bytes() == 0,
              "%d bytes" % face.bytes())
    check(tag + ": the floor drawn again looks as it did", crc32(frame) == before)
    check(tag + ": once each view has shown, each shows again with every picture read back, none drawn",
          kept.misses == drawn and kept.hits > 0 and kept.rebuilt == 0,
          "%d drawn after the first round, %d read, %d wrong" % (kept.misses - drawn, kept.hits, kept.rebuilt))
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
    art.use_cache(None)


def main():
    p = None
    tmp = "/tmp"
    argv = sys.argv[1:]
    while argv:
        a = argv.pop(0)
        if a.startswith("--plant="):
            p = a[len("--plant="):]
        elif a == "--tmp":
            tmp = argv.pop(0)
    plant(p)
    print("on " + sys.implementation.name)
    if heap() is None and tracemalloc is not None:
        tracemalloc.start()
    for w, h in SIZES:
        run_size(w, h, tmp)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
