# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Keys: one keyboard input for every keyboard, and one on-screen keyboard.

A text field gets keys from wherever they come: the computer's keyboard on a
desktop, a USB or Bluetooth keyboard on a board, or the keyboard on the
screen. Hand a field to `attach` and the on-screen keyboard opens when the
field is focused, types into it, and closes on its Enter or the moment a
real keyboard types::

    from appkit import keys

    field = lv.textarea(parent)
    keys.attach(field)

A keyboard that isn't LVGL's own (a USB one on the board's host port) feeds
the same input with `push`, or `hid_key` for a HID keycode as
``usb.host.hid`` reads it. `focus` gives every keypad and encoder to a focus
group (an overlay's, while it's open) and `release` gives them back, so a
board with an encoder or a gamepad and no touch can still reach every
button and type with the on-screen keyboard.
"""

import lvgl as lv

#: The on-screen keyboard's height, as a share of the screen's.
KEYBOARD_PCT = 45

# HID usage -> (the character, with shift), for a US layout.
_HID_CHARS = {
    0x2C: (" ", " "), 0x2D: ("-", "_"), 0x2E: ("=", "+"), 0x2F: ("[", "{"),
    0x30: ("]", "}"), 0x31: ("\\", "|"), 0x33: (";", ":"), 0x34: ("'", '"'),
    0x35: ("`", "~"), 0x36: (",", "<"), 0x37: (".", ">"), 0x38: ("/", "?"),
}  # fmt: skip
_SHIFTED_DIGITS = "!@#$%^&*()"
# HID usage -> LVGL key, for the keys that aren't characters.
_HID_KEYS = {
    0x28: "ENTER", 0x58: "ENTER", 0x29: "ESC", 0x2A: "BACKSPACE", 0x2B: "NEXT",
    0x4A: "HOME", 0x4C: "DEL", 0x4D: "END", 0x4F: "RIGHT", 0x50: "LEFT",
    0x51: "DOWN", 0x52: "UP",
}  # fmt: skip
_SHIFT_BITS = 0x22  # LEFT_SHIFT and RIGHT_SHIFT in a HID report's modifier byte


def hid_char(usage, modifiers=0):
    """What a HID keyboard *usage* types: a character, an LVGL key code
    (``lv.KEY.ENTER``), or None for a key with nothing to type (F1, Shift)."""
    shift = bool(modifiers & _SHIFT_BITS)
    if 0x04 <= usage <= 0x1D:
        ch = chr(ord("a") + usage - 0x04)
        return ch.upper() if shift else ch
    if 0x1E <= usage <= 0x27:
        i = (usage - 0x1E + 1) % 10
        return _SHIFTED_DIGITS[i - 1] if shift else str(i)
    if usage in _HID_CHARS:
        return _HID_CHARS[usage][1 if shift else 0]
    if usage in _HID_KEYS:
        return getattr(lv.KEY, _HID_KEYS[usage])
    return None


# -- the merged input ---------------------------------------------------------

_queue = []   # (key, pressed) waiting for LVGL to read
_state = {"indev": None, "last": 0}


def _read(indev, data):
    if _queue:
        key, pressed = _queue.pop(0)
        _state["last"] = key
        data.key = key
        data.state = lv.INDEV_STATE.PRESSED if pressed else lv.INDEV_STATE.RELEASED
        data.continue_reading = bool(_queue)
    else:
        data.key = _state["last"]
        data.state = lv.INDEV_STATE.RELEASED


def indev():
    """The keypad input that `push` feeds, made the first time."""
    if _state["indev"] is None:
        i = lv.indev_create()
        i.set_type(lv.INDEV_TYPE.KEYPAD)
        i.set_read_cb(_read)
        group = _groups[-1] if _groups else lv.group_get_default()
        if group is not None:
            i.set_group(group)
        _state["indev"] = i
    return _state["indev"]


def push(key):
    """Type *key* into whatever has focus: a character (``"a"``) or an LVGL
    key code (``lv.KEY.ENTER``). A real keyboard typing closes the on-screen one."""
    indev()
    code = ord(key) if isinstance(key, str) else key
    _queue.append((code, True))
    _queue.append((code, False))
    hide()


def hid_key(usage, modifiers=0):
    """`push` what a HID keyboard's key down types; returns it, or None for a
    key that types nothing."""
    key = hid_char(usage, modifiers)
    if key is not None:
        push(key)
    return key


# -- focus groups ---------------------------------------------------------------

_groups = []   # the groups given the keys, newest last
_own = []      # [(input, its group)] from before the first of them


def _inputs():
    """Every keypad and encoder LVGL has."""
    probe = lv.indev_create()   # LVGL lists the newest first, so from it is all of them
    out = []
    i = probe.get_next()
    while i is not None:
        if i.get_type() in (lv.INDEV_TYPE.KEYPAD, lv.INDEV_TYPE.ENCODER):
            out.append(i)
        i = i.get_next()
    probe.delete()
    return out


def focus(group):
    """Send every keypad and encoder to *group* until `release` gives it up:
    an overlay calls it when it opens."""
    inputs = _inputs()
    if not _groups:
        _own[:] = [(i, i.get_group()) for i in inputs]
    _groups.append(group)
    for i in inputs:
        i.set_group(group)


def release(group):
    """Give the keypads and encoders up: to the overlay opened before *group*
    when one is still open, otherwise back to the groups they had."""
    if group not in _groups:
        return
    _groups.remove(group)
    if _groups:
        for i in _inputs():
            i.set_group(_groups[-1])
    else:
        for i, old in _own:
            i.set_group(old)
        del _own[:]


def focused_group():
    """The group keys go to now: the newest `focus`, or LVGL's default."""
    return _groups[-1] if _groups else lv.group_get_default()


# -- the on-screen keyboard -----------------------------------------------------

_kb = {"board": None, "field": None}


def keyboard():
    """The on-screen keyboard: one, on ``lv.layer_top()``, made hidden the first time."""
    if _kb["board"] is None:
        kb = lv.keyboard(lv.layer_top())
        kb.set_size(lv.pct(100), lv.pct(KEYBOARD_PCT))
        kb.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        kb.add_flag(lv.obj.FLAG.HIDDEN)
        kb.add_event_cb(lambda e: hide(), lv.EVENT.READY, None)
        kb.add_event_cb(lambda e: hide(), lv.EVENT.CANCEL, None)
        # It outlives the app running when it was first needed.
        from . import scope

        scope.keep(kb)
        _kb["board"] = kb
    return _kb["board"]


def is_shown():
    kb = _kb["board"]
    return kb is not None and not kb.has_flag(lv.obj.FLAG.HIDDEN)


def show(field):
    """Open the on-screen keyboard on *field*, an ``lv.textarea``."""
    kb = keyboard()
    _kb["field"] = field
    kb.set_textarea(field)
    kb.remove_flag(lv.obj.FLAG.HIDDEN)
    kb.move_foreground()
    # An encoder walks the keys: the keyboard takes the focus, in editing
    # mode. Not now: LVGL can't move the focus inside the field's own focus event.
    _later(_take_focus)


def _later(fn):
    t = lv.timer_create(lambda t: fn(), 0, None)
    t.set_repeat_count(1)


def _take_focus():
    kb = _kb["board"]
    group = focused_group()
    if group is None or not is_shown():
        return
    group.add_obj(kb)
    lv.group_focus_obj(kb)
    group.set_editing(True)


def hide():
    """Close the on-screen keyboard, if it's open; the field keeps its text and focus."""
    kb = _kb["board"]
    if kb is None or kb.has_flag(lv.obj.FLAG.HIDDEN):
        return
    kb.add_flag(lv.obj.FLAG.HIDDEN)
    field = _kb["field"]
    _kb["field"] = None
    kb.set_textarea(None)
    group = focused_group()
    if group is not None:
        group.set_editing(False)
        lv.group_remove_obj(kb)
        if field is not None:
            lv.group_focus_obj(field)


def _field_event(e):
    code = e.get_code()
    field = e.get_target_obj()
    if code == lv.EVENT.CLICKED or (code == lv.EVENT.FOCUSED and _by_keys()):
        if not is_shown() or _kb["field"] is not field:
            show(field)
    elif code == lv.EVENT.KEY:
        # A real keyboard is typing here: the screen's is in the way.
        hide()
    elif code == lv.EVENT.DELETE and _kb["field"] is field:
        # Going with its app: the keyboard lets go of it now, or the next
        # show() has LVGL touch the freed field.
        _kb["field"] = None
        hide()
    elif code == lv.EVENT.DEFOCUSED and _kb["field"] is field:
        # LVGL says who has the focus only after this event, and can't move
        # it from inside one: look on the next tick.
        _later(_hide_if_left)


def _by_keys():
    """Whether a keypad or an encoder moved the focus. A field first in a new
    group is focused by LVGL itself, and a tap opens the keyboard on its own."""
    i = lv.indev_active()
    return i is not None and i.get_type() in (lv.INDEV_TYPE.KEYPAD, lv.INDEV_TYPE.ENCODER)


def _hide_if_left():
    field = _kb["field"]
    group = focused_group()
    if field is None or group is None:
        return
    now = group.get_focused()
    if now != field and not _keyboard_has_focus():
        hide()


def _keyboard_has_focus():
    group = focused_group()
    return group is not None and _kb["board"] is not None and group.get_focused() == _kb["board"]


def attach(field):
    """Open the on-screen keyboard when *field* (an ``lv.textarea``) is
    focused or tapped, and close it when a real keyboard types there."""
    # One callback for every event: the binding crashes when one function is
    # added for several codes.
    field.add_event_cb(_field_event, lv.EVENT.ALL, None)
    return field
