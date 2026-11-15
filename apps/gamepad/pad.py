# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The on-screen gamepad's state, and the USB report it sends.

The report is the one ``usb_hid.Device.GAMEPAD`` takes, seven bytes: sixteen
buttons as a little-endian mask (bit 0 is button 1), the hat (0 centred, 1
north to 8 north-west, clockwise), then X, Y, Z and Rz from -127 to 127.
Nothing here draws or touches USB, so the same code runs in the tests.
"""

import math
import struct

#: The buttons on the pad, by the HID button number each one sends.
A, B, X, Y = 1, 2, 3, 4
L, R = 5, 6
SELECT, START = 7, 8

#: Where a press inside the d-pad counts as no direction, as a share of its radius.
DEAD = 0.3


def hat_at(dx, dy, radius):
    """The hat direction for a touch *dx*, *dy* from the d-pad's centre (y
    grows downwards): 0 north to 7 north-west, clockwise, or None inside the
    dead zone."""
    if dx * dx + dy * dy < (DEAD * radius) ** 2:
        return None
    # Clockwise from north, in eighths, each centred on its direction.
    turn = math.atan2(dx, -dy) / (2 * math.pi)
    return int(turn * 8 + 8.5) % 8


def stick_at(dx, dy, radius):
    """``(x, y)`` from -127 to 127 for a touch *dx*, *dy* from the stick's
    centre; a touch past the rim reads as the rim in the same direction."""
    d = math.sqrt(dx * dx + dy * dy)
    if d > radius:
        dx, dy = dx * radius / d, dy * radius / d
    return round(dx * 127 / radius), round(dy * 127 / radius)


class Pad:
    """What is held on the pad: buttons, the hat and the stick."""

    def __init__(self):
        self.buttons = 0
        self.hat = None
        self.x = 0
        self.y = 0

    def press(self, number):
        self.buttons |= 1 << number - 1

    def release(self, number):
        self.buttons &= ~(1 << number - 1)

    def report(self):
        """The seven bytes ``Device.GAMEPAD.send_report`` takes."""
        hat = 0 if self.hat is None else self.hat + 1
        return struct.pack("<HBbbbb", self.buttons & 0xFFFF, hat, self.x, self.y, 0, 0)


class Sender:
    """Sends the pad's report to a host when it changes.

    *device* is ``usb_hid.Device.GAMEPAD``, or anything with its
    ``send_report``. A report that couldn't go, because no host has the
    board yet or the host stopped taking reports, is sent again by the next
    `send`, so the host always ends up with what the pad holds.
    """

    def __init__(self, pad, device):
        self.pad = pad
        self.device = device
        self.sent = None
        self.count = 0
        self.error = None

    def send(self):
        """Send the report if the host doesn't have it yet. Returns True when one went."""
        report = self.pad.report()
        if report == self.sent:
            return False
        try:
            self.device.send_report(report)
        except OSError as e:
            self.error = str(e) or type(e).__name__
            return False
        self.sent = report
        self.count += 1
        self.error = None
        return True
