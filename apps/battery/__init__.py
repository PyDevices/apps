# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Battery: the charge, the battery's voltage, the charger and USB, and the
screen's brightness.

The battery is the board's ``battery`` role, as the status bar reads it. A
charger that can be switched (the AXP2101's) gets a switch; one that can't
is only shown. The brightness slider sets ``display_drv.brightness`` for as
long as the board runs.
"""

import sys

import lvgl as lv
from appkit.bar import battery_percent, board_battery

from touchkit import ui


def lines(battery):
    """What the screen says about *battery*, one line each."""
    out = []
    pct = battery_percent(battery)
    out.append("%d%%" % pct if pct is not None else "No battery")
    v = battery.voltage
    if v is not None:
        out.append("Battery %.2f V" % v)
    state = getattr(battery, "battery_status", None)
    if state is None:
        state = "charging" if getattr(battery, "charging", False) else None
    if state:
        out.append("State: %s" % state)
    vbus = getattr(battery, "vbus_voltage", None)
    if vbus:
        out.append("USB %.2f V" % vbus)
    return out


def main(scope):
    try:
        battery = board_battery()
    except Exception as e:
        ui.missing(scope, "No battery", "The battery didn't answer: %r" % (e,))
        return
    if battery is None:
        ui.missing(scope, "No battery", "This board has no battery reading.")
        return
    root = scope.root
    root.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    root.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    root.set_style_pad_row(8, 0)
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    text = ui.label(root, "", ui.font, ui.WHITE)
    text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    if hasattr(battery, "charger"):
        row = lv.obj(root)
        row.remove_style_all()
        row.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        row.set_style_pad_column(10, 0)
        ui.label(row, "Charge", ui.small, ui.MUTED)
        sw = lv.switch(row)
        try:
            if battery.charger():
                sw.add_state(lv.STATE.CHECKED)
        except Exception:
            pass

        def charge(e):
            battery.charger(sw.has_state(lv.STATE.CHECKED))

        sw.add_event_cb(charge, lv.EVENT.VALUE_CHANGED, None)

    board = sys.modules.get("board_config")
    drv = getattr(board, "display_drv", None)
    if drv is not None and hasattr(drv, "brightness"):
        ui.label(root, "Brightness", ui.small, ui.MUTED)
        slider = lv.slider(root)
        slider.set_width(min(scope.size[0] * 2 // 3, 240))
        slider.set_range(5, 100)
        try:
            slider.set_value(int(drv.brightness * 100), False)
        except Exception:
            slider.set_value(100, False)

        def bright(e):
            drv.brightness = slider.get_value() / 100

        slider.add_event_cb(bright, lv.EVENT.VALUE_CHANGED, None)

    def tick(_t=None):
        try:
            text.set_text("\n".join(lines(battery)))
        except OSError as e:
            text.set_text("read failed: %r" % (e,))

    scope.every(2000, tick)
    tick()
