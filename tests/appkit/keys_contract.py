# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's keys on real LVGL with no window: the merged keypad, the
on-screen keyboard and the focus groups.

    python tests/appkit/keys_contract.py
    micropython tests/appkit/keys_contract.py

A text field is typed into from a stand-in USB keyboard, tapped with a
pointer, and reached and typed into with a wheel. ``KEYS_SHOTS=<folder>``
saves the screen with the keyboard open as a raw RGB565 frame.
``KEYS_PLANT=<name>`` breaks the keys one way from `PLANTS`, and the checks
must then fail. Exits 1 if a check fails, 2 if LVGL isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [_ROOT + "/lib", _TESTS]

try:
    import lvgl as lv
except ImportError as e:
    print("can't run the keys checks:", e)
    sys.exit(2)

import _headless
from appkit import keys

SW, SH = 480, 320
failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


# -- plants -------------------------------------------------------------------


def _plant_no_shift():
    real = keys.hid_char
    keys.hid_char = lambda usage, modifiers=0: real(usage, 0)


def _plant_keyboard_stays():
    # Typing on a real keyboard leaves the on-screen one open.
    real = keys._field_event

    def field_event(e):
        if e.get_code() != lv.EVENT.KEY:
            real(e)

    keys._field_event = field_event

    def push(key):
        keys._queue.append((ord(key) if isinstance(key, str) else key, True))
        keys._queue.append((ord(key) if isinstance(key, str) else key, False))

    keys.push = push


def _plant_focus_ignored():
    # Nothing moves the inputs between groups.
    keys._inputs = lambda: []


def _plant_encoder_cant_type():
    # The keyboard opens but never takes the wheel.
    keys._take_focus = lambda: None


def _plant_keyboard_holds_dead_field():
    # A field deleted under the open keyboard is never let go.
    real = keys._field_event

    def field_event(e):
        if e.get_code() != lv.EVENT.DELETE:
            real(e)

    keys._field_event = field_event


PLANTS = {
    "keyboard_holds_dead_field": _plant_keyboard_holds_dead_field,
    "no_shift": _plant_no_shift,
    "keyboard_stays": _plant_keyboard_stays,
    "focus_ignored": _plant_focus_ignored,
    "encoder_cant_type": _plant_encoder_cant_type,
}
plant = os.getenv("KEYS_PLANT")
if plant:
    PLANTS[plant]()


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def centre(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2


def tap(obj):
    x, y = centre(obj)
    _headless.touch(x, y, True, 50)
    _headless.touch(x, y, False, 50)


# -- what a HID keyboard types ---------------------------------------------------

SHIFT = 0x02
check(keys.hid_char(0x04) == "a" and keys.hid_char(0x04, SHIFT) == "A", "a letter, and with shift")
check(keys.hid_char(0x1E) == "1" and keys.hid_char(0x27) == "0" and keys.hid_char(0x1E, SHIFT) == "!"
      and keys.hid_char(0x27, SHIFT) == ")", "digits and their shifted marks")
check(keys.hid_char(0x2D, 0x20) == "_" and keys.hid_char(0x38) == "/" and keys.hid_char(0x2C) == " ",
      "punctuation, right shift too")
check(keys.hid_char(0x28) == lv.KEY.ENTER and keys.hid_char(0x2A) == lv.KEY.BACKSPACE
      and keys.hid_char(0x50) == lv.KEY.LEFT, "Enter, Backspace and the arrows are LVGL's keys")
check(keys.hid_char(0x3A) is None and keys.hid_char(0xE1) is None, "F1 and Shift type nothing")

# -- a field and the keyboard ----------------------------------------------------

_headless.display(SW, SH)
_headless.pointer()
scr = lv.obj(None)
lv.screen_load(scr)
group = lv.group_create()
field = lv.textarea(scr)
field.set_one_line(True)
field.set_width(300)
field.align(lv.ALIGN.TOP_MID, 0, 10)
other = lv.button(scr)
other.align(lv.ALIGN.TOP_LEFT, 0, 70)
keys.attach(field)
group.add_obj(other)
group.add_obj(field)
keys.focus(group)

tap(field)
check(keys.is_shown(), "tapping the field opens the keyboard")
check(keys.keyboard().get_textarea() == field, "on that field")
_headless.refresh()
if os.getenv("KEYS_SHOTS"):
    _headless.save_raw(os.getenv("KEYS_SHOTS") + "/keyboard.raw", SW, SH)

# A real keyboard types: the keys land and the screen's keyboard gets out of the way.
lv.group_focus_obj(field)
for usage, mods in ((0x0B, SHIFT), (0x0C, 0), (0x1E, SHIFT)):   # H i !
    keys.hid_key(usage, mods)
settle()
check(field.get_text() == "Hi!", "a USB keyboard types: %r" % (field.get_text(),))
check(not keys.is_shown(), "and the on-screen keyboard closes")
keys.push(lv.KEY.BACKSPACE)
settle()
check(field.get_text() == "Hi", "Backspace through the same input: %r" % (field.get_text(),))

# Enter on the keyboard closes it.
keys.show(field)
keys.keyboard().send_event(lv.EVENT.READY, None)
check(not keys.is_shown(), "the keyboard's Enter closes it")

# -- an encoder, and no touch -------------------------------------------------------

wheel = _headless.wheel(group)
keys.focus(group)   # the wheel was made after: focus gives it the group too
lv.group_focus_obj(other)
settle()
check(not keys.is_shown(), "nothing open while the button has focus")
_headless.turn(1)
check(group.get_focused() == keys.keyboard() and keys.is_shown(),
      "turning onto the field opens the keyboard and gives it the wheel")
before = field.get_text()
_headless.turn(2)   # the first turn picks a key ("1#", which changes the layout), the next "q"
_headless._wheel["pressed"] = True
_headless.advance(60)
_headless._wheel["pressed"] = False
_headless.advance(60)
check(len(field.get_text()) == len(before) + 1, "a press types the key under the wheel: %r" % (field.get_text(),))
keys.keyboard().send_event(lv.EVENT.READY, None)
check(not keys.is_shown() and group.get_focused() == field, "closing it gives the field the focus back")

# -- focus and release ---------------------------------------------------------------

overlay = lv.group_create()
elsewhere = lv.textarea(scr)
elsewhere.align(lv.ALIGN.BOTTOM_MID, 0, -10)
overlay.add_obj(elsewhere)
keys.focus(overlay)
lv.group_focus_obj(field)
keys.push("x")
settle()
check(elsewhere.get_text() == "x" and not field.get_text().endswith("x"),
      "an overlay's group takes the keys while it's open")
turned = overlay.get_focused()
_headless.turn(1)
check(group.get_focused() == field, "and the wheel's turns: the app's focus stays put")
keys.release(overlay)
keys.push("y")
settle()
check(field.get_text().endswith("y") and elsewhere.get_text() == "x", "release gives the keys back")

# Two overlays, the first closed before the second: the keys still end up home.
first, second = lv.group_create(), lv.group_create()
first_field, second_field = lv.textarea(scr), lv.textarea(scr)
first.add_obj(first_field)
second.add_obj(second_field)
keys.focus(first)
keys.focus(second)
keys.release(first)
keys.push("s")
settle()
check(second_field.get_text() == "s", "the open overlay keeps the keys when the one under it closes")
keys.release(second)
keys.push("h")
settle()
check(field.get_text().endswith("h") and first_field.get_text() == "", "and they go home when it closes too")

# A field deleted while the keyboard is open on it, as when its app closes:
# the keyboard closes and lets go, and opens on the next field safely.
doomed = keys.attach(lv.textarea(scr))
keys.show(doomed)
settle()
doomed.delete()
settle()
closed = not keys.is_shown() and keys._kb["field"] is None
check(closed, "a field deleted under the keyboard closes it")
if closed:  # otherwise the keyboard points at the freed field: LVGL would crash on it
    check(not keys.keyboard().get_textarea(), "and the keyboard lets go of it")
    keys.show(field)
    settle()
    check(keys.is_shown() and keys.keyboard().get_textarea() == field, "the next field opens it again")
    keys.hide()

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
