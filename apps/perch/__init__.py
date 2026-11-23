# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey's Perch: Huey the chameleon at the coast, a workbench and a desk, drawn as vectors.

Every picture is shapes built in Python and drawn by svgio at this screen's
size. Touch the chameleon and he answers. Touch anywhere else for four
buttons: the next place, the next season or time of day (at the workbench,
the next set of colours), a closer view of the same drawing, and something
for him to do.
"""

import lvgl as lv
from icons import lvgl as lvicons

from .stage import TICK_MS, Stage

_DOCK_TICKS = 4000 // TICK_MS  # the buttons stay this long after the last touch
_FADE_TICKS = 8
_GLASS = 0x0B2A4A
_LIME = 0xC4DC4C
_TURNS = ("tongue", "stroll", "hold", "turn", "look")  # what the star asks for, by turns


class _Dock:
    """Four round buttons down the right side, there when touched and gone soon after.

    The chameleon keeps to the left and the middle of every place, so this
    side is the one he is never behind.
    """

    def __init__(self, root, size, actions):
        w, h = size
        side = max(34, min(56, min(w, h) // 8))
        gap = side // 4
        self.bar = lv.obj(root)
        self.bar.remove_style_all()
        self.bar.set_size(side + 2 * gap, len(actions) * side + (len(actions) + 1) * gap)
        self.bar.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.bar.set_style_bg_color(lv.color_hex(_GLASS), 0)
        self.bar.set_style_bg_opa(170, 0)
        self.bar.remove_flag(lv.obj.FLAG.SCROLLABLE)
        # clear of a round screen's edge
        self.bar.align(lv.ALIGN.RIGHT_MID, -max(8, w // 28), 0)
        self.buttons = []
        for i, (icon, action) in enumerate(actions):
            button = lv.obj(self.bar)
            button.remove_style_all()
            button.set_size(side, side)
            button.set_pos(gap, gap + i * (side + gap))
            button.set_style_radius(lv.RADIUS_CIRCLE, 0)
            button.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
            button.set_style_bg_opa(36, 0)
            button.set_style_bg_color(lv.color_hex(_LIME), lv.STATE.PRESSED)
            button.set_style_bg_opa(150, lv.STATE.PRESSED)
            button.add_flag(lv.obj.FLAG.CLICKABLE)
            button.remove_flag(lv.obj.FLAG.SCROLLABLE)
            image = lvicons.image(button, icon, 24, lv.color_white())
            image.center()
            image.remove_flag(lv.obj.FLAG.CLICKABLE)
            button.add_event_cb(self._pressed(action), lv.EVENT.CLICKED, None)
            self.buttons.append(button)
        self.left = 0
        self.bar.add_flag(lv.obj.FLAG.HIDDEN)

    def _pressed(self, action):
        def on_click(_event):
            self.show()
            action()

        return on_click

    def show(self):
        self.left = _DOCK_TICKS
        self.bar.set_style_opa(255, 0)
        self.bar.remove_flag(lv.obj.FLAG.HIDDEN)

    def tick(self):
        if self.left <= 0:
            return
        self.left -= 1
        if self.left == 0:
            self.bar.add_flag(lv.obj.FLAG.HIDDEN)
        elif self.left < _FADE_TICKS:
            self.bar.set_style_opa(255 * self.left // _FADE_TICKS, 0)


def main(scope):
    root = scope.root
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    root.set_style_pad_all(0, 0)
    root.set_style_border_width(0, 0)
    root.set_style_bg_color(lv.color_hex(_GLASS), 0)
    root.set_style_bg_opa(255, 0)
    stage = Stage(root, scope.size)
    turn = [-1]

    def something():
        turn[0] = (turn[0] + 1) % len(_TURNS)
        stage.cues.append(_TURNS[turn[0]])

    dock = _Dock(
        root,
        scope.size,
        (
            ("photo_library", stage.next_place),
            ("wb_sunny", stage.next_variant),
            ("search", stage.next_view),
            ("star", something),
        ),
    )

    point = lv.point_t()

    def touched(_event):
        indev = lv.indev_active()
        if indev is None:
            return
        indev.get_point(point)
        if not stage.tap(point.x, point.y):
            dock.show()

    root.add_flag(lv.obj.FLAG.CLICKABLE)
    root.add_event_cb(touched, lv.EVENT.CLICKED, None)

    def tick(_timer=None):
        stage.tick()
        dock.tick()

    scope.every(TICK_MS, tick)
    scope.on_close(stage.close)
    # for whoever drives the app from outside: a test, a screenshot script
    scope.perch = (stage, dock)
