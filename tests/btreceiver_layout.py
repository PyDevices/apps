# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Check that Bluetooth Receiver's screen fits every display size, in one interpreter.

    python tests/btreceiver_layout.py   (from tests/, with lib/ and the root on the path)

The screen is built in the app areas appkit's status bar leaves on a
320 x 240, 480 x 320 and 800 x 480 display and on round 240 x 240 and
480 x 480 panels. In each, while pairing, playing a track, ringing and on a
call, every widget that shows has to lie inside the area, inside the circle
on a round panel, and clear of its Home button. Prints PASS or FAIL per size
and state, then ALL PASSED.
"""

import sys

sys.path.insert(0, "..")
sys.path.insert(0, "../lib")  # ahead of tests/, whose appkit folder would hide the real one

import lvgl as lv  # noqa: E402

import _headless  # noqa: E402

_headless.display(800, 800)

from apps.btreceiver import screen as screenmod  # noqa: E402

# The app area on each display: (width, height, round, calls setting in the app's area).
AREAS = (
    (800, 440, False, False),  # 800 x 480 under the status bar
    (800, 416, False, True),   # 800 x 480 under a 64-pixel header, the setting in the app's area
    (480, 288, False, True),   # 480 x 320 under the status bar
    (320, 188, False, True),   # 320 x 240 under the status bar and its status row
    (240, 240, True, True),    # round, under the compact cap
    (480, 480, True, True),
)
SLACK = 1  # pixels a box may stray, for rounding

failures = []


def check(name, ok, why=""):
    if ok:
        print("PASS " + name)
    else:
        print("FAIL %s: %s" % (name, why))
        failures.append(name)


class _Scope:
    header = None
    status = None

    def __init__(self, root):
        self.root = root


def shown(obj):
    return not obj.has_flag(lv.obj.FLAG.HIDDEN)


def boxes(obj, out):
    """Every shown descendant of *obj*, with its screen coordinates."""
    for i in range(obj.get_child_count()):
        child = obj.get_child(i)
        if not shown(child):
            continue
        a = lv.area_t()
        child.get_coords(a)
        if a.x2 >= a.x1 and a.y2 >= a.y1:
            out.append((child, a.x1, a.y1, a.x2, a.y2))
        boxes(child, out)
    return out


def strays(root, w, h, lay):
    """What shows outside the area, outside the circle or under the Home button."""
    bad = []
    r = w / 2
    for obj, x1, y1, x2, y2 in boxes(root, []):
        if (x2 - x1 + 1, y2 - y1 + 1) == (w, h):
            continue  # the call card's backdrop fills the area
        where = "%d,%d-%d,%d" % (x1, y1, x2, y2)
        if x1 < -SLACK or y1 < -SLACK or x2 > w - 1 + SLACK or y2 > h - 1 + SLACK:
            bad.append("off the area: " + where)
            continue
        if not lay.round:
            continue
        for x, y in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            if ((x + 0.5 - r) ** 2 + (y + 0.5 - r) ** 2) ** 0.5 > r + SLACK:
                bad.append("outside the circle: " + where)
                break
        else:
            hx, hy, d = lay.home
            if x1 < hx + d and x2 >= hx and y1 < hy + d and y2 >= hy:
                bad.append("under the Home button: " + where)
    return bad


def noop(*args):
    pass


ON = {k: noop for k in ("play", "next", "previous", "seek", "repeat", "shuffle", "volume", "answer", "hangup",
                        "mute", "route")}
LINK = {"codec": "SBC", "sample_rate": 44100, "channel_mode": "joint stereo", "battery": "normal",
        "rssi_delta": -12}

for w, h, round_, switch in AREAS:
    root = lv.obj(lv.screen_active())
    root.remove_style_all()
    root.set_pos(0, 0)
    root.set_size(w, h)
    scr = screenmod.Screen(root, (w, h), ON, switch=switch, round_=round_)
    lay = scr.lay
    if switch:
        screenmod.calls_switch(_Scope(root), False, noop, lay)
    size = "%dx%d%s" % (w, h, " round" if round_ else "")

    def look(state, root=root, w=w, h=h, lay=lay, size=size):
        root.update_layout()
        bad = strays(root, w, h, lay)
        check("%s, %s: everything inside" % (size, state), not bad, "; ".join(bad[:4]))

    scr.show_pairing("pydevices-speaker", "0000")
    look("pairing")
    scr.show_source("Galaxy S21", LINK)
    scr.show_phone(4, 3, True)
    scr.show_track("Paper Satellites (Extended Mix) and a title longer than any screen",
                   "The Low Hum", "Orbit Theory", 1, 14, "Electronic")
    scr.show_status("playing")
    scr.show_modes("single", "all")
    scr.show_position(61000, 365000)
    scr.show_volume(80)
    look("playing")
    check("%s: the title, transport and volume show" % size,
          shown(scr.title) and shown(scr.play.obj) and shown(scr.prev.obj) and shown(scr.next.obj)
          and shown(scr.vol))
    scr.show_modes(None, None)
    look("playing, no modes")
    scr.show_call("incoming", "+1 206 555 0143", "Galaxy S21", False, False, True)
    look("ringing")
    scr.show_call("active", "+1 206 555 0143", "Galaxy S21", True, False, True)
    scr.show_call_time(61000)
    look("on a call")
    scr.show_call(None, None, None, False, False, True)
    root.delete()

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
