# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The shared controls' contract, run on whichever interpreter runs this file.

Builds each control on a display with no window and drives it the way a host
and a hand do. Prints one ``PASS name`` or ``FAIL name: why`` line per check,
and exits 1 if anything failed. ``--plant`` makes a slider stop reporting its
changes, so the callback checks must fail: that is how test_controls.py knows
they can.

    micropython controls_contract.py [--plant]
"""

import sys

import _headless
import lvgl as lv

PLANT = "--plant" in sys.argv[1:]

_headless.display(800, 480)
_headless.pointer()

from controlkit import LampButton, LedMeter, PadGrid, Slider  # noqa: E402
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

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
