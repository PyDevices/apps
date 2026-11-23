# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's floor view on real LVGL with no window, at 320x240, 480x320,
800x480 and 720x720: it fits the screen, the bar's words fit inside the
ring on one line and the tempo's digits inside their window, lights one more segment of the ring each
beat and redraws little else, gives a 12/8 song twelve segments, shows the
song's name and the part coming next in full, shows the part and the next
one, lights a pedal's lamp while it is down, a touch on a lamp reaches the
device, the corner button asks for the desk view, and the beat's digit
pulses as a beat lands and settles before the next.

Then the app's item on appkit's status bar shows the part and the tempo
while a song plays and nothing while it's stopped, and on a firmware whose
icons font is older than Backline's newest icons, each icon falls back to
one the font has, or to a glyph.

    python tests/backline_floor_contract.py [--plant=NAME]

The view draws from an hmilink panel over the ``local`` transport; the
device here is a stand-in whose telemetry the check writes. Needs LVGL,
svgio and hmilink. ``--plant=NAME`` breaks the view one way (``PLANTS``)
and a check must then fail.
"""

import math
import sys

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
import icons  # noqa: E402
from appkit import bar as appbar  # noqa: E402
from backline import art, floor, glyphs  # noqa: E402
from backline.engine import BAR  # noqa: E402

PLANTS = ("no-beat", "full-redraw", "deaf-lamp", "overflow", "stale-part", "dark-lamp", "four-beats", "truncate",
          "dead-switch", "no-pulse", "mute-bar", "bar-while-stopped", "no-fallback", "screen-font", "wide-tempo")
# Icons newer than some firmware's font: the fallback check hides them.
NEW_ICONS = ("footprint", "steps", "sound_sampler", "music_cast", "cast_connected", "smartphone", "auto_awesome",
             "keyboard_voice", "mic_external_on", "repeat_one", "loop", "playlist_play", "lyrics", "timeline",
             "linear_scale", "waves", "spatial_audio", "settings_input_component", "view_module", "vibration")
SIZES = ((320, 240), (480, 320), (800, 480), (720, 720))
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
    elif name == "four-beats":
        old = floor.Floor._ring
        floor.Floor._ring = lambda self, steps, group, decoder=None: old(self, 4, 1, decoder)
    elif name == "truncate":
        def fit(label, choices, width, space=1):
            label.set_style_text_letter_space(space, 0)
            label.set_text(choices[0])
            return choices[0]
        floor.fit = fit
    elif name == "dead-switch":
        old = floor.Floor.__init__

        def init(self, root, size, panel, on_switch=None):
            old(self, root, size, panel, (lambda: None) if on_switch is not None else None)
        floor.Floor.__init__ = init
    elif name == "no-pulse":
        floor.pulse = lambda tele, steps: 0
    elif name == "mute-bar":
        glyphs.bar_reading = lambda t: None
    elif name == "bar-while-stopped":
        old_reading = glyphs.bar_reading

        def reading(t):
            t = dict(t)
            t["playing"] = True
            return old_reading(t)
        glyphs.bar_reading = reading
    elif name == "no-fallback":
        glyphs.pick = lambda role: glyphs.ICONS[role][0][0]
    elif name == "screen-font":
        art.Layout.font_px = (lambda old: lambda self, want: old(self, max(want, self.h * 0.06)))(art.Layout.font_px)
    elif name == "wide-tempo":
        old = art.Layout.__init__

        def init(self, w, h):
            old(self, w, h)
            self.small_h = max(14, self.tempo[3] - 8)
            self.small_w = int(self.small_h * 0.58)
        art.Layout.__init__ = init
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
    switched = []
    view = floor.Floor(scr, (w, h), panel, on_switch=lambda: switched.append(1))

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
    wide = []
    for kw in ({"playing": False}, {"bar": 12, "bars": 12}):
        show(beat=1, **kw)
        font = view.bar.get_style_text_font(0)
        text = view.bar.get_text()
        wide.append((text, floor.text_width(text, font, view.bar.get_style_text_letter_space(0))))
    check(tag + ": the bar's words fit inside the ring on one line", wide[0][0] == "STOPPED" and
          "12 / 12" in wide[1][0] and all(tw <= view.bar.get_width() for _t, tw in wide),
          "%r in %d" % (wide, view.bar.get_width()))
    show(beat=1)
    tx, _ty, tw, _th = view.lay.tempo
    slots = art.tempo_slots(view.lay)
    check(tag + ": the tempo's digits sit inside their window",
          slots[0] >= tx and slots[-1] + view.lay.small_w <= tx + tw, "%r of %d wide in %r" % (slots, view.lay.small_w,
                                                                                              view.lay.tempo))
    held = view.bytes()
    check(tag + ": the art holds under four screens' worth", held < 4 * w * h * 3, "%d bytes" % held)
    lay = view.lay
    probes = []
    for b in range(4):
        a0, a1 = art.beat_span(b)
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
    probes12 = []
    for b in range(12):
        a0, a1 = art.beat_span(b, 12, 3)
        am = math.radians((a0 + a1) / 2)
        mid = (lay.beat_in + lay.beat_out) / 2
        probes12.append((lay.cx + mid * math.cos(am), lay.cy + mid * math.sin(am)))
    ok = True
    for step in (1, 5, 12):
        show(steps=12, beats=4, step=step, beat=(step - 1) // 3 + 1)
        lit = [bright(pixel(frame, w, x, y)) > dark + 150 for x, y in probes12]
        if lit != [i < step for i in range(12)]:
            ok = False
            print("     12/8 step %d lit %r" % (step, lit))
    check(tag + ": a 12/8 song lights twelve segments, one a step", ok)
    show(beat=1, song="Country Train", part="Main 1", next="Transition", next_role="transition")
    words = []
    for lbl in (view.song, view.chip_text):
        font = lbl.get_style_text_font(0)
        words.append((lbl.get_text(), floor.text_width(lbl.get_text(), font, lbl.get_style_text_letter_space(0)),
                      lbl.get_width()))
    check(tag + ": the song's name and the next part show in full", words[0][0] == "COUNTRY TRAIN" and
          "TRANSITION" in words[1][0] and all(tw <= lw for _t, tw, lw in words), repr(words))
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
    a = lv.area_t()
    view.switch.get_coords(a)
    _headless.touch((a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2, True, 40)
    _headless.touch((a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2, False, 40)
    check(tag + ": the corner button asks for the desk view", switched == [1], repr(switched))
    beat = BAR // 4
    show(beat=3, step=3, at=2 * beat)
    landed = view.beat_digit.get_style_image_recolor_opa(0)
    show(beat=3, step=3, at=2 * beat + beat // 2)
    settled = view.beat_digit.get_style_image_recolor_opa(0)
    check(tag + ": the beat's digit pulses as the beat lands and settles by mid-beat", landed > 0 and settled == 0,
          "%d, then %d" % (landed, settled))
    scr.delete()
    device.close()


def run_bar():
    """The status bar's item, and the icons on an older font."""
    w, h = 320, 240
    _headless.display(w, h)
    scr = lv.obj(None)
    lv.screen_load(scr)
    bar = appbar.Bar(registry=None, items=[], tick_ms=0)
    state = {"t": tele(beat=2, part="Main 2", tempo=96.4)}
    bar.add(appbar.Item("backline", lambda: glyphs.bar_reading(state["t"])))
    bar.tick()
    shown = dict((name, (icon, text)) for name, icon, text in bar.status())
    got = shown.get("backline")
    check("the status bar shows the part and the tempo while a song plays",
          got is not None and "MAIN 2" in (got[1] or "") and "96" in (got[1] or ""), repr(got))
    state["t"] = tele(playing=False)
    bar.tick()
    names = [name for name, _i, _t in bar.status()]
    check("the status bar shows nothing of Backline while it's stopped", "backline" not in names, repr(bar.status()))
    bar.close()

    real_has = icons.has
    icons.has = lambda name: name not in NEW_ICONS and real_has(name)
    try:
        picked = dict((role, glyphs.pick(role)) for role in glyphs.ICONS)
        drawn = glyphs.show(scr, "form", 16, lv.color_hex(0xFFFFFF))
        text = drawn.get_text() if hasattr(drawn, "get_text") else None
        lost = [r for r, n in picked.items() if n is not None and n in NEW_ICONS]
        reading = glyphs.bar_reading(tele(cast="Living room"))
        ok = not lost and picked["desk"] == "grid_on" and text == glyphs.ICONS["form"][1] and \
            reading[0] == "cast"
        check("on an older icons font every icon falls back to one it has, or to a glyph", ok,
              "%r, form drew %r, bar %r" % (picked, text, reading))
    finally:
        icons.has = real_has
    scr.delete()


def main():
    argv = sys.argv[1:]
    p = None
    for a in argv:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    for w, h in SIZES:
        run_size(w, h)
    run_bar()
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
