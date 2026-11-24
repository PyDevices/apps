# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What happens around a switch between Backline's floor and desk views,
and a song change, on a box's own screen at 800x480.

A switch: the app's timer passes that land inside it do no panel work
(`backline.app.Views.poll`), and telemetry that reaches the floor while it
draws its art again is kept until the art is there, so the ring is drawn
once and no digit is reached for before it is drawn. A song change: a song
on the kit playing builds no kit, another kit is built after the old one
is closed, and a kit that won't open leaves the old one playing. A meter
change keeps the beat's digits both meters show.

Notes play through a switch: the box's pass that sequences them runs
between one picture and the next, and between the rows of a desk laid out
again for another song. A desk hidden behind the floor lays out nothing on
a song change, and when it shows again it is the same, pixel for pixel, as
a desk made fresh on that song. A document that changes nothing the desk
shows lays nothing out again.

    python tests/backline_switch_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks one of those (``PLANTS``) and a check must then
fail.
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
from backline import app, art, floor, kits  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline.desk import Desk  # noqa: E402
from backline.desk import editor as editormod  # noqa: E402
from backline.desk import grid as gridmod  # noqa: E402
from backline.desk import perform as performmod  # noqa: E402

PLANTS = ("poll-mid-switch", "tele-mid-draw", "rebuild-same-kit", "build-beside-old", "lose-kit",
          "rewrite-digits", "hold-notes", "lay-out-hidden", "drop-held", "relay-same-song")
W, H = 800, 480
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
    if name == "poll-mid-switch":
        def poll(self, box):
            box.poll()
            self.floor.poll()
            if self.desk is not None:
                self.desk.poll()
            return True
        app.Views.poll = poll
    elif name == "tele-mid-draw":
        def show(self):
            if self.hidden:
                self.hidden = False
                self._draw()
                self.shown = {}
                self._tele({})
            self.base.remove_flag(lv.obj.FLAG.HIDDEN)
        floor.Floor.show = show
    elif name == "rebuild-same-kit":
        old_use = boxmod.Box.use_kit

        def use_kit(self, spec):
            if spec == self.kit_spec():
                self.engine.set_kit(None)
                self.bus.detach()
            return old_use(self, spec)
        boxmod.Box.use_kit = use_kit
    elif name == "build-beside-old":
        def use_kit(self, spec):
            if spec == self.kit_spec():
                return True
            kit = kits.open_kit(spec, self.rate)
            self.bus.attach(kit)
            self.engine.set_kit(kit)
            return True
        boxmod.Box.use_kit = use_kit
    elif name == "lose-kit":
        def use_kit(self, spec):
            if spec == self.kit_spec():
                return True
            if not self.engine.transport["playing"] and self.bus.kit is not None:
                self.engine.set_kit(None)
                self.bus.detach()
            try:
                kit = kits.open_kit(spec, self.rate)
            except Exception as e:  # noqa: BLE001
                self.error = "kit %s: %s" % (spec, e)
                return False
            self.bus.attach(kit)
            self.engine.set_kit(kit)
            return True
        boxmod.Box.use_kit = use_kit
    elif name == "rewrite-digits":
        old_ring = art.Texts.ring

        def ring(self, steps, group):
            if self.meter is not None and self.meter != (steps, group):
                self.meter = None       # forget it all: everything is written fresh
                self._ring_at = (0, 0)
                self._keep(self._texts(0, self._face), [])
                return old_ring(self, steps, group)
            return old_ring(self, steps, group)
        art.Texts.ring = ring
    elif name == "hold-notes":
        art.pause = lambda: None
    elif name == "lay-out-hidden":
        old_hide = Desk.hide

        def hide(self):
            old_hide(self)
            self.hidden = False
        Desk.hide = hide
    elif name == "drop-held":
        old_show = Desk.show

        def show(self):
            self._stale = False
            old_show(self)
        Desk.show = show
    elif name == "relay-same-song":
        old_doc = performmod.Perform.on_doc
        old_rebuild = editormod.Editor.rebuild

        def on_doc(self, doc, desc):
            self.titles = self.kits_listed = None
            old_doc(self, doc, desc)

        def rebuild(self, *args):
            self.grid.head = None
            old_rebuild(self, *args)
        performmod.Perform.on_doc = on_doc
        editormod.Editor.rebuild = rebuild
    else:
        raise SystemExit("no such plant: %r" % name)


class Hook:
    """Runs ``fn`` once, as the next picture of the art starts to draw: where
    a timer's pass lands in the middle of a switch."""

    def __init__(self):
        self.fn = None
        self.error = None
        self.trace = []     # "p" as each picture starts, "s" for each pass of the box's
        real = art.Picture
        hook = self

        class Picture(real):
            def __init__(self, *args, **kwargs):
                fn, hook.fn = hook.fn, None
                if fn is not None:
                    fn()
                hook.trace.append("p")
                real.__init__(self, *args, **kwargs)

        art.Picture = Picture


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    print("on " + sys.implementation.name)
    hook = Hook()
    _headless.display(W, H)
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
    polled = [0]
    real_poll = hmilink.Panel.poll

    def counted_poll(self):
        polled[0] += 1
        return real_poll(self)

    hmilink.Panel.poll = counted_poll

    def make_desk(on_switch):
        desk_panels.append(hmilink.Panel(local.connect(listener)))
        box.poll()
        desk_panels[-1].poll()
        return Desk(scr, (W, H), desk_panels[-1], on_switch=on_switch)

    def service():
        hook.trace.append("s")
        box.service()

    views = app.Views(lambda on_switch: floor.Floor(scr, (W, H), panel, on_switch=on_switch), make_desk,
                      service=service)

    def settle():
        for _ in range(3):
            box.device._telemetry()
            views.poll(box)
            _headless.advance(30)
        _headless.refresh()

    def play():
        box.engine.gesture(0, "tap")
        for _ in range(40):
            box.service()
            frames[0] += 2048

    settle()
    play()
    settle()
    views.show("desk")
    settle()
    views.show("floor")
    settle()

    # A timer's pass in the middle of a switch, with telemetry waiting.
    for which in ("desk", "floor"):
        seen = []

        def timer_pass():
            box.device._telemetry()
            before = polled[0]
            seen.append(views.poll(box))
            seen.append(polled[0] - before)

        hook.fn = timer_pass
        views.show(which)
        settle()
        check("a timer's pass while the %s draws reads no panel" % which, seen[1:] == [0],
              "it polled the panels %d times" % (seen[1] if len(seen) > 1 else -1))

    # Notes play through a switch: a pass of the box's between each picture.
    for which in ("desk", "floor"):
        del hook.trace[:]
        views.show(which)
        trace = "".join(hook.trace)
        run = max(len(r) for r in trace.split("s"))
        check("the box's pass runs between the pictures of a switch to the %s" % which,
              "p" in trace and run <= 1,
              "%d pictures, %d passes, at most %d pictures in a row" % (trace.count("p"), trace.count("s"), run))
        settle()

    # Telemetry that reaches the floor while it draws its art again, with a
    # tempo the floor hasn't shown: its digits aren't drawn yet.
    views.show("desk")
    settle()
    box.set("/tempo", 97)
    settle()
    drawn = [0]
    real_bands = art.bands

    def counted_bands(*args, **kwargs):
        drawn[0] += 1
        return real_bands(*args, **kwargs)

    art.bands = counted_bands
    fl = views.floor
    trouble = []

    def tele_now():
        try:
            fl._tele(box.telemetry())
        except Exception as e:  # noqa: BLE001 - what a timer would have hit
            trouble.append("%s: %s" % (type(e).__name__, e))

    hook.fn = tele_now
    try:
        views.show("floor")
    except Exception as e:  # noqa: BLE001
        trouble.append("%s: %s" % (type(e).__name__, e))
    settle()
    art.bands = real_bands
    t = box.telemetry()
    check("telemetry while the floor draws again is shown once the art is there",
          not trouble and fl.shown.get("tempo") == int(t["tempo"] + 0.5) == 97 and fl.shown.get("bar"),
          "; ".join(trouble) or "the floor shows %r" % (fl.shown,))
    check("the floor's ring is drawn once when it shows again", drawn[0] == 1, "drawn %d times" % drawn[0])

    # Song changes: the kit is built only when it changes, after the old one goes.
    box.command("stop", {})
    settle()
    opened = []
    real_open = kits.open_kit

    def counted_open(spec, rate=kits.RATE):
        old = box.bus.kit
        opened.append((spec, old is None and box.engine.kit is None))
        return real_open(spec, rate)

    kits.open_kit = counted_open

    def song(name):
        i = [j for j, (n, _p) in enumerate(box.songs) if n == name][0]
        box.command("song", {"index": i})
        settle()

    builds = [0]
    real_build = gridmod.Grid.build

    def counted_build(self, *args):
        builds[0] += 1
        return real_build(self, *args)

    gridmod.Grid.build = counted_build
    buttons = [0]
    real_button = performmod.look.button

    def counted_button(*args, **kwargs):
        buttons[0] += 1
        return real_button(*args, **kwargs)

    performmod.look.button = counted_button

    song("funk")      # the same kit as rock's
    check("a desk hidden behind the floor lays out nothing on a song change",
          views.shown == "floor" and builds[0] == 0 and buttons[0] == 0,
          "%d grids and %d song buttons laid out" % (builds[0], buttons[0]))
    check("a song on the kit playing builds no kit", opened == [] and box.kit_spec() == "rhythm909",
          "built %r" % (opened,))
    first = box.bus.kit
    song("bossa")
    check("a song on another kit builds it once, after the old one is closed",
          [s for s, _ in opened] == ["rhythm606"] and all(gone for _, gone in opened)
          and getattr(first, "inst", None) is None and box.kit_spec() == "rhythm606",
          "built %r" % (opened,))
    del opened[:]
    box.command("kit", {"spec": "no_such_kit"})
    settle()
    check("a kit that won't open leaves the one before playing",
          box.kit_spec() == "rhythm606" and box.bus.kit is not None and "no_such_kit" in (box.error or ""),
          "playing %r, error %r" % (box.kit_spec(), box.error))
    kits.open_kit = real_open
    box.error = None

    # The hidden desk, shown again, is the desk made fresh on that song.
    def shots(desk):
        out = []
        desk.perform.songs.scroll_to_y(0, False)   # where a list was scrolled to is the desk's own history
        for tab in ("perform", "edit"):
            desk.show_tab(tab)
            for _ in range(3):
                views.poll(box)
                _headless.advance(30)
            scr.invalidate()
            _headless.refresh()
            out.append(bytes(_headless._state["frame"]))
        desk.show_tab("perform")
        return out

    views.show("desk")
    settle()
    kept = shots(views.desk)
    views.desk.hide()
    fresh = make_desk(lambda: None)
    for _ in range(3):
        box.device._telemetry()
        box.poll()
        desk_panels[-1].poll()
    fresh.show()
    made = shots(fresh)
    fresh.base.delete()
    desk_panels.pop().close()
    views.desk.show()
    settle()
    differ = [sum(1 for i in range(0, len(a), 2) if a[i:i + 2] != b[i:i + 2]) for a, b in zip(kept, made)]
    check("a desk shown again after song changes is the desk made fresh on that song, pixel for pixel",
          differ == [0, 0], "%r pixels differ on the perform and edit tabs" % (differ,))

    # A document that changes nothing the desk shows lays nothing out.
    builds[0] = buttons[0] = 0
    desk = views.desk
    desk._doc(desk.panel.doc, desk.panel.desc)
    check("a document with the same songs, kits and grid lays nothing out again",
          builds[0] == 0 and buttons[0] == 0, "%d grids and %d song buttons laid out" % (builds[0], buttons[0]))

    # A shown desk laid out for another song lets the box play between rows.
    passes = []

    def watched_build(self, rows, *args):
        before = hook.trace.count("s")
        counted_build(self, rows, *args)
        passes.append((len(rows), hook.trace.count("s") - before))

    gridmod.Grid.build = watched_build
    del hook.trace[:]
    song("rock")
    gridmod.Grid.build = real_build
    performmod.look.button = real_button
    check("a desk laid out for another song lets the box's pass run between its rows",
          passes and all(n >= rows for rows, n in passes), "rows and passes per grid: %r" % (passes,))
    views.show("floor")
    settle()

    # A meter change keeps the beat's digits both meters show.
    lay = fl.lay
    written = []
    real_digit = art.digit_svg

    def counted_digit(ch, w, h, *args, **kwargs):
        if (w, h) == (lay.big_w, lay.big_h):
            written.append(ch)
        return real_digit(ch, w, h, *args, **kwargs)

    art.digit_svg = counted_digit
    fl._ring(4, 1)
    settle()
    fl._ring(12, 3)
    settle()
    art.digit_svg = real_digit
    same = all(bytes(fl.texts.big(ch)) == real_digit(ch, lay.big_w, lay.big_h).encode()
               for ch in art.beat_digits(12, 3))
    check("from 4/4 to 12/8 the beat's digits are kept, not written again", written == [] and same,
          "written %r, as fresh: %r" % (written, same))

    hmilink.Panel.poll = real_poll
    scr.delete()
    for p_ in desk_panels + [panel]:
        p_.close()
    box.close()
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
