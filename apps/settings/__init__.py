# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Settings: what you can change about this board, one card per setting.

Device name is the name the board shows everywhere: its hostname on the
network, its Bluetooth and BLE names, and the USB sound card's name on a
computer. It is saved with ``boarddev.name``, where the board keeps its Wi-Fi
networks, and the radios take it up from the next start. An empty name puts
the board back on its default, ``omnipython-`` and the end of its unique ID.

Wi-Fi power saving lets the radio sleep between the access point's beacons:
it saves battery, and every reply to the board waits for the radio to wake.
It is on by default when a battery is fitted, and while Bluetooth runs, which
needs the radio to sleep to share its antenna; otherwise it's off. A choice
made here is remembered by ``wifi_manager``, and Default forgets it. The card
says which it is. A board without ``wifi_manager`` has no such card.

Each card is built by one function in `CARDS`, so another setting is
another function there.
"""

import lvgl as lv

from appkit import keys
from touchkit import ui

try:
    import boarddev
except ImportError:
    boarddev = None

try:
    import wifi_manager
except ImportError:
    wifi_manager = None  # no Wi-Fi here: no power saving card

GAP = 12
CARD = 0x121826  # Home's card colour
NAME_HINT = "Letters, digits and hyphens, up to %d. Empty goes back to the default. The network and Bluetooth use it from the next start."


def _card(parent, title):
    """A card in the list, with *title* at its top. Returns the card."""
    card = ui.plain(lv.obj(parent))
    card.set_size(lv.pct(100), lv.SIZE_CONTENT)
    card.set_style_bg_color(lv.color_hex(CARD), 0)
    card.set_style_bg_opa(lv.OPA.COVER, 0)
    card.set_style_radius(12, 0)
    card.set_style_pad_all(GAP, 0)
    card.set_style_pad_row(8, 0)
    card.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    ui.label(card, title, ui.font, ui.WHITE)
    return card


def save_name(text):
    """Save *text* as the board's name, or go back to the default when it's
    empty. Returns what to tell the user; a name the board can't take says why."""
    text = text.strip()
    try:
        boarddev.name(text or None)
    except ValueError as e:
        return str(e)
    except OSError as e:  # CircuitPython, with CIRCUITPY mounted on a computer
        return "Not saved: %s" % (e,)
    return "Saved: %s. Restart the board to use it everywhere." % (boarddev.name(),)


def device_name(scope, parent):
    """The Device name card: the name in a field, and Save."""
    card = _card(parent, "Device name")
    row = ui.plain(lv.obj(card))
    row.set_size(lv.pct(100), lv.SIZE_CONTENT)
    row.set_flex_flow(lv.FLEX_FLOW.ROW)
    row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    row.set_style_pad_column(GAP, 0)
    field = lv.textarea(row)
    field.set_one_line(True)
    field.set_max_length(boarddev.NAME_MAX)
    field.set_accepted_chars("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
    field.set_text(boarddev.name())
    field.set_flex_grow(1)
    keys.attach(field)
    said = ui.label(card, NAME_HINT % boarddev.NAME_MAX, ui.small, ui.MUTED)
    said.set_width(lv.pct(100))
    said.set_long_mode(lv.label.LONG_MODE.WRAP)

    def save():
        said.set_text(save_name(field.get_text()))
        field.set_text(boarddev.name())
        keys.hide()

    ui.button(row, "Save", save, color=ui.PANEL)
    # Enter on any keyboard saves too.
    field.add_event_cb(lambda e: save(), lv.EVENT.READY, None)
    return card


def _wifi_call(name):
    """``wifi_manager``'s *name* called, or None where this version hasn't it."""
    fn = getattr(wifi_manager, name, None)
    try:
        return fn() if fn is not None else None
    except Exception:  # a reading that fails says nothing either way
        return None


def power_save_state():
    """``(on, why)``: whether Wi-Fi power saving is on, and why: "Set by you",
    or what makes it the default ("On by default: a battery is fitted")."""
    chosen = (_wifi_call("_settings") or {}).get("power_save")
    bluetooth = _wifi_call("_bluetooth_on")
    if chosen is not None:
        if not chosen and bluetooth:
            return True, "On while Bluetooth runs: it shares the antenna. Off is kept for after."
        return bool(chosen), "Set by you."
    if bluetooth:
        return True, "On by default: Bluetooth is running."
    if wifi_manager.power_save():
        return True, "On by default: a battery is fitted."
    return False, "Off by default: no battery is fitted."


def power_saving(scope, parent):
    """The Wi-Fi power saving card: a switch, why it's on or off, and Default."""
    card = _card(parent, "Wi-Fi power saving")
    row = ui.plain(lv.obj(card))
    row.set_size(lv.pct(100), lv.SIZE_CONTENT)
    row.set_flex_flow(lv.FLEX_FLOW.ROW)
    row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    row.set_style_pad_column(GAP, 0)
    sw = lv.switch(row)
    sw.set_ext_click_area(8)
    why = ui.label(row, "", ui.small, ui.MUTED)
    why.set_flex_grow(1)
    why.set_long_mode(lv.label.LONG_MODE.WRAP)

    def show():
        on, said = power_save_state()
        if on:
            sw.add_state(lv.STATE.CHECKED)
        else:
            sw.remove_state(lv.STATE.CHECKED)
        why.set_text(said)

    def flipped(e):
        wifi_manager.set_power_save(sw.has_state(lv.STATE.CHECKED))
        show()

    def default():
        wifi_manager.set_power_save(None)
        show()

    sw.add_event_cb(flipped, lv.EVENT.VALUE_CHANGED, None)
    ui.button(row, "Default", default, color=ui.PANEL)
    show()
    return card


#: The cards, top to bottom: each a function of (scope, parent) that adds one.
CARDS = [device_name, power_saving]


def main(scope):
    if boarddev is None:
        ui.missing(scope, "no boarddev here", "Settings saves through boarddev,\nwhich comes with OmniPython.")
        return
    W, H = scope.size
    root = scope.root
    root.set_style_bg_color(ui.BG, 0)
    root.set_style_bg_opa(lv.OPA.COVER, 0)
    cards = lv.obj(root)
    cards.set_size(W, H)
    cards.set_style_bg_opa(lv.OPA.TRANSP, 0)
    cards.set_style_border_width(0, 0)
    cards.set_style_radius(0, 0)
    cards.set_style_pad_all(GAP, 0)
    cards.set_style_pad_gap(GAP, 0)
    cards.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    for card in CARDS:
        if card is power_saving and not hasattr(wifi_manager, "set_power_save"):
            continue
        card(scope, cards)
