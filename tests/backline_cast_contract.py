# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's cast desk on real LVGL with no window and no receiver: the
desk view drawn at 1280x720 on a display of its own, its frames handed to a
stand-in for a cast while a song plays.

The box has its own small screen, as it does in the app, and it stays the
display new screens go to. The cast's frames show the desk, keep coming
while the song plays but no faster than the cast's frame rate, and the
song-form strip's playhead moves between two of them; a tempo change made
from another panel reaches the cast. Closing it ends the cast and leaves
the box. The receiver settings (``remote.cast_target``) read each kind
and refuse what isn't one.

    python tests/backline_cast_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the cast one way (``PLANTS``) and a check must
then fail.
"""

import os
import sys

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import audiocore  # noqa: E402
import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline import cast, remote  # noqa: E402

PLANTS = ("no-show", "steal-default", "deaf-desk", "flood", "lost-kind", "no-close")
RESULTS = [0, 0]
RATE = 48000
W, H = cast.SIZE
UI_MS = 30
FPS = cast.COMPANION_FPS     # the slower cast: the desk redraws faster than this


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
    if name == "no-show":
        old = cast.CastDesk.step

        def step(self):
            self.dirty = False
            old(self)
        cast.CastDesk.step = step
    elif name == "steal-default":
        old = cast.CastDesk.__init__

        def init(self, *a, **k):
            old(self, *a, **k)
            self.disp.set_default()
        cast.CastDesk.__init__ = init
    elif name == "deaf-desk":
        cast.CastDesk.step = lambda self: None
    elif name == "flood":
        old = cast.CastDesk.__init__

        def init(self, *a, **k):
            old(self, *a, **k)
            self.gap_ms = 0
        cast.CastDesk.__init__ = init
    elif name == "lost-kind":
        old = remote.cast_target

        def target(prefs=None, spec=None):
            t = old(prefs, spec)
            if t is not None:
                t["kind"] = "windows"
            return t
        remote.cast_target = target
    elif name == "no-close":
        cast.CastDesk.close = lambda self: self.panel.close()
    else:
        raise SystemExit("no such plant: %r" % name)


class Sink:
    """What a cast looks like to the desk: a frame buffer, and a frame
    handed over at each ``show()``. It keeps the strip's rows of each frame."""

    def __init__(self, w, h):
        self.buf = bytearray(w * h * 2)
        self.w = w
        self.shown = 0
        self.closed = False
        self.frames = []
        self.rows = None

    def framebuffers(self):
        return (self.buf, None, len(self.buf), self.w * 2)

    def show(self):
        self.shown += 1
        if self.rows is not None:
            a, b = self.rows
            self.frames.append(bytes(self.buf[a * self.w * 2:b * self.w * 2]))

    def stats(self):
        return {"shown": self.shown}

    def close(self):
        self.closed = True


def coords(o):
    a = lv.area_t()
    o.get_coords(a)
    return a.x1, a.y1, a.x2, a.y2


def width(disp):
    return disp.get_horizontal_resolution()


def same(a, b):
    """The binding may wrap one LVGL object twice: compare where it is."""
    return coords(a) == coords(b) and a.get_child_count() == b.get_child_count()


def check_targets():
    t = remote.cast_target(spec="windows:192.0.2.30")
    check("windows:HOST is a Wireless Display cast", t == {"kind": "windows", "host": "192.0.2.30",
                                                           "name": "windows at 192.0.2.30"}, repr(t))
    t = remote.cast_target({"cast": "roku:192.0.2.40"})
    check("the setting roku:HOST is Screen mirroring", t is not None and t["kind"] == "roku", repr(t))
    t = remote.cast_target(spec="companion:192.0.2.40")
    check("companion:HOST is the Companion channel", t is not None and t["kind"] == "companion", repr(t))
    saved = os.environ.pop("BACKLINE_CAST", None)
    try:
        check("no setting is no cast", remote.cast_target({}) is None and remote.cast_target({"cast": ""}) is None)
        os.environ["BACKLINE_CAST"] = "roku:192.0.2.41"
        t = remote.cast_target({})
        check("$BACKLINE_CAST is read when the settings say nothing", t is not None and t["host"] == "192.0.2.41",
              repr(t))
        t = remote.cast_target({"cast": "windows:192.0.2.31"})
        check("the setting comes before $BACKLINE_CAST", t is not None and t["host"] == "192.0.2.31", repr(t))
    finally:
        os.environ.pop("BACKLINE_CAST", None)
        if saved is not None:
            os.environ["BACKLINE_CAST"] = saved
    for bad in ("chromecast:192.0.2.40", "windows:", "192.0.2.40"):
        try:
            remote.cast_target(spec=bad)
            refused = False
        except ValueError:
            refused = True
        check("%r is refused" % bad, refused)
    try:
        cast.open_sink({"kind": "airplay", "host": "192.0.2.40"})
        refused = False
    except ValueError:
        refused = True
    check("a cast of an unknown kind is refused", refused)


def run():
    _headless.display(320, 240)             # the box's own screen
    own = lv.display_get_default()
    own_scr = lv.obj(None)
    lv.screen_load(own_scr)
    frames = [0]
    ms = [0]
    box = boxmod.Box(lambda: frames[0], song="rock", now_ms=lambda: ms[0])
    box.device._tele_ms = 0
    sink = Sink(W, H)
    view = cast.CastDesk(sink, box.device, fps=FPS, now_ms=lambda: ms[0])
    check("the cast display is %dx%d" % (W, H),
          (view.disp.get_horizontal_resolution(), view.disp.get_vertical_resolution()) == (W, H))
    probe = lv.obj(None)
    check("new screens still go to the box's own display", width(probe.get_display()) == 320 and
          width(lv.display_get_default()) == 320)
    probe.delete()
    check("the box's own screen is still the one it shows", same(own.get_screen_active(), own_scr))
    check("the cast's screen is on the cast display", width(view.screen.get_display()) == W and
          same(view.disp.get_screen_active(), view.screen))

    strip = view.desk.perform.strip
    view.screen.update_layout()
    x1, y1, x2, y2 = coords(strip.base)
    sink.rows = (max(0, y1), min(H, y2 + 1))
    e = box.engine
    spb = RATE * 60.0 / e.project["tempo"]

    def run_for(beats):
        end = frames[0] + int(beats * spb)
        next_ui = ms[0]
        while frames[0] < end:
            box.service()
            audiocore.get_buffer(box.bus.output)
            frames[0] += 256
            ms[0] = frames[0] * 1000 // RATE
            box.poll()
            if ms[0] >= next_ui:
                next_ui += UI_MS
                box.device._telemetry()
                _headless.advance(UI_MS)
                view.step()

    run_for(1)
    before = sink.shown
    e.gesture(0, "tap")
    t0 = ms[0]
    run_for(1.5)
    first = sink.frames[-1] if sink.frames else None
    run_for(4.5)
    seconds = (ms[0] - t0) / 1000.0
    shown = sink.shown - before
    check("frames reach the cast while the song plays", shown >= seconds * FPS / 2,
          "%d frames in %.1f s" % (shown, seconds))
    check("no faster than %d a second" % FPS, shown <= seconds * FPS + 2,
          "%d frames in %.1f s" % (shown, seconds))
    lit = len(set(bytes(sink.buf[i:i + 2]) for i in range(0, len(sink.buf), 2 * 997)))
    check("the frame holds the desk, not a blank screen", lit > 8, "%d colours sampled" % lit)
    last = sink.frames[-1] if sink.frames else None
    check("the strip's playhead moved between two cast frames", first is not None and last is not None and
          first != last)
    t = e.telemetry()
    check("the song is playing on the box", t["playing"] and t["part"] != "", repr(t.get("part")))

    other = hmilink.Panel(local.connect(box.device.add(local.serve())))
    box.poll()
    other.poll()
    shown = sink.shown
    other.set("/tempo", 97)
    run_for(2)
    doc = view.panel.doc or {}
    check("a tempo set from another panel reaches the cast's desk", doc.get("tempo") == 97 and sink.shown > shown,
          "tempo %r" % (doc.get("tempo"),))
    other.close()

    view.close()
    box.poll()
    check("closing ends the cast", sink.closed)
    check("closing leaves the box", view.panel.closed)
    box.close()


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    check_targets()
    run()
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
