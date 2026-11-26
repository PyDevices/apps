# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch: a home screen for round and small screens, a watch face first.

It opens on a watch face, with the date, the battery where the board has
one, today's steps where it counts them, and whether it's on the network, on
a line under the hands. Swipe left or right for another face; the one you
pick is kept across restarts. A tap, or a swipe up, opens the wheel of
apps (`wheel`); a tap on the time at the top of the wheel, a swipe
sideways, or a few idle seconds go back to the face. The apps are those
Home shows, in the order of its tabs: each app's ``app.json`` says what
it is, as for Home, and an app Home hides stays off the wheel too.

Every app comes back here through the Shell's Home button. The faces are
Clock's analog clock in each of its skins, Grand Classic first, and a
hybrid face with the time in digits too (`faces`).

A board's ``main.py`` makes it the home screen with
``TouchLauncher(app, home="watch")``; Home's own ``main.py`` does that by
itself on a round screen or a small one (see ``appkit.shell.is_small``).
"""

import json
import sys

import lvgl as lv
from deskkit import localtime

from appkit.bar import battery_percent, board_battery
from appkit.shell import is_round
from touchkit import ui

from . import faces
from .wheel import Wheel

DEFAULT_COLOR = "#44505E"
WHEEL_IDLE_MS = 8000  # the wheel goes back to the face after this long untouched
GLANCE_MS = 5000  # how often the line under the face is read again
TICK_MS = 250
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def in_order(info, hidden=()):
    """``[(name, title, category, icon, colour), ...]``: the apps Home puts
    on its tabs, in the same order, from each app's ``app.json``. An app
    with no icon gets the "apps" icon rather than stopping the wheel."""
    by_category = {}
    for name in sorted(info):
        entry = info[name]
        if not entry.get("tile", True) or name in hidden:
            continue
        category = entry.get("category") or "More"
        color = int(entry.get("color", DEFAULT_COLOR)[1:], 16)
        tile = (name, entry.get("title", name), category, entry.get("icon") or "apps", color)
        by_category.setdefault(category, []).append(tile)
    order = sorted(c for c in by_category if c != "More")
    if "More" in by_category:
        order.append("More")
    return [tile for c in order for tile in by_category[c]]


def _role(name):
    """The board's role *name*, or None where it hasn't one or it fails."""
    board = sys.modules.get("board_config")
    if board is None or name not in getattr(board, "PERIPHERALS", ()):
        return None
    try:
        return getattr(board, name)
    except Exception:
        return None


def _battery():
    try:
        return board_battery()
    except Exception:
        return None


def battery_text(battery):
    """``"82%"``, with ``" charging"`` while it charges, as the status bar
    reads it, or None with no reading."""
    if battery is None:
        return None
    try:
        pct = battery_percent(battery)
        charging = getattr(battery, "charging", False)
    except Exception:
        return None
    if pct is None:
        return None
    return "%d%%%s" % (pct, " charging" if charging else "")


def steps_text(accel):
    """``"1234 steps"`` where the accelerometer counts steps, else None."""
    if accel is None or not hasattr(accel, "steps"):
        return None
    try:
        if not getattr(accel, "features_running", True):
            return None
        return "%d steps" % accel.steps
    except Exception:
        return None


def network_text():
    """``"online"`` or ``"offline"``, from the board's network."""
    from touchkit import net

    return "online" if net.ip() else "offline"


def glances():
    """The line under the face: the date, then whatever the board can tell."""
    t = localtime.now()
    parts = ["%s %d %s" % (_WEEKDAYS[t[6] % 7], t[2], _MONTHS[(t[1] - 1) % 12])]
    for text in (battery_text(_battery()), steps_text(_role("accelerometer")), network_text()):
        if text:
            parts.append(text)
    return "  ".join(parts)


def _face_path(scope):
    return scope.data_dir + "/face.json"


def _load_face(scope):
    try:
        with open(_face_path(scope)) as f:
            return json.load(f).get("face", faces.DEFAULT)
    except (OSError, ValueError):
        return faces.DEFAULT


def _save_face(scope, name):
    try:
        with open(_face_path(scope), "w") as f:
            json.dump({"face": name}, f)
    except OSError as e:
        print("watch: the face wasn't saved: %r" % (e,))


def _catcher(parent, w, h):
    """A clear, clickable layer over the whole screen."""
    o = lv.obj(parent)
    o.remove_style_all()
    o.set_size(w, h)
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    o.add_flag(lv.obj.FLAG.CLICKABLE)
    o.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)  # its swipes are its own
    return o


def main(scope):
    root = scope.root
    W, H = scope.size
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    root.set_style_bg_color(lv.color_hex(0x000000), 0)
    root.set_style_bg_opa(lv.OPA.COVER, 0)
    kept = scope.store()
    side = min(W, H)
    state = {"face": None, "name": _load_face(scope), "swiped": False, "glance_at": 0, "idle": 0}

    # -- the face --
    face_view = lv.obj(root)
    face_view.remove_style_all()
    face_view.set_size(W, H)
    face_view.remove_flag(lv.obj.FLAG.SCROLLABLE)
    dial = lv.obj(face_view)
    dial.remove_style_all()
    dial.set_size(side, side)
    dial.center()
    dial.remove_flag(lv.obj.FLAG.SCROLLABLE)
    line = ui.label(face_view, "", ui.tiny, ui.WHITE)
    line.set_style_bg_color(lv.color_hex(0x000000), 0)
    line.set_style_bg_opa(lv.OPA._60, 0)
    line.set_style_pad_hor(8, 0)
    line.set_style_pad_ver(2, 0)
    line.set_style_radius(8, 0)
    line.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    line.set_long_mode(lv.label.LONG_MODE.DOTS)
    # Inside the circle on a round screen: the chord at that height.
    y = H * 4 // 5 - ui.tiny.line_height // 2
    if is_round():
        half = int(((side / 2 - 8) ** 2 - (side / 2 - y - ui.tiny.line_height) ** 2) ** 0.5)
        line.set_style_max_width(max(60, 2 * half), 0)
    else:
        line.set_style_max_width(W - 16, 0)
    catch = _catcher(face_view, W, H)

    def show_face(name):
        dial.clean()
        state["name"] = name
        state["face"] = faces.make(name, dial, side)
        line.move_foreground()
        catch.move_foreground()

    def glance(force=False):
        state["glance_at"] += TICK_MS
        if force or state["glance_at"] >= GLANCE_MS:
            state["glance_at"] = 0
            line.set_text(glances())
            line.update_layout()
            line.align(lv.ALIGN.TOP_MID, 0, y)

    def turn_face(step):
        names = faces.names()
        i = names.index(state["name"]) if state["name"] in names else 0
        name = names[(i + step) % len(names)]
        show_face(name)
        _save_face(scope, name)
        line.set_text(name)  # says which face it is until the next glance
        state["glance_at"] = -GLANCE_MS // 2
        line.update_layout()
        line.align(lv.ALIGN.TOP_MID, 0, y)

    # -- the wheel --
    wheel_view = lv.obj(root)
    wheel_view.remove_style_all()
    wheel_view.set_size(W, H)
    wheel_view.remove_flag(lv.obj.FLAG.SCROLLABLE)
    wheel_view.add_flag(lv.obj.FLAG.HIDDEN)
    wheel_view.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
    launcher = scope.launcher
    apps = in_order(launcher.info, launcher.hidden())
    names = [a[0] for a in apps]
    at = names.index(kept["app"]) if kept.get("app") in names else 0
    wheel = Wheel(wheel_view, W, H, apps, scope.switch, at)
    clock = ui.label(wheel_view, "", ui.small, ui.MUTED)
    clock.add_flag(lv.obj.FLAG.CLICKABLE)
    clock.set_ext_click_area(12)
    clock.align(lv.ALIGN.TOP_MID, 0, 6 if not is_round() else max(6, H // 16))

    def selected(i):
        if 0 <= i < len(apps):
            kept["app"] = apps[i][0]

    wheel.on_select = selected
    selected(wheel.selected)

    def open_wheel():
        t = localtime.now()
        clock.set_text("%d:%02d" % (t[3], t[4]))
        face_view.add_flag(lv.obj.FLAG.HIDDEN)
        wheel_view.remove_flag(lv.obj.FLAG.HIDDEN)
        state["idle"] = 0
        if lv.group_get_default() is not None:
            lv.group_focus_obj(wheel.cont)

    def close_wheel():
        wheel_view.add_flag(lv.obj.FLAG.HIDDEN)
        face_view.remove_flag(lv.obj.FLAG.HIDDEN)
        glance(True)

    # A swipe also ends in a release, which LVGL may report as a click:
    # one press is a swipe or a tap, never both.
    def pressed(e):
        state["swiped"] = False

    def face_gesture(e):
        d = lv.indev_active().get_gesture_dir()
        state["swiped"] = True
        if d == lv.DIR.LEFT:
            turn_face(1)
        elif d == lv.DIR.RIGHT:
            turn_face(-1)
        elif d == lv.DIR.TOP:
            open_wheel()

    def face_tap(e):
        if not state["swiped"]:
            open_wheel()

    catch.add_event_cb(pressed, lv.EVENT.PRESSED, None)
    catch.add_event_cb(face_gesture, lv.EVENT.GESTURE, None)
    catch.add_event_cb(face_tap, lv.EVENT.CLICKED, None)

    def wheel_gesture(e):
        d = lv.indev_active().get_gesture_dir()
        if d in (lv.DIR.LEFT, lv.DIR.RIGHT):
            close_wheel()

    wheel_view.add_event_cb(wheel_gesture, lv.EVENT.GESTURE, None)
    wheel.cont.add_event_cb(wheel_gesture, lv.EVENT.GESTURE, None)
    clock.add_event_cb(lambda e: close_wheel(), lv.EVENT.CLICKED, None)

    # Keys: Enter on the face opens the wheel; the wheel takes them from there.
    group = lv.group_get_default()
    if group is not None:
        group.add_obj(catch)
        group.add_obj(wheel.cont)
        lv.group_focus_obj(catch)

    def face_key(e):
        if e.get_key() == lv.KEY.ENTER:
            open_wheel()

    catch.add_event_cb(face_key, lv.EVENT.KEY, None)

    def tick(_t=None):
        if not face_view.has_flag(lv.obj.FLAG.HIDDEN):
            state["face"].update_time()
            glance()
            return
        t = localtime.now()
        clock.set_text("%d:%02d" % (t[3], t[4]))
        disp = lv.display_get_default()
        if disp is not None and disp.get_inactive_time() > WHEEL_IDLE_MS:
            close_wheel()

    show_face(state["name"])
    glance(True)
    scope.every(TICK_MS, tick)
    tick()
