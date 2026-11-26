# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch on real LVGL with no window: the place is drawn, the chameleon
walks, changes colour and answers a finger, and closing lets every picture go.

    micropython -X heapsize=24M tests/perch_contract.py

``PERCH_PLANT`` swaps in a fault that a check below must catch;
test_perch.py runs each one.
"""

import os
import sys

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
# lib for appkit, whose glass controls the dock is drawn with
sys.path[:0] = [_HERE + "/../lib", _HERE + "/../apps", _HERE]

import lvgl as lv

import _headless

W, H = 480, 320
frame = _headless.display(W, H)
_headless.pointer()

import perch
from perch import stage as stagemod

PLANT = os.getenv("PERCH_PLANT")
PLANTS = ("no_paint", "hidden", "same_colours", "no_walk", "deaf", "hoard", "leak")
# One more where the decoders work in memory of their own (CPython's svgio only takes the argument).
ROOMY = sys.implementation.name != "cpython"
if ROOMY:
    PLANTS += ("cramped",)

# a small allowance, so keeping to it is tested without drawing megabytes
ALLOWED = 700 * 1024
stagemod.CACHE_BYTES = ALLOWED
Stage = stagemod.Stage

if PLANT == "no_paint":
    Stage._shapes = lambda self: stagemod.Doc()
elif PLANT == "hidden":
    _put = Stage._put

    def _put_nowhere(self, frame, spec):
        _put(self, frame, spec)
        self.huey.add_flag(lv.obj.FLAG.HIDDEN)

    Stage._put = _put_nowhere
elif PLANT == "same_colours":
    for place in stagemod.PLACES.values():
        if place["schemes"]:
            place["schemes"] = dict.fromkeys(place["schemes"], "leaf")
elif PLANT == "no_walk":
    stagemod.STRIDE = 0.0
    stagemod.PLACES["coast"]["walk"] = (0, 0)
elif PLANT == "deaf":
    Stage.hit = lambda self, x, y: False
elif PLANT == "hoard":
    stagemod.CACHE_BYTES = 1 << 30
elif PLANT == "leak":
    Stage.close = lambda self: None
elif PLANT == "cramped" and ROOMY:
    stagemod.POSE_MEMORY = 8192
elif PLANT is not None:
    raise SystemExit("no such plant: %r" % PLANT)


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)


class Scope:
    """As much of an appkit scope as the app uses."""

    def __init__(self):
        self.size = (W, H)
        self.root = lv.obj(None)
        lv.screen_load(self.root)
        self.ticks = []
        self.closers = []

    def every(self, ms, callback):
        self.ticks.append(callback)

    def on_close(self, fn):
        self.closers.append(fn)


scope = Scope()
perch.main(scope)
stage, dock = scope.perch


def step(n=1):
    for _ in range(n):
        for tick in scope.ticks:
            tick()
        _headless.advance(stagemod.TICK_MS)
        _headless.refresh()


def settle(limit=200):
    step()
    while stage.busy and limit:
        step()
        limit -= 1
    check(not stage.busy, "a change of place, colours or view finishes")


def pixel(x, y):
    i = (y * W + x) * 2
    return frame[i] | (frame[i + 1] << 8)


def colours(points):
    return [pixel(x, y) for x, y in points]


def tap(x, y):
    _headless.touch(x, y, True, 0)
    step(2)
    _headless.touch(x, y, False, 0)
    step(3)


# Before the first tick the screen is one colour; a second later it is the coast.
step(0)
settle()
corners = ((5, 5), (W - 6, 5), (5, H - 6), (W - 6, H - 6), (W // 2, H // 2))
check(len(set(colours(corners))) >= 3, "the place is drawn into the picture behind everything")

# The chameleon is on the screen, over his perch.
check(not stage.huey.has_flag(lv.obj.FLAG.HIDDEN), "the chameleon is shown once the place is drawn")
ox, oy = stage._origin()
check(0 < ox < W and 0 < oy <= H, "the chameleon's perch is on this screen")
body = (int(ox), int(oy - H * 0.12))
summer_body = pixel(*body)
summer_sky = pixel(W // 2, 8)

# Another season: the place is redrawn, and the chameleon takes his colours.
check(stage.next_variant(), "the next variant is taken when nothing else is being drawn")
check(not stage.next_view(), "a second change waits for the first")
settle()
check(stage.variant == "autumn" and stage.scheme == "sunset", "the coast's next season is autumn, in sunset colours")
check(pixel(W // 2, 8) != summer_sky, "the sky is redrawn for the season")
check(pixel(*body) != summer_body, "the chameleon's colours change with the season")
check(not [n for n in stagemod.huey.COLORS if ">" in n], "the blended schemes are dropped after the change")

# A walk carries him along the perch, and he ends standing.
start = stage.huey.get_x()
stage.cues[:] = ["stroll"]
furthest = 0
walked = False
for _ in range(160):
    step()
    furthest = max(furthest, abs(stage.huey.get_x() - start))
    walked = walked or (stage.pose is not None and stage.pose[0] == "walk")
check(walked and furthest > W // 30, "a stroll moves the chameleon along his perch")
check(stage.stats["first_walk_ms"] is not None, "the stage notes when he first walked")
stage.cues[:] = []
step(60)

# A finger on him is answered; a finger elsewhere brings the buttons.
ox, oy = stage._origin()
check(dock.left == 0, "the buttons are away until the screen is touched")
tap(int(ox), int(oy - H * 0.12))
step(12)
check(stage.pose == ("happy",), "touched, the chameleon is pleased")
check(dock.left == 0, "a touch on the chameleon doesn't bring the buttons")
tap(6, 6)
check(dock.left > 0 and not dock.bar.has_flag(lv.obj.FLAG.HIDDEN), "a touch anywhere else brings the buttons")
area = lv.area_t()
dock.buttons[0].get_coords(area)
tap((area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2)
settle()
check(stage.place == "bench", "the first button goes to the next place")
step(4500 // stagemod.TICK_MS)
check(dock.bar.has_flag(lv.obj.FLAG.HIDDEN), "the buttons go away again, left alone")

# Closer views draw only what the screen shows, and old poses make room for new.
# the allowance, and beside it the pose on screen and the one just drawn
allowance = len(stage._ground) + ALLOWED + 2 * W * H * 3
for view in ("mid", "close", "wide"):
    check(stage.go(view=view), "another view is taken")
    settle()
    for variant in ("brand", "copper"):
        stage.go(variant=variant)
        settle()
        stage.cues[:] = ["look", "blink", "look"]
        step(120)
    check(stage.held_bytes() <= allowance, "the pictures held stay within the allowance in the %s view" % view)
    check(stage._shown[0].header.w <= W and stage._shown[0].header.h <= H, "a pose is never larger than the screen in the %s view" % view)
check(stage.stats["peak"] <= allowance, "the most ever held stayed within the allowance")
check(stage.stats["swaps"] >= 6, "each change of colours was made by swapping them as svgio drew")
if ROOMY:
    # every place and pose so far was drawn inside its decoder's own memory
    check(0 < stage.stats["place_memory"] <= stagemod.PLACE_MEMORY, "a place fits its decoder's working memory")
    check(0 < stage.stats["pose_memory"] <= stagemod.POSE_MEMORY, "a pose fits its decoder's working memory")

# The desk, where he sleeps at night and a finger doesn't wake him.
stage.go("desk", "night")
settle()
check(stage.pose == ("sleep",), "at the desk at night he is asleep")

# Closing lets go of every picture.
for fn in scope.closers:
    fn()
scope.root.delete()
check(not stage._frames and stage._shown is None and stage.held_bytes() <= len(stage._ground), "closing drops every pose")
print("ok")
