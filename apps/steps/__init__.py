# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Steps: today's steps, what you're doing, and the accelerometer live.

It needs a board whose ``accelerometer`` counts steps (a BMA423 with its
feature firmware, as the T-Watch S3's config sets it up). Reset steps
starts the count again. On a board whose accelerometer doesn't count, it
still shows the live reading.
"""

import sys

import lvgl as lv

from touchkit import ui


def _column(root):
    root.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    root.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    root.set_style_pad_row(8, 0)
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)


def main(scope):
    board = sys.modules.get("board_config")
    accel = None
    if board is not None and "accelerometer" in getattr(board, "PERIPHERALS", ()):
        try:
            accel = board.accelerometer
        except Exception as e:
            ui.missing(scope, "No accelerometer", "The accelerometer didn't answer: %r" % (e,))
            return
    if accel is None:
        ui.missing(scope, "No accelerometer", "This board has no accelerometer.")
        return
    counts = hasattr(accel, "steps") and getattr(accel, "features_running", True)
    root = scope.root
    _column(root)
    steps = ui.label(root, "-", ui.huge, ui.WHITE)
    doing = ui.label(root, "" if counts else "This accelerometer doesn't count steps", ui.small, ui.MUTED)
    live = ui.label(root, "", ui.small, ui.MUTED)
    if counts:
        ui.button(root, "Reset steps", accel.reset_steps, color=ui.PANEL)

    def tick(_t=None):
        try:
            if counts:
                steps.set_text("%d" % accel.steps)
                doing.set_text(str(accel.activity))
            x, y, z = accel.acceleration
            live.set_text("x %+.2f  y %+.2f  z %+.2f g" % (x, y, z))
        except OSError as e:
            live.set_text("read failed: %r" % (e,))

    scope.every(250, tick)
    tick()
