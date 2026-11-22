# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's desk view on real LVGL with no window, at 800x480 and 1280x720,
two desks on one box while a song plays: one on the box's own screen through
``hmilink.local``, the other joined over TCP as another computer would.

Each size: both tabs fit the screen; the song-form strip's playhead moves on
as the song plays; the grid has a row for each of the kit's drums the song
uses or every grid shows, and no more; a finger's tap on a cell of the local
desk lands in the box's song and on the remote desk's grid, a tap on the
remote desk lands back on the local one, and the song plays on through both;
a fader moved on one desk moves on the other; and the tempo button changes
the box's tempo.

    python tests/backline_desk_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the desk one way (``PLANTS``) and a check must
then fail.
"""

import sys
import time

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import audiocore  # noqa: E402
import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local, tcp  # noqa: E402

import _headless  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline import desk_main, parts  # noqa: E402
from backline.desk import Desk, editor, grid, perform, strip  # noqa: E402

PLANTS = ("overflow", "wide-grid", "deaf-cell", "stale-grid", "still-strip", "all-rows", "deaf-fader")
SIZES = ((800, 480), (1280, 720))
RESULTS = [0, 0]
RATE = 48000


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
    if name == "overflow":
        old = perform.Perform.__init__

        def init(self, parent, x, y, w, h, desk):
            old(self, parent, x, y, w + 160, h, desk)
        perform.Perform.__init__ = init
    elif name == "wide-grid":
        old_build = grid.Grid.build

        def build(self, rows, cols, beat):
            self.w += 12
            old_build(self, rows, cols, beat)
            self.w -= 12
        grid.Grid.build = build
    elif name == "deaf-cell":
        grid.Grid._tapper = lambda self, pitch, c: (lambda e: None)
    elif name == "stale-grid":
        editor.Editor.on_op = lambda self, op: None
    elif name == "still-strip":
        old = strip.Strip.show

        def show(self, tele):
            t = dict(tele)
            t["at"] = 0
            old(self, t)
        strip.Strip.show = show
    elif name == "all-rows":
        parts.rows = lambda voices, doc: [(int(p), n) for p, n in voices]
    elif name == "deaf-fader":
        editor.Editor._fader = lambda self, key, final=False: (lambda value: None)
    else:
        raise SystemExit("no such plant: %r" % name)


def coords(o):
    a = lv.area_t()
    o.get_coords(a)
    return a.x1, a.y1, a.x2, a.y2


def outside(root, w, h):
    """The objects that reach past the screen, or past a parent that doesn't
    scroll that way."""
    bad = []

    def walk(o, clip):
        if o.has_flag(lv.obj.FLAG.HIDDEN):
            return
        x1, y1, x2, y2 = coords(o)
        if clip is not None and (x1 < clip[0] - 1 or x2 > clip[2] + 1 or
                                 (clip[1] is not None and (y1 < clip[1] - 1 or y2 > clip[3] + 1))):
            bad.append((x1, y1, x2, y2))
        inner = (x1, y1, x2, y2)
        if o.has_flag(lv.obj.FLAG.SCROLLABLE) and o.get_child_count() and o is not root:
            # A list that scrolls up and down may run long, never wide.
            inner = (x1, None, x2, None) if o.get_scroll_dir() == lv.DIR.VER else None
        for i in range(o.get_child_count()):
            walk(o.get_child(i), inner)

    walk(root, (0, 0, w - 1, h - 1))
    return bad


def run_size(w, h):
    tag = "%dx%d" % (w, h)
    _headless.display(w, h)
    _headless.pointer().set_display(_headless._state["display"])
    scr = lv.obj(None)
    lv.screen_load(scr)
    other = lv.obj(None)          # the remote desk's screen: drawn into, never shown
    frames = [0]
    box = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm808", now_ms=lambda: frames[0] * 1000 // RATE)
    box.device._tele_ms = 0
    listener = box.device.add(local.serve())
    served = box.device.add(tcp.serve(0, bind="127.0.0.1"))
    port = served.sock.getsockname()[1]
    near = hmilink.Panel(local.connect(listener))
    box.poll()
    near.poll()
    desk = Desk(scr, (w, h), near)
    far = desk_main.Remote(other, (w, h), "127.0.0.1", port)
    e = box.engine
    spb = RATE * 60.0 / e.project["tempo"]

    def run(beats):
        end = frames[0] + int(beats * spb)
        while frames[0] < end:
            box.service()
            audiocore.get_buffer(box.bus.output)
            frames[0] += 256
            if frames[0] % 1024 == 0:
                box.poll()
                box.device._telemetry()
                desk.poll()
                far.step()
                _headless.advance(5)
        for _ in range(3):
            box.poll()
            desk.poll()
            far.step()

    def settle(done, seconds=3.0):
        """Poll every side, the song held still, until ``done()`` or the time is up.
        A TCP link takes a few passes to carry an op both ways."""
        end = time.monotonic() + seconds
        while not done() and time.monotonic() < end:
            box.poll()
            box.device._telemetry()
            desk.poll()
            far.step()
            time.sleep(0.005)
        return done()

    run(0.1)
    check(tag + ": the remote desk joins over TCP",
          settle(lambda: far.desk.panel is not None and far.desk.panel.doc is not None))
    for tab in ("perform", "edit"):
        desk.show_tab(tab)
        _headless.advance(5)
        _headless.refresh()
        bad = outside(desk.base, w, h)
        check(tag + ": the %s tab fits the screen" % tab, not bad, "outside: %r" % bad[:4])
    desk.show_tab("perform")
    e.gesture(0, "tap")
    run(9.0)                      # into main 1
    x0 = desk.perform.strip.head_x()
    run(1.0)
    x1 = desk.perform.strip.head_x()
    check(tag + ": the song form's playhead moves on as it plays", 0 <= x0 < x1, "%d -> %d" % (x0, x1))

    desk.show_tab("edit")
    run(0.1)
    ed, fed = desk.editor, far.desk.editor
    pitches = [p for p, _n in ed.grid.rows]
    kit = set(p for p, _n in box.voices())
    used = set(n[2] for pat in e.project["tracks"][0]["patterns"] for n in pat["notes"])
    want = sorted((set(parts.CORE) & kit) | used, reverse=True)
    check(tag + ": the grid has a row for each drum the song uses or every grid shows", pitches == want,
          "%r, not %r" % (pitches, want))
    main = e.project["parts"]["mains"][0]
    check(tag + ": both desks follow the playing part", ed.pattern == main and fed.pattern == main,
          "%r, %r" % (ed.pattern, fed.pattern))
    col = 6                       # a step no starter song plays the clap on
    pitch = 39 if 39 in pitches else pitches[0]
    step = ed.bar * ed.cols + col
    before = ed.grid.level(pitch, col)
    x, y = ed.grid.center(pitch, col)
    _headless.touch(x, y, True, 40)
    _headless.touch(x, y, False, 40)
    run(0.2)
    settle(lambda: parts.cell(box.model.doc["tracks"][0]["patterns"][main]["notes"], pitch, step, ed.ticks) >= 0 and
           fed.grid.level(pitch, col) > 0)
    notes = box.model.doc["tracks"][0]["patterns"][main]["notes"]
    landed = parts.cell(notes, pitch, step, ed.ticks) >= 0
    check(tag + ": a tap on a cell lands in the box's song", before == 0 and landed, "before %d" % before)
    fed.grid.bar = ed.bar
    fed.show_cells()
    check(tag + ": the remote desk shows the tap", fed.grid.level(pitch, col) == 1, repr(fed.grid.level(pitch, col)))
    fed._tap(pitch, step)
    run(0.2)
    settle(lambda: ed.grid.level(pitch, col) == 2)
    check(tag + ": the remote desk's tap comes back to the local desk", ed.grid.level(pitch, col) == 2 and
          fed.grid.level(pitch, col) == 2, "%d, %d" % (ed.grid.level(pitch, col), fed.grid.level(pitch, col)))
    t = box.telemetry()
    same = near.doc["tracks"][0]["patterns"] == box.model.doc["tracks"][0]["patterns"] == \
        far.desk.panel.doc["tracks"][0]["patterns"]
    check(tag + ": the song plays on, both desks holding the box's song", t["playing"] and same, repr(t["part"]))
    ed._fader("kick", True)(40)
    run(0.2)
    settle(lambda: fed.faders["kick"].get_value() == 40)
    check(tag + ": a fader moved on one desk moves on the other", box.model.doc["tracks"][0]["mix"]["kick"] == 40 and
          fed.faders["kick"].get_value() == 40, repr(fed.faders["kick"].get_value()))
    desk.show_tab("perform")
    tempo = e.project["tempo"]
    b = desk.perform.base
    plus = None
    for i in range(b.get_child_count()):
        c = b.get_child(i)
        if c.get_child_count() == 1 and c.has_flag(lv.obj.FLAG.CLICKABLE) and coords(c)[0] > w * 0.85:
            plus = c
    if plus is not None:
        x1, y1, x2, y2 = coords(plus)
        _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, True, 40)
        _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, False, 40)
    run(0.2)
    check(tag + ": the tempo button changes the box's tempo", e.project["tempo"] == int(tempo + 0.5) + 1,
          "%r -> %r" % (tempo, e.project["tempo"]))
    far.close()
    near.close()
    box.close()
    scr.delete()
    other.delete()


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    for w, h in SIZES:
        run_size(w, h)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
