# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Turn a footswitch's presses and releases into taps, holds and double taps.

A `Pedal` is told when the switch goes down and up, and asked now and then
how long it has been held. It answers with gestures:

- ``"tap"``: pressed and let go before ``hold_ms``. It fires on the release,
  at once: a fill shouldn't wait to find out whether a second tap follows.
- ``"double"``: a second press within ``double_ms`` of a tap's release. It
  fires on that press, and its release says nothing more. What the first tap
  started is still waiting for its bar line, so a double tap replaces it.
- ``"hold"``: still down after ``hold_ms``. It fires once, while held, so the
  player hears the change coming without lifting the foot first.

Times are milliseconds from any clock that counts up (``time.ticks_ms()``
on a board). Nothing here touches a pin, a timer or the screen, so it is
checked with numbers alone.

Example::

    pedal = Pedal()
    pedal.press(1000)        # []
    pedal.release(1120)      # ["tap"]
    pedal.press(1300)        # ["double"]
"""

try:
    from time import ticks_diff
except ImportError:  # CPython
    def ticks_diff(a, b):
        return a - b

HOLD_MS = 400
DOUBLE_MS = 350

#: What `Pedal.state` says, for a screen to show.
UP = "up"
DOWN = "down"
HELD = "held"


class Pedal:
    """One footswitch's gestures. See the module docstring."""

    def __init__(self, hold_ms=HOLD_MS, double_ms=DOUBLE_MS):
        self.hold_ms = hold_ms
        self.double_ms = double_ms
        self.down_at = None       # when the switch went down, while it is down
        self.held = False         # a hold has fired for this press
        self.spent = False        # this press was a double tap: its release says nothing
        self.tapped_at = None     # the last tap's release, for a double tap
        #: The last gesture, and what the switch is doing now.
        self.last = None

    @property
    def state(self):
        """``"up"``, ``"down"`` or ``"held"``."""
        if self.down_at is None:
            return UP
        return HELD if self.held else DOWN

    def press(self, now):
        """The switch went down at ``now``. Returns the gestures it makes."""
        if self.down_at is not None:
            return []             # a key's auto-repeat, or a bounce
        self.down_at = now
        self.held = False
        self.spent = False
        if self.tapped_at is not None and ticks_diff(now, self.tapped_at) <= self.double_ms:
            self.tapped_at = None
            self.spent = True
            return self._say("double")
        return []

    def release(self, now):
        """The switch came up at ``now``. Returns the gestures it makes."""
        if self.down_at is None:
            return []
        out = []
        if not (self.held or self.spent):
            # A hold that hasn't been polled yet is still a hold.
            if ticks_diff(now, self.down_at) >= self.hold_ms:
                out = self._say("hold")
            else:
                self.tapped_at = now
                out = self._say("tap")
        self.down_at = None
        self.held = False
        self.spent = False
        return out

    def poll(self, now):
        """Call often while the switch may be down. Returns ``["hold"]`` once,
        when it has been down ``hold_ms``."""
        if self.down_at is None or self.held or self.spent:
            return []
        if ticks_diff(now, self.down_at) >= self.hold_ms:
            self.held = True
            self.tapped_at = None
            return self._say("hold")
        return []

    def _say(self, gesture):
        self.last = gesture
        return [gesture]
