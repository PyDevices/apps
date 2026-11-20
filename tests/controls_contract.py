# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The shared controls' contract, run on whichever interpreter runs this file.

Builds each control on a display with no window and drives it the way a host
and a hand do. Prints one ``PASS name`` or ``FAIL name: why`` line per check,
and exits 1 if anything failed. ``--plant`` makes a slider stop reporting its
changes, an envelope ignore its rates and a routing diagram put every node
on one row, so those checks must fail: that is how test_controls.py knows
they can.

    micropython controls_contract.py [--plant]
"""

import gc
import sys

import _headless
import lvgl as lv

PLANT = "--plant" in sys.argv[1:]

_headless.display(800, 480)
_headless.pointer()

from controlkit import EnvelopeView, LampButton, LedMeter, PadGrid, RingButton, RoutingDiagram, Slider, SpectrumBars  # noqa: E402
from controlkit import envelope_view as envelope_module  # noqa: E402
from controlkit import routing_diagram as routing_module  # noqa: E402
from controlkit.mock import ENVELOPES, ROUTINGS, MockEnvelope  # noqa: E402
from routing_algorithms import ALGORITHMS, graph  # noqa: E402
from controlkit import slider as slider_module  # noqa: E402
from controlkit import encoder as encoder_module  # noqa: E402
from controlkit.theme import BLACK  # noqa: E402

if PLANT:
    # A slider that moves its cap but never tells its host.
    def _silent_change(self, value):
        value = 0 if value < 0 else (127 if value > 127 else int(value))
        if value != self.value:
            self._show(value)

    slider_module.Slider._change = _silent_change

    # An envelope whose segments are all one width, whatever their rates.
    envelope_module._SHORTEST = 1.0

    # A diagram with every node on the bottom row.
    _arrange = routing_module.arrange

    def _flat_arrange(nodes, edges, carriers):
        return {name: (float(i), 0) for i, name in enumerate(_arrange(nodes, edges, carriers))}

    routing_module.arrange = _flat_arrange

failures = []


def check(name, ok, why=""):
    if ok:
        print("PASS " + name)
    else:
        print("FAIL %s: %s" % (name, why))
        failures.append(name)


def screen():
    scr = lv.obj(None)
    lv.screen_load(scr)
    return scr


def point_at(obj):
    """Where the middle of *obj* is on the screen."""
    area = lv.area_t()
    obj.get_coords(area)
    return (area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2


# ---- Slider ------------------------------------------------------------------

scr = screen()
events = []
slider = Slider(scr, 20, 20, 60, 200, BLACK, legend="Cutoff", value=40, led=True,
                on_change=lambda s, v: events.append(v))
_headless.refresh()
check("slider opens on its value", slider.value == 40, str(slider.value))

slider.set_value(300)
check("set_value clamps high", slider.value == 127, str(slider.value))
slider.set_value(-5)
check("set_value clamps low", slider.value == 0, str(slider.value))
check("set_value does not call on_change", events == [], str(events))

slider.set_value(60)
cx, cy = point_at(slider.cap)
_headless.touch(cx, cy, False)
_headless.touch(cx, cy, True)
for i in range(1, 11):
    _headless.touch(cx, cy - 3 * i, True)
_headless.touch(cx, cy - 30, False)
check("dragging the cap up raises the value", slider.value > 60, str(slider.value))
check("a drag reports its change once", events and events[-1] == slider.value, str(events))
_headless.refresh()

group = lv.group_create()
group.add_obj(slider.obj)
lv.group_focus_obj(slider.obj)
before = slider.value
group.send_data(lv.KEY.RIGHT)
check("the arrow key steps it up", slider.value == before + 1, "%d -> %d" % (before, slider.value))
group.send_data(lv.KEY.END)
check("End goes to the top", slider.value == 127, str(slider.value))
group.send_data(lv.KEY.HOME)
check("Home goes to the bottom", slider.value == 0, str(slider.value))

slider.set_led(0xFF2814)
check("the lamp lights", slider.lamp is not None and slider.lamp.rgb == 0xFF2814)
slider.set_led(None)
check("the lamp goes out", slider.lamp is not None and slider.lamp.rgb is None)

horizontal = Slider(scr, 100, 20, 200, 40, BLACK, legend="Mix", vertical=False, value=127)
horizontal.set_led(0x010203)
check("a slider without led=True has no lamp", horizontal.lamp is None)
check("a horizontal slider opens at its value", horizontal.value == 127)
scr.delete()

# ---- LedMeter ----------------------------------------------------------------

scr = screen()
meter = LedMeter(scr, 20, 20, 30, 200, BLACK, segments=16, legend="Out")
_headless.refresh()
meter.set_level(0.5)
check("half a level lights half the segments", meter._lit == 8, str(meter._lit))
meter.set_level(1.0)
check("full scale lights every segment", meter._lit == 16, str(meter._lit))
check("the top segment is red", meter._segments[15][1] == "red", str(meter._segments[15][1]))
check("the bottom segment is green", meter._segments[0][1] == "green", str(meter._segments[0][1]))
meter.set_level(-1)
check("a level below zero is zero", meter._lit == 0 and meter.level == 0.0)
scr.delete()

# ---- LampButton --------------------------------------------------------------

scr = screen()
presses = []
momentary = LampButton(scr, 10, 10, 60, 26, BLACK, legend="Tap", on_press=lambda b, v: presses.append(v))
_headless.refresh()
momentary.cap.send_event(lv.EVENT.CLICKED, None)
check("a momentary press calls on_press with True", presses == [True], str(presses))
check("a momentary lamp is lit at all times", momentary.lamp.rgb is not None)

toggled = []
button = LampButton(scr, 100, 10, 60, 26, BLACK, legend="Run", toggle=True, lamp=0x00FF00,
                    on_press=lambda b, v: toggled.append(v))
button.cap.send_event(lv.EVENT.CLICKED, None)
check("a toggle turns on at a press", button.on and toggled == [True], str(toggled))
check("a toggle's lamp shows its colour while on", button.lamp.rgb == 0x00FF00)
button.cap.send_event(lv.EVENT.CLICKED, None)
check("a second press turns it off", not button.on and toggled == [True, False], str(toggled))
check("a toggle's lamp goes out when off", button.lamp.rgb is None)
button.set_on(True)
check("set_on lights the lamp without a call", button.on and len(toggled) == 2)
button.set_lamp(None)
check("set_lamp(None) darkens the lamp", button.lamp.rgb is None)
scr.delete()

# ---- PadGrid -----------------------------------------------------------------

scr = screen()
hits = []
grid = PadGrid(scr, 10, 10, 320, 120, BLACK, cols=8, rows=2, on_press=lambda g, i: hits.append(i))
_headless.refresh()
grid.set_color(3, 0x00FF00)
check("a pad takes a colour", grid.colors[3] == 0x00FF00)
grid.set_color(3, None)
check("a pad goes dark with None", grid.colors[3] is None)
grid._pads[9].send_event(lv.EVENT.CLICKED, None)
check("a press reports its pad index", hits == [9], str(hits))
try:
    grid.set_color(16, 0x010203)
    check("an index past the grid is refused", False, "no error")
except IndexError:
    check("an index past the grid is refused", True)
scr.delete()

# ---- Encoder: how the ring shows the value ------------------------------------


class _Panel:
    """What an encoder asks of the panel that holds it."""

    travel = 200
    fine = False

    def __init__(self):
        self.turned = []

    def default_value(self, index):
        return 64

    def _turned(self, encoder, value):
        self.turned.append(value)

    def _focused(self, encoder):
        pass


def ring(mode, value, enabled=True):
    """The LEDs' brightness for a new encoder in *mode* showing *value*."""
    enc = encoder_module.Encoder(_Panel(), scr, 0, "Pan", 10, 10, 120, 140, geom, BLACK, enabled=enabled, mode=mode)
    enc.set_value(value)
    _headless.refresh()
    levels = enc.lit()
    hidden = [led.has_flag(lv.obj.FLAG.HIDDEN) for led in enc._leds]
    check("%s at %d: a dark LED is hidden and a lit one is shown" % (mode, value),
          hidden == [level == 0 for level in levels], str(hidden))
    enc.obj.delete()
    return levels


def lit_leds(levels):
    return [i for i, level in enumerate(levels) if level]


scr = screen()
geom = encoder_module.geometry(120, 140, 1.0)

plain = encoder_module.Encoder(_Panel(), scr, 0, "Level", 10, 10, 120, 140, geom, BLACK)
check("an encoder fills its ring unless told otherwise", plain.mode == "fill", plain.mode)
plain.obj.delete()
check("fill at 0 is dark", lit_leds(ring("fill", 0)) == [])
check("fill at 127 is the whole ring", ring("fill", 127) == [255] * 16)
levels = ring("fill", 64)
check("fill at 64 lights the first half", levels[:8] == [255] * 8 and lit_leds(levels[9:]) == [], str(levels))

levels = ring("bipolar", 64)
check("bipolar at the centre lights only the two middle LEDs", lit_leds(levels) == [7, 8] and levels[7] == levels[8] == 255, str(levels))
levels = ring("bipolar", 127)
check("bipolar at 127 lights the middle to the end", levels == [0] * 7 + [255] * 9, str(levels))
levels = ring("bipolar", 0)
check("bipolar at 0 lights the start to the middle", levels == [255] * 9 + [0] * 7, str(levels))
levels = ring("bipolar", 96)
check("bipolar above the centre leaves the low half dark", lit_leds(levels)[0] == 7 and lit_leds(levels)[-1] in (11, 12) and levels[:7] == [0] * 7, str(levels))
levels = ring("bipolar", 32)
check("bipolar below the centre leaves the high half dark", lit_leds(levels)[0] in (3, 4) and lit_leds(levels)[-1] == 8 and levels[9:] == [0] * 7, str(levels))

levels = ring("dot", 0)
check("dot at 0 lights only the first LED", levels == [255] + [0] * 15, str(levels))
levels = ring("dot", 127)
check("dot at 127 lights only the last LED", levels == [0] * 15 + [255], str(levels))
moving = True
for value in range(128):
    on = lit_leds(ring("dot", value))
    moving = moving and 1 <= len(on) <= 2 and on[-1] - on[0] == len(on) - 1 and abs(on[0] - value * 15 / 127) < 1
check("dot lights one LED, or two neighbours while it crosses, at every value", moving)

check("an encoder past the macros stays dark in dot mode", lit_leds(ring("dot", 100, enabled=False)) == [])
check("an encoder past the macros stays dark in bipolar mode", lit_leds(ring("bipolar", 100, enabled=False)) == [])

panel = _Panel()
enc = encoder_module.Encoder(panel, scr, 0, "Pan", 10, 10, 120, 140, geom, BLACK, mode="bipolar")
enc.set_value(64)
check("set_value does not report back in bipolar mode", panel.turned == [], str(panel.turned))
enc._change(70)
check("a turn reports its value in bipolar mode", panel.turned == [70] and enc.value == 70, str(panel.turned))
try:
    encoder_module.Encoder(_Panel(), scr, 0, "Pan", 10, 10, 120, 140, geom, BLACK, mode="centre")
    check("a mode that isn't one of MODES is refused", False, "no error")
except ValueError:
    check("a mode that isn't one of MODES is refused", True)
scr.delete()

# A small screen: the panel's cells on a 160 x 128 display under an app's
# 64-pixel header are about 25 x 12. Every cell gets positive sizes or a
# clear refusal, never a negative canvas.
sound = True
for w in range(2, 80, 3):
    for h in range(2, 80, 3):
        try:
            g = encoder_module.geometry(w, h, 0.15)
        except ValueError as e:
            sound = sound and min(w - 4, h - 2) < encoder_module.MIN_ROOM and "at least" in str(e)
            continue
        sound = sound and g["size"] > 0 and g["led_ring"] > 0 and g["knob_r"] > 0 and g["size"] <= max(w, h)
check("an encoder's geometry is positive in every cell it accepts", sound)
small = encoder_module.geometry(25, 12, 0.133)
check("a cell too short for the legend drops it and keeps the knob", small["legend"] == 0 and small["size"] > 0, str(small))
scr = screen()
tiny = encoder_module.Encoder(_Panel(), scr, 0, "Cutoff", 10, 10, 25, 12, small, BLACK)
tiny.set_value(100)
check("an encoder in a 25 x 12 cell draws, with no legend",
      _headless.refresh() > 0 and tiny.legend.has_flag(lv.obj.FLAG.HIDDEN), str(small))
scr.delete()
try:
    encoder_module.geometry(12, 8, 0.1)
    check("a cell too small for any knob is refused with its minimum", False, "no error")
except ValueError as e:
    check("a cell too small for any knob is refused with its minimum", "14 x 12" in str(e), str(e))

scr = screen()
edges = []
grid = PadGrid(scr, 10, 10, 320, 320, BLACK, cols=4, rows=4,
               on_down=lambda g, i: edges.append(("down", i)), on_up=lambda g, i: edges.append(("up", i)))
grid.set_label(5, "C1")
_headless.refresh()
x, y = point_at(grid.pad(5))
_headless.touch(x, y, False, 40)
_headless.touch(x, y, True, 40)
check("a finger landing on a pad reports it down at once", edges == [("down", 5)], str(edges))
_headless.touch(x, y, False, 40)
check("lifting it reports it up", edges == [("down", 5), ("up", 5)], str(edges))
check("a pad shows its legend", grid._labels[5].get_text() == "C1")
grid.set_label(5, "D1")
check("a legend can change", grid._labels[5].get_text() == "D1")
scr.delete()

# ---- RingButton --------------------------------------------------------------

scr = screen()
taps = []
holds = []
ring = RingButton(scr, 100, 100, 56, BLACK, text="R", on_press=lambda b: taps.append(1),
                  on_hold=lambda b, held: holds.append(held), hit=88)
_headless.refresh()
x, y = point_at(ring.obj)
_headless.touch(x, y, True, 40)
_headless.touch(x, y, False, 40)
check("a tap on a ring button calls on_press once", taps == [1] and holds == [], "%s %s" % (taps, holds))
_headless.touch(x + 40, y, True, 40)
_headless.touch(x + 40, y, False, 40)
check("hit= widens where a finger lands", taps == [1, 1], str(taps))
_headless.touch(x, y, True, 40)
_headless.touch(x, y, True, 900)
_headless.touch(x, y, False, 40)
check("a hold reports its start and end, and is not a tap", holds == [True, False] and taps == [1, 1],
      "%s %s" % (holds, taps))
_headless.touch(x, y, True, 40)
_headless.touch(x, y, False, 40)
check("the tap after a hold counts", taps == [1, 1, 1], str(taps))
ring.set_enabled(False)
_headless.touch(x, y, True, 40)
_headless.touch(x, y, False, 40)
check("a disabled ring button ignores taps", taps == [1, 1, 1], str(taps))
ring.set_color(0x00FF00)
check("set_color recolours the ring", ring.obj.get_style_border_color(0).to_int() & 0xFFFFFF == 0x00FF00)
scr.delete()

# ---- SpectrumBars ------------------------------------------------------------

scr = screen()
bars = SpectrumBars(scr, 10, 10, 200, 50, BLACK, bands=10, fall=0.25, floor=2)


def heights():
    bars.obj.update_layout()
    return [b.get_height() for b in bars._bars]


check("silent bars stand at the floor", heights() == [2] * 10, str(heights()))
bars.set_levels([1.0] * 10)
check("a full level fills a bar", heights()[0] == 50, str(heights()))
bars.set_levels([0.0] * 10)
check("a bar falls back by fall per call, not at once", heights()[0] == 2 + int(0.75 * 48 + 0.5), str(heights()))
bars.set_levels([2.0, -1.0])
check("levels are clamped, and missing bands read as silence",
      bars.levels[0] == 1.0 and bars.levels[1] == 0.5 and bars.levels[9] == 0.5, str(bars.levels))
bars.clear()
check("clear drops every bar to the floor", heights() == [2] * 10, str(heights()))
scr.delete()

# ---- EnvelopeView ------------------------------------------------------------


def pixel(x, y):
    """The (red, green, blue) on the display at (*x*, *y*), each 0 to 255."""
    frame = _headless._state["frame"]
    at = (int(y) * 800 + int(x)) * 2
    value = frame[at] | (frame[at + 1] << 8)
    return (value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31


def near(a, b, slack=1.5):
    return abs(a[0] - b[0]) <= slack and abs(a[1] - b[1]) <= slack


scr = screen()
view = EnvelopeView(scr, 20, 30, 240, 160, BLACK, stages=4, sustain=2, maximum=99,
                    rates=(99, 50, 20, 60), levels=(99, 70, 40, 0))
_headless.refresh()
pts = view.points()
check("an envelope turns once per stage, after its start", len(pts) == 5, str(pts))
widths = [pts[i + 1][0] - pts[i][0] for i in range(4)]
check("a faster rate draws a shorter segment",
      widths[0] < widths[3] - view._hold_w < widths[1] < widths[2], str(widths))
check("a higher level draws higher up", pts[1][1] < pts[2][1] < pts[3][1] < pts[4][1], str(pts))
check("the curve starts at the last stage's level", pts[0][1] == pts[4][1], str(pts))
check("the held level runs from the end of the sustain stage to the start of the next",
      view._hold_w > 10 and abs(view._starts[3][0] - pts[3][0] - view._hold_w) < 0.01, str(view._starts))
mid = ((pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2)
check("the curve is drawn where points() says", pixel(20 + mid[0], 30 + mid[1])[0] > 180,
      str(pixel(20 + mid[0], 30 + mid[1])))

view.set_values((0, 0, 0, 0), (99, 0, 99, 0))
slow = view.points()
check("the slowest envelope still fits its window", slow[4][0] <= 240 - 4 and slow[0][0] >= 4, str(slow))
check("the highest and lowest levels fit its window",
      4 <= min(p[1] for p in slow) and max(p[1] for p in slow) <= 160 - 4, str(slow))
view.set_values((150, -3, 50, 50), (200, -1, 50, 0))
check("values past the range are held to it", view.rates[:2] == [99, 0] and view.levels[:2] == [99, 0],
      "%s %s" % (view.rates, view.levels))
view.set_values((99, 50, 20, 60), (99, 70, 40, 0))
view.set_level(1, 20)
check("set_level moves one stage", view.levels == [99, 20, 40, 0] and view.points()[2][1] > pts[2][1])
view.set_rate(1, 99)
check("set_rate moves one stage", view.rates == [99, 99, 20, 60] and view.points()[2][0] < pts[2][0])
view.set_values((99, 50, 20, 60), (99, 70, 40, 0))

_headless.refresh()
view.set_selected(1)
check("selecting a stage redraws it", view.selected == 1 and _headless.refresh() > 0)
lit = pixel(20 + mid[0], 30 + mid[1])
check("the selected stage is drawn in the pointer colour", lit[1] > 180 and lit[2] > 150, str(lit))
view.set_selected(1)
check("selecting it again redraws nothing", _headless.refresh() == 0)
view.set_selected(None)
_headless.refresh()
check("selecting None lights no stage", view.selected is None and pixel(20 + mid[0], 30 + mid[1])[2] < 100)

check("the playhead starts hidden", view.playhead() is None and view._head.has_flag(lv.obj.FLAG.HIDDEN))
view.set_position(1, 0.5)
check("the playhead sits part of the way through its stage",
      near(view.playhead(), mid) and not view._head.has_flag(lv.obj.FLAG.HIDDEN), str(view.playhead()))
view.set_position(2, 1.5)
spot = view.playhead()
check("past the end of the sustain stage it runs along the held level",
      spot[1] == pts[3][1] and pts[3][0] < spot[0] < pts[3][0] + view._hold_w, str(spot))
view.set_position(0, 7)
check("a stage that doesn't hold stops the playhead at its end", near(view.playhead(), pts[1]), str(view.playhead()))
view.set_position(None)
check("set_position(None) hides the playhead", view.playhead() is None and view._cursor.has_flag(lv.obj.FLAG.HIDDEN))

for name, call, error in (
    ("too few rates are refused", lambda: view.set_values((1, 2, 3), (1, 2, 3, 4)), ValueError),
    ("a stage past the last is refused", lambda: view.set_selected(4), IndexError),
    ("a playhead in a stage past the last is refused", lambda: view.set_position(9, 0.5), IndexError),
    ("an envelope with no stages is refused", lambda: EnvelopeView(scr, 0, 0, 100, 60, BLACK, stages=0), ValueError),
    ("a sustain stage past the last is refused",
     lambda: EnvelopeView(scr, 0, 0, 100, 60, BLACK, stages=2, sustain=2), ValueError),
):
    try:
        call()
        check(name, False, "no error")
    except error:
        check(name, True)

plain_view = EnvelopeView(scr, 300, 30, 120, 80, BLACK, stages=2, legend="Amp")
check("an envelope with no values opens flat at zero",
      plain_view.levels == [0, 0] and len({p[1] for p in plain_view.points()}) == 1)
check("an envelope with no sustain draws no held level", plain_view._hold.has_flag(lv.obj.FLAG.HIDDEN))
for name, rates, levels in ENVELOPES:
    plain_view = EnvelopeView(scr, 300, 130, 64, 40, BLACK, stages=4, sustain=2, rates=rates, levels=levels)
    inside = all(0 <= p[0] <= 64 and 0 <= p[1] <= 40 for p in plain_view.points())
    check("the mock's %s envelope fits a 64 x 40 view" % name, inside and _headless.refresh() > 0)
    plain_view.obj.delete()

clock = MockEnvelope(stages=4, sustain=2, stage_ms=100, hold_ms=200)
seen = [clock.tick(50) for _ in range(12)]
check("the mock envelope walks the stages and waits on the held one",
      [s for s, _ in seen] == [0, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 0] and seen[6] == (2, 1.25), str(seen))
scr.delete()

# A view nobody holds must still draw: LVGL only points at a line's points.
scr = screen()
EnvelopeView(scr, 20, 30, 240, 160, BLACK, stages=4, sustain=2, maximum=99,
             rates=(99, 50, 20, 60), levels=(99, 70, 40, 0))
gc.collect()
bytearray(4096)
_headless.refresh()
check("a view the host doesn't keep still draws its curve", pixel(20 + mid[0], 30 + mid[1])[0] > 180,
      str(pixel(20 + mid[0], 30 + mid[1])))
scr.delete()

# ---- RoutingDiagram ----------------------------------------------------------


def coords(obj):
    area = lv.area_t()
    obj.get_coords(area)
    return area.x1, area.y1, area.x2, area.y2


def apart(a, b):
    return a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]


check("the fixture lists 32 algorithms, each one different", len(ALGORITHMS) == 32 and len(set(ALGORITHMS)) == 32)
check("the algorithms have the carriers they are known for",
      [len(a[1]) for a in ALGORITHMS] == [2, 2, 2, 2, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 3, 3, 4, 4, 4, 5, 5,
                                           3, 3, 3, 4, 4, 5, 6], str([len(a[1]) for a in ALGORITHMS]))
wired = True
for edges, carriers, feedback in ALGORITHMS:
    modulators = {source for source, _ in edges}
    wired = wired and modulators | set(carriers) == {1, 2, 3, 4, 5, 6} and not modulators & set(carriers)
    wired = wired and feedback[0] in (1, 2, 3, 4, 5, 6) and feedback[1] in modulators | {feedback[0]}
check("every operator is a carrier or modulates something, never both", wired)

rows_ok = True
spaced = True
for number in range(1, 33):
    nodes, edges, carriers, feedback = graph(number)
    places = routing_module.arrange(nodes, edges, carriers)
    rows_ok = rows_ok and all(places[c][1] == 0 for c in carriers)
    rows_ok = rows_ok and all(places[s][1] == places[t][1] + 1 for s, t in edges)
    for a in nodes:
        for b in nodes:
            if a < b and places[a][1] == places[b][1]:
                spaced = spaced and abs(places[a][0] - places[b][0]) >= 0.999
check("carriers take the bottom row and each modulator the row above its target", rows_ok)
check("no two nodes of a row share a column", spaced)

fan = routing_module.arrange(*ROUTINGS[2][1:4])
check("a node that modulates several sits over the middle of them", fan["D"] == (fan["B"][0], 1), str(fan))
under = routing_module.arrange((1, 2, 3), ((2, 1), (3, 1)), (1,))
check("a node with several modulators sits under the middle of them",
      under[1][0] == (under[2][0] + under[3][0]) / 2, str(under))
scr = screen()
for name, call in (
    ("edges that loop are refused", lambda: routing_module.arrange((1, 2), ((1, 2), (2, 1)), ())),
    ("an edge to a node that isn't there is refused", lambda: routing_module.arrange((1, 2), ((3, 1),), (1,))),
    ("a carrier that isn't there is refused", lambda: routing_module.arrange((1, 2), ((2, 1),), (5,))),
    ("feedback to a node that isn't there is refused",
     lambda: RoutingDiagram(scr, 0, 0, 100, 80, BLACK, (1, 2), ((2, 1),), (1,), (2, 9))),
):
    try:
        call()
        check(name, False, "no error")
    except ValueError:
        check(name, True)
scr.delete()

for width, height in ((240, 160), (480, 320)):
    fits = True
    clear = True
    named = True
    why = ""
    for number in range(1, 33):
        scr = screen()
        diagram = RoutingDiagram(scr, 30, 40, width, height, BLACK, *graph(number))
        _headless.refresh()
        boxes = [coords(diagram.node(name)) for name in diagram.nodes]
        for i, a in enumerate(boxes):
            if not (a[0] >= 30 and a[1] >= 40 and a[2] < 30 + width and a[3] < 40 + height):
                fits = False
                why = "algorithm %d: %s" % (number, a)
            if a[2] - a[0] < 15 or a[3] - a[1] < 15 or diagram._boxes[diagram.nodes[i]][1] is None:
                named = False
                why = "algorithm %d: %s" % (number, a)
            for b in boxes[i + 1:]:
                if not apart(a, b):
                    clear = False
                    why = "algorithm %d: %s %s" % (number, a, b)
        scr.delete()
    check("all 32 algorithms fit %d x %d" % (width, height), fits, why)
    check("no two boxes touch at %d x %d" % (width, height), clear, why)
    check("every box shows its number at %d x %d" % (width, height), named, why)

scr = screen()
taps = []
diagram = RoutingDiagram(scr, 30, 40, 240, 160, BLACK, *graph(4), on_press=lambda d, name: taps.append(name))
_headless.refresh()
x, y = point_at(diagram.node(5))
_headless.touch(x, y, False, 40)
_headless.touch(x, y, True, 40)
_headless.touch(x, y, False, 40)
check("a tap on a node reports its name", taps == [5], str(taps))
top6 = coords(diagram.node(6))
top5 = coords(diagram.node(5))
between = pixel((top6[0] + top6[2]) // 2, (top6[3] + top5[1]) // 2)
face = pixel(31, 41)
check("a line joins a modulator to its target", between != face, "%s %s" % (between, face))
_headless.refresh()
diagram.set_selected(6)
check("selecting a node redraws it", diagram.selected == 6 and _headless.refresh() > 0)
check("the selected node is lit", pixel(top6[0] + 4, top6[1] + 4)[0] > 180, str(pixel(top6[0] + 4, top6[1] + 4)))
diagram.set_selected(6)
check("selecting it again redraws nothing", _headless.refresh() == 0)
diagram.set_color(2, 0x0000FF)
_headless.refresh()
box2 = coords(diagram.node(2))
check("a node takes a colour", diagram.colors[2] == 0x0000FF and pixel(box2[0] + 4, box2[1] + 4)[2] > 200)
diagram.set_color(2, None)
check("a node goes dark with None", diagram.colors[2] is None)
try:
    diagram.set_selected(9)
    check("a node that isn't there is refused", False, "no error")
except KeyError:
    check("a node that isn't there is refused", True)

before = diagram.obj.get_child_count()
diagram.set_graph(*graph(32))
_headless.refresh()
check("set_graph draws another graph and starts the selection again",
      diagram.selected is None and diagram.places[6] == (5.0, 0) and diagram.obj.get_child_count() != before,
      str(diagram.places))
for name, nodes, edges, carriers, feedback in ROUTINGS:
    diagram.set_graph(nodes, edges, carriers, feedback)
    boxes = [coords(diagram.node(n)) for n in nodes]
    check("the mock's %s graph draws inside the diagram" % name,
          _headless.refresh() > 0 and all(b[0] >= 30 and b[2] < 270 and b[1] >= 40 and b[3] < 200 for b in boxes))
diagram.set_graph((), (), ())
check("an empty graph draws nothing", diagram.obj.get_child_count() == 0 and diagram.nodes == [])
scr.delete()

# A diagram nobody holds must still draw its lines.
scr = screen()
RoutingDiagram(scr, 30, 40, 240, 160, BLACK, *graph(4))
gc.collect()
bytearray(4096)
_headless.refresh()
check("a diagram the host doesn't keep still draws its lines",
      pixel((top6[0] + top6[2]) // 2, (top6[3] + top5[1]) // 2) == between)
scr.delete()

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
