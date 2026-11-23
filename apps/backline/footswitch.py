# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Play Backline from a switch wired to a pin: a stomp switch, or the
board's own button.

A `Footswitch` reads its pin each time it is polled and tells the box when
the switch has gone down or come up (``on_pedal(which, down)``, the same call
a MIDI switch or a panel's key makes), so taps, holds and double taps are
timed in one place. A contact bounces for a few milliseconds when it closes
and opens, so a new level counts only once it has held for ``settle_ms``.

`open_switches` makes the switches the settings name: ``"switch"`` is
pedal A and ``"switch_b"`` is pedal B, each as

- ``boot_button``: the board's own button, from its ``board_peripherals``.
- ``pin:N``: a switch between GPIO ``N`` and ground, read with the pin's
  pull-up (pressed reads low).
- ``pin:N:high``: a switch that reads high when pressed, with a pull-down.

Example::

    sw = Footswitch(Pin(35, Pin.IN, Pin.PULL_UP), on_pedal=box.pedal)
    sw.poll(now)    # call every few milliseconds
"""

try:
    from time import ticks_diff
except ImportError:  # CPython
    def ticks_diff(a, b):
        return a - b

SETTLE_MS = 8
#: The settings that name a switch, and the pedal each one is.
KEYS = (("switch", 0), ("switch_b", 1))


class Footswitch:
    """One switch on a pin, debounced, as pedal ``which``.

    Args:
        pin: anything with ``value()`` (a ``machine.Pin``).
        which: 0 for pedal A, 1 for pedal B.
        on_pedal: ``on_pedal(which, down)`` when the switch settles down or up.
        active_low: the pin reads 0 while the switch is pressed.
        settle_ms: how long a new level must hold before it counts.
    """

    def __init__(self, pin, which=0, on_pedal=None, active_low=True, settle_ms=SETTLE_MS):
        self.pin = pin
        self.which = which
        self.on_pedal = on_pedal
        self.active_low = active_low
        self.settle_ms = settle_ms
        #: Whether the switch is down, as last told.
        self.down = False
        self._raw = False
        self._since = None

    def _pressed(self):
        v = self.pin.value()
        return not v if self.active_low else bool(v)

    def poll(self, now):
        """Read the pin at ``now`` (ms).

        Returns:
            True when the switch has just settled into a new position, after
            telling ``on_pedal``.
        """
        raw = self._pressed()
        if raw != self._raw or self._since is None:
            self._raw = raw
            self._since = now
        if raw == self.down or ticks_diff(now, self._since) < self.settle_ms:
            return False
        self.down = raw
        if self.on_pedal is not None:
            self.on_pedal(self.which, raw)
        return True


def open_pin(spec):
    """``(pin, active_low)`` for a switch spec (see the module docstring).

    Raises:
        ValueError: The spec isn't one of the forms.
        ImportError: There's no ``machine`` or ``board_peripherals``.
        AttributeError: The board's peripherals have no ``boot_button``.
    """
    if spec == "boot_button":
        import board_peripherals as bp

        return bp.boot_button(), True
    parts = spec.split(":")
    if parts[0] != "pin" or len(parts) not in (2, 3) or not parts[1].isdigit() \
            or (len(parts) == 3 and parts[2] not in ("low", "high")):
        raise ValueError("a switch is boot_button, pin:N or pin:N:high, not %r" % (spec,))
    from machine import Pin

    high = len(parts) == 3 and parts[2] == "high"
    return Pin(int(parts[1]), Pin.IN, Pin.PULL_DOWN if high else Pin.PULL_UP), not high


def open_switches(settings, on_pedal, opener=open_pin):
    """The switches ``settings`` names (``"switch"``, ``"switch_b"``), as
    `Footswitch` objects calling ``on_pedal``. A setting that is missing or
    empty is no switch.

    Raises:
        ValueError, ImportError, AttributeError: From `open_pin`.
    """
    out = []
    for key, which in KEYS:
        spec = settings.get(key)
        if spec:
            pin, active_low = opener(spec)
            out.append(Footswitch(pin, which, on_pedal, active_low))
    return out
