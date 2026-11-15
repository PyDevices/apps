# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Gamepad: be a USB game controller, or test one.

On a board with a USB device port (an ESP32-S2, S3 or P4), the screen is a
gamepad: a d-pad, a stick, A, B, X and Y, two shoulder buttons, Select and
Start. Plug the port into a computer or into another board's host port and
it's a game controller with sixteen buttons, a hat and four axes. The touch
panel reads one finger, so one control moves at a time.

On a board with a USB host port, it shows the gamepad plugged into it as it
changes: each button lights while it's held, the sticks and the hat move,
and every axis has a bar. Any HID gamepad or joystick works, whatever its
layout, apart from the ones that need a start-up message first (a DualShock
4, a Switch Pro controller).

A board that can do both asks which. The gamepad needs ``usb-hid`` and the
tester ``usb-host-hid``, which ``omip.install("usb-host-hid")`` puts in
``/lib``.
"""

import lvgl as lv
from multimer import ticks_diff, ticks_ms
from touchkit import ui

from .pad import A, B, L, R, SELECT, START, X, Y, Pad, Sender, hat_at, stick_at
from .watch import AXIS_NAMES, Watch

#: How often the screen catches up with the pad or the tester, in ms.
TICK_MS = 20
#: The face buttons: number, label, colour and place in the diamond (column, row).
FACE = (
    (Y, "Y", 0xE0A030, (1, 0)),
    (X, "X", 0x3A7BD5, (0, 1)),
    (B, "B", 0xD9483B, (2, 1)),
    (A, "A", 0x3BA55C, (1, 2)),
)
#: The hat's eight directions as the d-pad arrows they light: up, right, down, left.
LIT = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0), (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1))
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def sides():
    """What this board can be: ``"device"`` with a USB device port,
    ``"host"`` with a USB host port, in that order."""
    out = []
    try:
        import machine

        if hasattr(machine, "USBDevice"):
            out.append("device")
    except ImportError:
        pass
    try:
        import _usbhost

        if hasattr(_usbhost, "host_start"):
            out.append("host")
    except ImportError:
        pass
    return out


def _zone(parent, x, y, size, color=None):
    """A round, touchable area that keeps the press while the finger slides off it."""
    o = ui.plain(lv.obj(parent))
    o.set_pos(x, y)
    o.set_size(size, size)
    o.set_style_radius(lv.RADIUS_CIRCLE, 0)
    o.set_style_bg_color(color or ui.PANEL, 0)
    o.set_style_bg_opa(lv.OPA.COVER, 0)
    o.add_flag(lv.obj.FLAG.CLICKABLE)
    o.add_flag(lv.obj.FLAG.PRESS_LOCK)
    o.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
    return o


def _touch_offset(obj):
    """Where the finger is, from *obj*'s centre."""
    p = lv.point_t()
    lv.indev_active().get_point(p)
    a = lv.area_t()
    obj.get_coords(a)
    return p.x - (a.x1 + a.x2) // 2, p.y - (a.y1 + a.y2) // 2


def _on_press(obj, cb):
    """Call ``cb(True)`` while *obj* is pressed or the finger moves on it, and
    ``cb(False)`` when it lets go."""

    def ev(e):
        code = e.get_code()
        cb(code == lv.EVENT.PRESSED or code == lv.EVENT.PRESSING)

    for code in (lv.EVENT.PRESSED, lv.EVENT.PRESSING, lv.EVENT.RELEASED, lv.EVENT.PRESS_LOST):
        obj.add_event_cb(ev, code, None)


def _pad_button(parent, text, x, y, w, h, color, radius, number, st):
    b, lbl = ui.button(parent, text, lambda: None, w=w, h=h, font=ui.big, color=lv.color_hex(color))
    b.set_pos(x, y)
    b.set_style_radius(radius, 0)
    b.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
    # A ring while it's held, since the finger covers the button.
    b.set_style_outline_width(4, lv.STATE.PRESSED)
    b.set_style_outline_color(ui.WHITE, lv.STATE.PRESSED)
    b.set_style_outline_pad(3, lv.STATE.PRESSED)

    def held(down):
        if down:
            st["pad"].press(number)
        else:
            st["pad"].release(number)
        st["send"]()

    _on_press(b, held)
    st["buttons"][number] = b
    return b


def be_gamepad(scope):
    """The screen as a gamepad on the board's USB device port."""
    root = scope.root
    W, H = scope.size
    status = ui.status(scope)
    try:
        import usb_hid
    except ImportError as e:
        ui.missing(scope, "missing: %s" % e, 'The gamepad needs usb-hid: omip.install("usb-hid").')
        return None
    usb_hid.enable((usb_hid.Device.GAMEPAD,))
    scope.on_close(usb_hid.disable)  # the port is the board's serial port alone again

    pad = Pad()
    sender = Sender(pad, usb_hid.Device.GAMEPAD)
    st = {"pad": pad, "sender": sender, "shown": None, "buttons": {}}

    def send():
        sender.send()
        show()

    st["send"] = send

    # The shoulders above, then the d-pad, the stick and the face buttons.
    m = max(8, W // 60)
    top = max(44, H // 7)
    s = min((W - 4 * m) // 3, H - top - 3 * m)
    y0 = top + 2 * m + (H - top - 3 * m - s) // 2
    side_w = max(80, W // 6)
    _pad_button(root, "L", m, m, side_w, top, 0x2A3550, 12, L, st)
    _pad_button(root, "R", W - m - side_w, m, side_w, top, 0x2A3550, 12, R, st)
    mid_w = max(70, W // 8)
    _pad_button(root, "Select", W // 2 - mid_w - m // 2, m, mid_w, top, 0x1A2030, top // 2, SELECT, st)
    _pad_button(root, "Start", W // 2 + m // 2, m, mid_w, top, 0x1A2030, top // 2, START, st)

    dpad = _zone(root, m, y0, s)
    arrows = []
    for sym, align, dx, dy in (
        (lv.SYMBOL.UP, lv.ALIGN.TOP_MID, 0, s // 10),
        (lv.SYMBOL.RIGHT, lv.ALIGN.RIGHT_MID, -s // 10, 0),
        (lv.SYMBOL.DOWN, lv.ALIGN.BOTTOM_MID, 0, -s // 10),
        (lv.SYMBOL.LEFT, lv.ALIGN.LEFT_MID, s // 10, 0),
    ):
        a = ui.label(dpad, sym, ui.huge, ui.MUTED)
        a.align(align, dx, dy)
        arrows.append(a)

    def dpad_moved(down):
        pad.hat = hat_at(*_touch_offset(dpad), s // 2) if down else None
        lit = LIT[pad.hat] if pad.hat is not None else (0, 0, 0, 0)
        for a, on in zip(arrows, lit):
            a.set_style_text_color(ui.ACCENT if on else ui.MUTED, 0)
        send()

    _on_press(dpad, dpad_moved)
    st["dpad"] = dpad

    stick = _zone(root, (W - s) // 2, y0, s)
    knob_d = s * 2 // 5
    knob = ui.plain(lv.obj(stick))
    knob.set_size(knob_d, knob_d)
    knob.set_style_radius(lv.RADIUS_CIRCLE, 0)
    knob.set_style_bg_color(ui.KEY, 0)
    knob.set_style_bg_opa(lv.OPA.COVER, 0)
    knob.remove_flag(lv.obj.FLAG.CLICKABLE)
    knob.center()
    reach = (s - knob_d) // 2

    def stick_moved(down):
        pad.x, pad.y = stick_at(*_touch_offset(stick), reach) if down else (0, 0)
        knob.align(lv.ALIGN.CENTER, pad.x * reach // 127, pad.y * reach // 127)
        knob.set_style_bg_color(ui.ACCENT if down else ui.KEY, 0)
        send()

    _on_press(stick, stick_moved)
    st["stick"] = stick

    fx = W - m - s
    cell = s // 3
    for number, text, color, (col, row) in FACE:
        _pad_button(root, text, fx + col * cell + 4, y0 + row * cell + 4, cell - 8, cell - 8, color,
                    lv.RADIUS_CIRCLE, number, st)

    def show():
        if sender.error is not None:
            text = "no host yet: plug the USB port into a computer or a host board"
        else:
            held = [str(n) for n in range(1, 17) if pad.buttons >> n - 1 & 1]
            text = "buttons %s   hat %s   stick %d, %d   %d sent" % (
                " ".join(held) or "-", COMPASS[pad.hat] if pad.hat is not None else "-", pad.x, pad.y, sender.count)
        if text != st["shown"]:
            st["shown"] = text
            status.set_text(text)

    def tick(_t=None):
        # A report the host didn't take goes again until it does.
        send()

    tick()
    scope.every(250, tick)
    return st


def _square(parent, x, y, size, title):
    """A stick's square, with a dot that shows where it is. Returns the dot."""
    box = ui.box(parent, x, y, size, size)
    box.set_style_pad_all(0, 0)
    cap = ui.label(box, title, ui.tiny, ui.MUTED)
    cap.align(lv.ALIGN.TOP_LEFT, 6, 4)
    for w, h in ((size - 16, 1), (1, size - 16)):
        line = ui.plain(lv.obj(box))
        line.set_size(w, h)
        line.set_style_bg_color(ui.KEY, 0)
        line.set_style_bg_opa(lv.OPA.COVER, 0)
        line.center()
    dot = ui.plain(lv.obj(box))
    dot.set_size(size // 7, size // 7)
    dot.set_style_radius(lv.RADIUS_CIRCLE, 0)
    dot.set_style_bg_color(ui.ACCENT, 0)
    dot.set_style_bg_opa(lv.OPA.COVER, 0)
    dot.center()
    return dot, (size - size // 7) // 2


def _pairs(axes):
    """The sticks to draw as squares: (X, Y), then (Rx, Ry) or (Z, Rz)."""
    out = []
    for a, b in ((0x010030, 0x010031), (0x010033, 0x010034), (0x010032, 0x010035)):
        if a in axes and b in axes and len(out) < 2:
            out.append((a, b))
    return out


def test_gamepad(scope):
    """The gamepad on the board's USB host port, live."""
    root = scope.root
    W, H = scope.size
    status = ui.status(scope)
    try:
        import usb.core
        from usb.host import hid_generic
    except ImportError as e:
        ui.missing(scope, "missing: %s" % e, 'The tester needs usb-host-hid: omip.install("usb-host-hid").')
        return None
    # A gamepad is a full-speed device, and full speed reaches one behind a
    # hub too. A host that already ran at high speed since power-up can't
    # change on a board whose hub can't be power-cycled, so it stays there.
    try:
        usb.core.start(full_speed=True, classes=("hid",))
    except OSError as e:
        if e.errno != 95:  # EOPNOTSUPP: an earlier app ran the host at high speed
            raise
        usb.core.start(classes=("hid",))
    watch = Watch(usb.core, hid_generic)
    st = {"watch": watch, "layout": None, "view": None, "shown": None}

    def close():
        watch.close()
        usb.core.stop()

    scope.on_close(close)

    body = ui.plain(lv.obj(root))
    body.set_size(W, H)
    hint = ui.label(body, "Plug a gamepad into the USB host port.", ui.font, ui.MUTED)
    hint.center()

    def build(layout):
        """Widgets for this pad's buttons, sticks, hats and axes."""
        body.clean()
        buttons, axes, hats = layout
        m = max(8, W // 60)
        view = {"lamps": {}, "dots": [], "bars": {}, "values": {}, "hat": None}
        pairs = _pairs(axes)
        # The buttons along the bottom, in rows of up to sixteen.
        cols = min(16, len(buttons)) or 1
        bw = min(56, (W - m) // cols - 6)
        rows = (len(buttons) + cols - 1) // cols
        lamps_y = H - m - rows * (bw + 6) + 6
        for i, n in enumerate(buttons):
            lamp = ui.box(body, m + (i % cols) * (bw + 6), lamps_y + (i // cols) * (bw + 6), bw, bw, ui.KEY)
            lamp.set_style_pad_all(0, 0)
            ui.label(lamp, str(n), ui.small, ui.WHITE).center()
            view["lamps"][n] = lamp
        # Above them the sticks and the hat as squares, then a bar for each axis.
        top = lamps_y - 2 * m
        count = len(pairs) + (1 if hats else 0)
        sq = max(0, min(top - len(axes) * 28 - m, (W - m) // count - m)) if count else 0
        x = (W - count * (sq + m) + m) // 2
        for a, b in pairs:
            dot, reach = _square(body, x, m, sq, "%s / %s" % (AXIS_NAMES[a], AXIS_NAMES[b]))
            view["dots"].append((dot, reach, a, b))
            x += sq + m
        if hats:
            hb = ui.box(body, x, m, sq, sq)
            hb.set_style_pad_all(0, 0)
            ui.label(hb, "Hat", ui.tiny, ui.MUTED).align(lv.ALIGN.TOP_LEFT, 6, 4)
            marks = []
            for i, name in enumerate(COMPASS):
                lbl = ui.label(hb, name, ui.small, ui.MUTED)
                dx, dy = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))[i]
                lbl.align(lv.ALIGN.CENTER, dx * sq * 3 // 10, 6 + dy * sq * 3 // 10)
                marks.append(lbl)
            view["hat"] = marks
            x += sq + m
        x = m
        y = m + sq + (m if sq else 0)
        bar_h = max(16, min(36, (top - y + m) // max(1, len(axes))))
        for code in axes:
            name = ui.label(body, AXIS_NAMES.get(code, "%06x" % code), ui.small, ui.MUTED)
            name.set_pos(x, y + (bar_h - 22) // 2)
            bar = lv.bar(body)
            bar.set_mode(lv.bar.MODE.SYMMETRICAL)
            bar.set_range(-100, 100)
            bar.set_value(0, False)
            bar.set_pos(x + 70, y + bar_h // 4)
            bar.set_size(W - x - m - 70 - 52, bar_h // 2)
            value = ui.label(body, "", ui.small, ui.WHITE)
            value.set_pos(W - m - 46, y + (bar_h - 22) // 2)
            view["bars"][code] = bar
            view["values"][code] = value
            y += bar_h
        return view

    def draw():
        view = st["view"]
        if view is None:
            return
        held = watch.buttons
        for n, lamp in view["lamps"].items():
            lamp.set_style_bg_color(ui.ACCENT if n in held else ui.KEY, 0)
        axes = watch.axes
        for dot, reach, a, b in view["dots"]:
            dot.align(lv.ALIGN.CENTER, int((axes.get(a) or 0) * reach), int((axes.get(b) or 0) * reach))
        for code, bar in view["bars"].items():
            v = axes.get(code)
            bar.set_value(int((v or 0) * 100), False)
            raw = watch.pad.axes.get(code) if watch.pad is not None else None
            view["values"][code].set_text("" if raw is None else str(raw))
        if view["hat"] is not None:
            d = watch.hats.get(0, -1)
            for i, lbl in enumerate(view["hat"]):
                lbl.set_style_text_color(ui.ACCENT if i == d else ui.MUTED, 0)

    def tick(_t=None):
        changed = watch.poll(ticks_ms(), ticks_diff)
        if watch.layout != st["layout"]:
            st["layout"] = watch.layout
            if watch.layout is None:
                body.clean()
                st["view"] = None
                ui.label(body, "Plug a gamepad into the USB host port.", ui.font, ui.MUTED).center()
            else:
                st["view"] = build(watch.layout)
            changed = True
        if changed:
            draw()
        text = watch.status if watch.pad is None else "%s   %d events" % (watch.name, watch.events)
        if text != st["shown"]:
            st["shown"] = text
            status.set_text(text)

    tick()
    scope.every(TICK_MS, tick)
    return st


def main(scope):
    can = sides()
    if not can:
        ui.missing(scope, "no USB port for this", "Gamepad needs a board with a USB device port (to be a gamepad) "
                   "or a USB host port (to test one), such as an ESP32-S3 or ESP32-P4.")
        return
    if len(can) == 1:
        (be_gamepad if can[0] == "device" else test_gamepad)(scope)
        return
    # Both: ask which, once.
    root = scope.root
    W, H = scope.size
    ui.status(scope).set_text("choose one")
    bw, bh = min(340, (W - 64) // 2), min(200, H - 80)

    def pick(fn):
        # Not from inside the button's own click: cleaning the root deletes it.
        root.add_flag(lv.obj.FLAG.HIDDEN)

        def start(_t=None):
            root.clean()
            root.remove_flag(lv.obj.FLAG.HIDDEN)
            fn(scope)

        scope.after(10, start)

    for i, (title, text, fn) in enumerate((
        ("Be a gamepad", "for a computer or a host board on the USB device port", be_gamepad),
        ("Test a gamepad", "plugged into this board's USB host port", test_gamepad),
    )):
        b, lbl = ui.button(root, title, lambda fn=fn: pick(fn), w=bw, h=bh, font=ui.big, color=ui.PANEL)
        b.align(lv.ALIGN.CENTER, (bw // 2 + 16) * (2 * i - 1), 0)
        lbl.align(lv.ALIGN.TOP_MID, 0, 20)
        sub = ui.label(b, text, ui.small, ui.MUTED)
        sub.set_width(bw - 32)
        sub.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        sub.align(lv.ALIGN.BOTTOM_MID, 0, -20)
