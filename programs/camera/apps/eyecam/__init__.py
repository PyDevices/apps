# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The ESP32-P4X-EYE's camera app, page for page, on PyDevices.

Buttons: Menu, Up, Down, and the knob (turn and press). On a desktop the
keys stand in: M is Menu, the up and down arrows are Up and Down, Enter is
the knob's press (so is the middle mouse button), and + and - (or the
mouse wheel) are one detent each of the knob; three detents within half a
second make one step. On the board an Encoder device gives the knob
(MOUSEWHEEL, and its button as MOUSEBUTTONDOWN 2) and a Keypad device the
three buttons, with the same key codes. A board with a touch screen also gets
tap zones over the Menu, Up and Down pictures and a vertical swipe for the
knob (``controls.py``).
"""

import appdev
import events
import keys

from . import assets, controls, hw
from .control import Eye
from .settings import Settings

DETENTS = {
    keys.K_PLUS: -1, keys.K_EQUALS: -1, keys.K_KP_PLUS: -1,  # + turns left: closer
    keys.K_MINUS: 1, keys.K_KP_MINUS: 1,  # - turns right: wider
}

eye = None  # the running app, for tests and the REPL


def main(scope):
    global eye
    parts = hw.build(scope)
    board = None
    if not parts.desktop:
        try:
            import board_config as board
        except ImportError:
            pass
    buttons = controls.button_table(keys, board)
    _, use_touch = controls.devices_for(
        [d.type for d in scope.app.devices], parts.desktop)
    if parts.desktop:
        settings = Settings(scope.data_dir + "/settings.json")
    else:
        settings = Settings()
    eye = Eye(scope, settings, parts, touch=use_touch)
    if assets.fallbacks:
        print("eyecam: no KoHo .bin for %s, using Montserrat" % ", ".join(assets.fallbacks))

    def on_key(e):
        name = buttons.get(e.key)
        if name is not None:
            eye.button(name)
            return
        d = DETENTS.get(e.key)
        if d is not None:
            eye.detent(d)
            return
        if parts.desktop:
            desktop_key(e.key)

    def desktop_key(k):
        if eye.hw.sleep.sleeping:
            eye.button("menu")  # any key wakes it
        elif k == keys.K_s:
            parts.storage.card_in = not parts.storage.card_in
            eye.set_sd_card_mounted(parts.storage.card_in)
        elif k == keys.K_f:
            parts.storage.full = not parts.storage.full
        elif k == keys.K_u:
            parts.usb.plug(parts.usb.state != "connected")
        elif k == keys.K_r:
            parts.accel.angle = (parts.accel.angle + 90) % 360

    counts = 1  # counts the knob gives a click; the board config says
    if not parts.desktop:
        try:
            import board_config

            counts = getattr(board_config, "encoder_counts_per_detent", 1)
        except ImportError:
            pass
    acc = [0]

    def on_event(e, *_):  # on a board LVGL's read path adds (indev, data)
        if e.type == events.KEYDOWN:
            on_key(e)
        elif e.type == events.MOUSEWHEEL:
            if e.y:
                # The count climbs clockwise (right). A click is `counts` counts,
                # which can arrive one at a time: gather them.
                acc[0] += e.y
                while abs(acc[0]) >= counts:
                    d = 1 if acc[0] > 0 else -1
                    acc[0] -= d * counts
                    eye.detent(d)
        elif e.type == events.MOUSEBUTTONDOWN and e.button == 2:
            eye.button("encoder")  # the knob's press (an Encoder device's button)

    # LVGL owns the input while it runs, so take the events at the devices
    # themselves: the host window on a desktop, the knob and buttons on the board.
    for dev in scope.app.devices:
        if dev.type in (appdev.HOST, appdev.KEYPAD, appdev.ENCODER):
            scope.subscribe(dev, on_event, (events.KEYDOWN, events.MOUSEWHEEL, events.MOUSEBUTTONDOWN))

    if eye.scaled is not None:
        for dev in scope.app.devices:
            if dev.type == appdev.POINTER:
                scope.subscribe(dev, eye.scaled.pointer,
                                (events.MOUSEBUTTONDOWN, events.MOUSEBUTTONUP, events.MOUSEMOTION))

    def closing():
        global eye
        if eye is not None:
            if eye.recording:
                eye.hw.recorder.stop()
            eye.close()
        eye = None

    scope.on_close(closing)
