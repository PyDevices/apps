# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the board offers: its ``board_config`` if it has one, and its lazy roles."""


def _optional(name):
    """Import a module that may be absent, but not one that's broken."""
    try:
        return __import__(name)
    except ImportError as e:
        if name in str(e):
            return None
        raise


class Board:
    """The board this program runs on.

    Importing ``board_config`` starts the board's display, so a program that
    makes a `Board` gets one. A board without a display has only
    ``board_peripherals``.

    Attributes:
        config: the ``board_config`` module, or None.
        peripherals: the ``board_peripherals`` module, or None.
        display: ``board_config.display_drv``, or None.
    """

    def __init__(self):
        self.config = _optional("board_config")
        self.peripherals = _optional("board_peripherals")
        self.display = getattr(self.config, "display_drv", None)
        self._roles = getattr(self.peripherals, "PERIPHERALS", frozenset())
        self._factories = getattr(self.peripherals, "FACTORY_ROLES", frozenset())

    def has(self, role):
        """True when the board lists ``role`` (``"audio_out"``, ``"sdcard"``, ...)."""
        return role in self._roles

    def get(self, role):
        """The role's object, or its factory for the audio roles; None if absent.

        Each call through ``board_peripherals`` alone makes a new object, so
        keep what this returns.
        """
        if role not in self._roles:
            return None
        if self.config is not None:
            return getattr(self.config, role)
        factory = getattr(self.peripherals, role)
        return factory if role in self._factories else factory()

    def eager(self, name):
        """A ``board_config`` name such as ``touch_read`` or ``keypad_read``, or None."""
        return getattr(self.config, name, None)
