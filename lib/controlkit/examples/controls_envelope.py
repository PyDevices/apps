# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Show an envelope as a curve, with a stage lit and a playhead moving.

Draws a four-stage rate and level envelope in an EnvelopeView. A playhead
runs through the stages and waits on the held level, the stage it is in is
lit, and every few seconds the view changes to the next shape in the mock's
list. The name of each shape is printed as it appears.

Needs: LVGL and a board_config with a display, which a PyDevices board
package or omnipython-desktop provides.

Run it:

    micropython controls_envelope.py

Tested on: the unix port of MicroPython and CPython 3.12 on Linux, each in
an SDL window.
"""

from display_driver import app  # noqa: F401  (opens the display and LVGL)

import lvgl as lv

from controlkit import EnvelopeView
from controlkit._safe import safe
from controlkit.mock import ENVELOPES, MockEnvelope
from controlkit.theme import BLACK

# Change these to match your setup.
TICK_MS = 40  # how often the playhead moves
SHAPE_MS = 6000  # how long each shape stays
SUSTAIN = 2  # the stage whose level holds

# Fill the screen with the faceplate colour and leave a margin round the view.
screen = lv.screen_active()
screen.set_style_bg_color(lv.color_hex(BLACK["face"]), 0)
display = lv.display_get_default()
width = display.get_horizontal_resolution()
height = display.get_vertical_resolution()
margin = max(4, width // 20)

# Build the view on the first shape. The mock's values run 0 to 127, which
# is the view's own range.
name, rates, levels = ENVELOPES[0]
view = EnvelopeView(screen, margin, margin, width - 2 * margin, height - 2 * margin, BLACK,
                    stages=4, sustain=SUSTAIN, legend="Envelope", rates=rates, levels=levels)
print("envelope", name)

# The mock stands in for an engine that says where its envelope has got to.
engine = MockEnvelope(stages=4, sustain=SUSTAIN)
state = {"shape": 0, "elapsed": 0}


# Move the playhead, light the stage it is in, and change shape now and then.
def step(_timer):
    stage, fraction = engine.tick(TICK_MS)
    view.set_position(stage, fraction)
    view.set_selected(stage)
    state["elapsed"] += TICK_MS
    if state["elapsed"] >= SHAPE_MS:
        state["elapsed"] = 0
        state["shape"] = (state["shape"] + 1) % len(ENVELOPES)
        shape_name, shape_rates, shape_levels = ENVELOPES[state["shape"]]
        view.set_values(shape_rates, shape_levels)
        print("envelope", shape_name)


timer = lv.timer_create(safe(step), TICK_MS, None)

# It runs until you close the window.
app.run()
