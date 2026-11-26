# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station turns a board's USB port into a MIDI device only where the
board lists a ``usb_midi`` role: starting one re-enumerates the port. In a
browser page it reads the inputs chosen in Connections, and every input the
browser offers until some are chosen.

    python -m unittest tests.test_synthstation_midi
"""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps"))

from synthstation import midi  # noqa: E402
from synthstation.midi import Inputs  # noqa: E402


def _board(roles, started):
    bp = types.ModuleType("board_peripherals")
    bp.PERIPHERALS = frozenset(roles)

    def usb_midi():
        started.append(True)
        return ("in", "out")

    bp.usb_midi = usb_midi
    return bp


class DeviceModeTests(unittest.TestCase):
    def _open(self, roles):
        started = []
        inputs = Inputs()
        with mock.patch.dict(sys.modules, {"board_peripherals": _board(roles, started)}):
            opened = inputs._open_device()
        return inputs, opened, started

    def test_a_board_with_usb_midi_becomes_a_midi_device(self):
        inputs, opened, started = self._open({"usb_device", "usb_midi"})
        self.assertTrue(opened)
        self.assertEqual(started, [True])
        self.assertEqual((inputs.kind, inputs.ports, inputs.names()), ("device", ["in"], ["USB MIDI"]))

    def test_usb_device_alone_leaves_the_port_alone(self):
        inputs, opened, started = self._open({"usb_device", "wlan"})
        self.assertFalse(opened)
        self.assertEqual(started, [])
        self.assertIsNone(inputs.kind)

    def test_no_board_peripherals_leaves_the_port_alone(self):
        with mock.patch.dict(sys.modules, {"board_peripherals": None}):
            self.assertFalse(Inputs()._open_device())


class BrowserTests(unittest.TestCase):
    def _open(self, chosen):
        provider = object()
        merged = types.SimpleNamespace(provider=provider)
        pages = []
        kit = types.ModuleType("endpointkit")
        kit.selected = lambda kind: [types.SimpleNamespace(provider=provider, label=label) for label in chosen]
        endpoints = types.ModuleType("midiports.endpoints")
        endpoints.merged_in = lambda: merged
        webmidi = types.ModuleType("midiports.webmidi")
        webmidi.page_in = lambda name="": pages.append(name) or "every input"
        ports = types.ModuleType("midiports")
        ports.__path__ = []
        ports.endpoints, ports.webmidi = endpoints, webmidi
        modules = {"endpointkit": kit, "midiports": ports, "midiports.endpoints": endpoints,
                   "midiports.webmidi": webmidi}
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(midi, "sys", types.SimpleNamespace(platform="webassembly")):
            inputs = Inputs().open()
        return inputs, merged, pages

    def test_a_page_reads_the_inputs_chosen_in_connections(self):
        inputs, merged, pages = self._open(["Keys", "Pads"])
        self.assertEqual((inputs.ports, inputs.names()), ([merged], ["Keys", "Pads"]))
        self.assertEqual(pages, [], "nothing else is opened")

    def test_until_some_are_chosen_it_reads_every_input(self):
        inputs, merged, pages = self._open([])
        self.assertEqual((inputs.kind, inputs.ports, pages), ("web", ["every input"], [""]))


if __name__ == "__main__":
    unittest.main()
