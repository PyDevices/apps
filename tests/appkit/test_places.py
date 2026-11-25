# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit.places mounting and unmounting the SD card, with each kind of card a
board config hands back.

    python -m unittest discover -s tests/appkit -p test_places.py

The cards are stand-ins with the methods the real ones have: ``machine.SDCard``
on an ESP32 and a USB drive have ``deinit``; micropython-lib's SPI
``sdcard.SDCard`` has only the block device calls.
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")


def _places():
    # By its file: the appkit package brings LVGL and icons, which this needs neither of.
    data = types.SimpleNamespace(desktop=lambda: False)
    package = types.ModuleType("appkit")
    package.__path__ = [os.path.join(_LIB, "appkit")]
    package.data = data
    with mock.patch.dict(sys.modules, {"appkit": package, "appkit.data": data}):
        spec = importlib.util.spec_from_file_location("appkit.places", os.path.join(_LIB, "appkit", "places.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class _SpiCard:
    """micropython-lib's sdcard.SDCard: a block device and nothing to free."""

    def readblocks(self, n, buf):
        pass

    def writeblocks(self, n, buf):
        pass

    def ioctl(self, op, arg):
        return 0


class _HostCard(_SpiCard):
    """machine.SDCard on an ESP32: deinit frees the SD host."""

    def __init__(self):
        self.freed = 0

    def deinit(self):
        self.freed += 1


class _Scope:
    def __init__(self):
        self.closers = []

    def on_close(self, fn):
        self.closers.append(fn)

    def close(self):
        for fn in self.closers:
            fn()


class CardTest(unittest.TestCase):
    def _hold(self, card, mount_fails=False):
        places = _places()
        board = types.SimpleNamespace(sdcard=lambda: card)
        calls = []

        def mount(dev, path, readonly=True):
            calls.append(("mount", path))
            if mount_fails:
                raise OSError(19)

        os_ = types.SimpleNamespace(stat=mock.Mock(side_effect=OSError(2)), mount=mount,
                                    umount=lambda path: calls.append(("umount", path)))
        scope = _Scope()
        with mock.patch.dict(sys.modules, {"board_peripherals": board}), mock.patch.object(places, "os", os_):
            held = places.hold_card(scope)
            scope.close()
        return held, calls

    def test_an_spi_card_unmounts_when_the_app_closes(self):
        card = _SpiCard()
        held, calls = self._hold(card)
        self.assertIs(held, card)
        self.assertEqual(calls, [("mount", "/sd"), ("umount", "/sd")])

    def test_a_machine_sdcard_is_freed_when_the_app_closes(self):
        card = _HostCard()
        held, calls = self._hold(card)
        self.assertIs(held, card)
        self.assertEqual(calls, [("mount", "/sd"), ("umount", "/sd")])
        self.assertEqual(card.freed, 1)

    def test_a_card_that_wont_mount_is_freed_and_reads_as_none(self):
        card = _HostCard()
        held, calls = self._hold(card, mount_fails=True)
        self.assertIs(held, False)
        self.assertEqual(calls, [("mount", "/sd")])
        self.assertEqual(card.freed, 1)


if __name__ == "__main__":
    unittest.main()
