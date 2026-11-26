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
    def _open(self, chosen, tabs=False, from_tab=False):
        provider, tab_provider = object(), object()
        merged = types.SimpleNamespace(provider=provider, providers=[provider, tab_provider])
        pages = []
        kit = types.ModuleType("endpointkit")
        by = tab_provider if from_tab else provider
        kit.selected = lambda kind: [types.SimpleNamespace(provider=by, label=label) for label in chosen]
        endpoints = types.ModuleType("midiports.endpoints")
        endpoints.merged_in = lambda: merged
        webmidi = types.ModuleType("midiports.webmidi")
        webmidi.page_in = lambda name="": pages.append(name) or "every input"
        ports = types.ModuleType("midiports")
        ports.__path__ = []
        ports.endpoints, ports.webmidi = endpoints, webmidi
        modules = {"endpointkit": kit, "midiports": ports, "midiports.endpoints": endpoints,
                   "midiports.webmidi": webmidi}
        if tabs:
            other = types.ModuleType("midiports.tabs")
            other.page_in = lambda: types.SimpleNamespace(names=["Tab: MIDI Controller"])
            ports.tabs = modules["midiports.tabs"] = other
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

    def test_an_input_from_another_tab_counts_as_chosen(self):
        inputs, merged, pages = self._open(["Tab: MIDI Controller"], tabs=True, from_tab=True)
        self.assertEqual((inputs.ports, inputs.names()), ([merged], ["Tab: MIDI Controller"]))

    def test_until_some_are_chosen_it_hears_the_other_tabs_too(self):
        inputs, merged, pages = self._open([], tabs=True)
        self.assertEqual((inputs.kind, len(inputs.ports)), ("web", 2))
        self.assertEqual(inputs.ports[1].names, ["Tab: MIDI Controller"])


if __name__ == "__main__":
    unittest.main()
