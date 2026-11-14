# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Clock: an analog clock that fills the screen, on the time at your chosen place."""

import lvgl as lv
from deskkit import forecast, localtime

from .face import AnalogClock

FACE = "Grand Classic"
_TICK_MS = 200  # the second hand is at most this late


def main(scope):
    root = scope.root
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    clock = AnalogClock(root, scope.size, localtime.clock_time, FACE)

    # A clock showing a wrong time looks right, so say so until it's been set.
    waiting = lv.label(root)
    waiting.set_text("Setting the time")
    waiting.set_style_text_color(lv.color_hex(clock.skin["second"]), 0)
    waiting.set_style_text_font(lv.font_montserrat_16, 0)
    waiting.align(lv.ALIGN.CENTER, 0, 70)

    def tick(_timer=None):
        clock.update_time()
        if localtime.is_set():
            waiting.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            waiting.remove_flag(lv.obj.FLAG.HIDDEN)

    scope.every(_TICK_MS, tick)
    tick()
    # The board sets its clock when it joins a network (touchkit.net); the
    # forecast's reply is what gives the chosen place's offset. Without a place
    # the clock shows UTC.
    forecast.keep_fresh(scope)
