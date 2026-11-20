# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw the 32 six-operator FM algorithms, one after another.

Shows each algorithm from routing_algorithms.py in a RoutingDiagram:
modulators stacked over what they modulate, the carriers along the bottom
joined to one output, and the feedback loop in its own colour. The diagram
changes every two seconds and prints the algorithm's number. Tap an
operator to light it, and its number is printed.

Needs: LVGL and a board_config with a display, which a PyDevices board
package or omnipython-desktop provides, and routing_algorithms.py beside
this file.

Run it:

    micropython controls_routing.py

Tested on: the unix port of MicroPython and CPython 3.12 on Linux, each in
an SDL window.
"""

from display_driver import app  # noqa: F401  (opens the display and LVGL)

import lvgl as lv

from controlkit import RoutingDiagram
from controlkit._safe import safe
from controlkit.theme import BLACK
from routing_algorithms import graph

# Change these to match your setup.
STEP_MS = 2000  # how long each algorithm stays
FIRST = 1  # the algorithm to open on, 1 to 32

# Fill the screen with the faceplate colour and put a caption at the top.
screen = lv.screen_active()
screen.set_style_bg_color(lv.color_hex(BLACK["face"]), 0)
display = lv.display_get_default()
width = display.get_horizontal_resolution()
height = display.get_vertical_resolution()
caption = lv.label(screen)
caption.set_style_text_color(lv.color_hex(BLACK["legend"]), 0)
caption.set_pos(8, 4)


# Light the operator that was tapped.
def pressed(diagram, operator):
    diagram.set_selected(operator)
    print("operator", operator)


# Build the diagram under the caption, with no graph yet.
diagram = RoutingDiagram(screen, 8, 28, width - 16, height - 36, BLACK, on_press=pressed)
state = {"number": FIRST - 1}


# Draw the next algorithm. set_graph() takes the same four arguments as the
# constructor: the nodes, the edges, the carriers and the feedback pair.
def step(_timer):
    state["number"] = state["number"] % 32 + 1
    diagram.set_graph(*graph(state["number"]))
    caption.set_text("Algorithm %d" % state["number"])
    print("algorithm", state["number"])


step(None)
timer = lv.timer_create(safe(step), STEP_MS, None)

# It runs until you close the window.
app.run()
