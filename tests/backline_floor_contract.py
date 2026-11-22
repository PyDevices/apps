# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's floor view on real LVGL with no window, at 320x240, 480x320
and 800x480: it fits the screen, lights one more segment of the ring each
beat and redraws little else, shows the part and the next one, lights a
pedal's lamp while it is down, and a touch on a lamp reaches the device.

    python tests/backline_floor_contract.py [--plant=NAME]

The view draws from an hmilink panel over the ``local`` transport; the
device here is a stand-in whose telemetry the check writes. Needs LVGL,
svgio and hmilink. ``--plant=NAME`` breaks the view one way (``PLANTS``)
and a check must then fail.
"""

import sys

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import art, floor  # noqa: E402

PLANTS = ("no-beat", "full-redraw", "deaf-lamp", "overflow", "stale-part", "dark-lamp")
SIZES = ((320, 240), (480, 320), (800, 480))
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
    if name == "no-beat":
        old = floor.Floor._tele

        def tele(self, values):
            values = dict(values)
            values["beat"] = 0
            old(self, values)
        floor.Floor._tele = tele
    elif name == "full-redraw":
        old = floor.Floor._tele

        def tele(self, values):
            old(self, values)
            self.base.invalidate()
        floor.Floor._tele = tele
    elif name == "deaf-lamp":
        floor.Floor.pedal = lambda self, which, down: None
    elif name == "overflow":
        old = art.Layout.__init__

        def init(self, w, h):
            old(self, w, h)
            x, y, cw, ch = self.col
            self.col = (x, y, cw + 120, ch)
        art.Layout.__init__ = init
    elif name == "stale-part":
        old = floor.Floor._set

        def _set(self, key, value, fn):
            if key == "part" and key in self.shown:
                return False
            return old(self, key, value, fn)
        floor.Floor._set = _set
    elif name == "dark-lamp":
        floor.PEDAL_COLORS = (0x000000, 0x000000)
        art.glow_svg = (lambda g: lambda r, c: g(r, 0x000000))(art.glow_svg)
    else:
        raise SystemExit("no such plant: %r" % name)


class Stand(hmilink.Model):
    """A device whose telemetry is what the check says, and which remembers commands."""

    def __init__(self):
        hmilink.Model.__init__(self, {"name": "Straight Rock", "tempo": 118.0})
        self.values = {}
        self.commands = []

    def telemetry(self):
        return dict(self.values)

    def command(self, name, args):
        self.commands.append((name, dict(args)))
        return None


def tele(**kw):
    base = {"playing": True, "song": "Straight Rock", "tempo": 118.0, "kit": "Rhythm 909", "role": "main",
            "part": "Main 1", "next": "", "next_role": "", "bar": 1, "bars": 2, "beat": 1,
            "pedals": ["up", "up"]}
    base.update(kw)
    return base


def pixel(frame, w, x, y):
    i = 2 * (int(y) * w + int(x))
    v = frame[i] | (frame[i + 1] << 8)
    return ((v >> 11) & 31) * 8, ((v >> 5) & 63) * 4, (v & 31) * 8


def bright(rgb):
    return sum(rgb)


def inside(obj, w, h):
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1 >= 0 and a.y1 >= 0 and a.x2 < w and a.y2 < h


def walk(obj):
    out = [obj]
    for i in range(obj.get_child_count()):
        out.extend(walk(obj.get_child(i)))
    return out


def run_size(w, h):
    tag = "%dx%d" % (w, h)
    frame = _headless.display(w, h)
    _headless.pointer().set_display(_headless._state["display"])
    scr = lv.obj(None)
    lv.screen_load(scr)
    scr.set_size(w, h)
    model = Stand()
    device = hmilink.Device(model, telemetry_hz=0)
    panel = hmilink.Panel(local.connect(device.add(local.serve())))
    device.poll()
    panel.poll()
    view = floor.Floor(scr, (w, h), panel)

    def show(**kw):
        model.values = tele(**kw)
        device._telemetry()
        view.poll()
        _headless.advance(5)
        return _headless.refresh()

    show(beat=1)
    _headless.refresh()
    out = [o for o in walk(view.base) if not o.has_flag(lv.obj.FLAG.HIDDEN) and not inside(o, w, h)]
    where = []
    for o in out:
        a = lv.area_t()
        o.get_coords(a)
        where.append((a.x1, a.y1, a.x2, a.y2))
    check(tag + ": everything fits on the screen", not out, "outside: %r" % where)
    held = view.bytes()
    check(tag + ": the art holds under four screens' worth", held < 4 * w * h * 3, "%d bytes" % held)
    lay = view.lay
    probes = []
    for b in range(4):
        a0, a1 = art.beat_span(b)
        import math

        am = math.radians((a0 + a1) / 2)
        mid = (lay.beat_in + lay.beat_out) / 2
        probes.append((lay.cx + mid * math.cos(am), lay.cy + mid * math.sin(am)))
    dark = bright(pixel(frame, w, *probes[3]))
    ok = True
    redrawn = []
    for beat in (1, 2, 3, 4):
        redrawn.append(show(beat=beat))
        lit = [bright(pixel(frame, w, x, y)) > dark + 150 for x, y in probes]
        if lit != [i < beat for i in range(4)]:
            ok = False
            print("     beat %d lit %r" % (beat, lit))
    check(tag + ": each beat lights one more segment of the ring", ok)
    worst = max(redrawn[1:])
    check(tag + ": a beat redraws under a third of the screen", worst < w * h // 3,
          "%d of %d pixels" % (worst, w * h))
    show(beat=2, role="fill", part="Fill 1", next="Main 1", next_role="main")
    check(tag + ": the part and the next one are shown", view.part.get_text() == "FILL 1" and
          "MAIN 1" in view.chip_text.get_text(), repr((view.part.get_text(), view.chip_text.get_text())))
    x, y = lay.pedal_x[0], lay.pedal_y
    before = bright(pixel(frame, w, x, y - lay.pedal_r * 0.5))
    show(beat=2, pedals=["down", "up"])
    after = bright(pixel(frame, w, x, y - lay.pedal_r * 0.5))
    check(tag + ": pedal A's lamp lights while it is down", after > before + 150, "%d -> %d" % (before, after))
    show(beat=2, pedals=["up", "up"])
    model.commands = []
    for _ in range(3):
        _headless.touch(int(lay.pedal_x[1]), int(lay.pedal_y), True, 40)
    for _ in range(3):
        _headless.touch(int(lay.pedal_x[1]), int(lay.pedal_y), False, 40)
    device.poll()
    want = [("pedal", {"pedal": 1, "down": True}), ("pedal", {"pedal": 1, "down": False})]
    check(tag + ": a touch on lamp B presses pedal B", model.commands == want, repr(model.commands))
    scr.delete()
    device.close()


def main():
    argv = sys.argv[1:]
    p = None
    for a in argv:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    for w, h in SIZES:
        run_size(w, h)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
