# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""midiEngine's MIDI in on a computer and in a browser page: the inputs
chosen in Connections, or every input until some are.

    python -m unittest tests.test_midiengine_midiin
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    # The module on its own: the app's package needs LVGL.
    path = os.path.join(ROOT, "apps", "midiengine", "midiin.py")
    spec = importlib.util.spec_from_file_location("midiengine_midiin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


midiin = _load()


class _Port:
    def __init__(self, data=b""):
        self.data = data

    def any(self):
        return len(self.data)

    def read(self):
        data, self.data = self.data, b""
        return data

    def close(self):
        pass


class BrowserTests(unittest.TestCase):
    def _open(self, chosen, tabs=False, from_tab=False):
        provider, tab_provider = object(), object()
        merged = _Port()
        merged.provider = provider
        merged.providers = [provider, tab_provider]
        pages = []
        kit = types.ModuleType("endpointkit")
        by = tab_provider if from_tab else provider
        kit.selected = lambda kind: [types.SimpleNamespace(provider=by, label=label) for label in chosen]
        endpoints = types.ModuleType("midiports.endpoints")
        endpoints.merged_in = lambda: merged
        webmidi = types.ModuleType("midiports.webmidi")

        def page_in(name=""):
            pages.append(name)
            return _Port(b"\x90\x3c\x64")

        webmidi.page_in = page_in
        ports = types.ModuleType("midiports")
        ports.__path__ = []
        ports.endpoints, ports.webmidi = endpoints, webmidi
        modules = {"endpointkit": kit, "midiports": ports, "midiports.endpoints": endpoints,
                   "midiports.webmidi": webmidi}
        if tabs:
            other = types.ModuleType("midiports.tabs")
            other.page_in = lambda: _Port(b"\xb0\x07\x64")
            ports.tabs = modules["midiports.tabs"] = other
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(midiin, "sys", types.SimpleNamespace(platform="webassembly")):
            found = midiin.open_desktop()
        return found, merged, pages

    def test_a_page_reads_the_inputs_chosen_in_connections(self):
        (port, names), merged, pages = self._open(["Keys", "Pads"])
        self.assertIs(port, merged)
        self.assertEqual((names, pages), ("Keys + Pads", []))

    def test_an_input_from_another_tab_counts_as_chosen(self):
        (port, names), merged, pages = self._open(["Tab: MIDI Controller"], tabs=True, from_tab=True)
        self.assertIs(port, merged)
        self.assertEqual(names, "Tab: MIDI Controller")

    def test_until_some_are_chosen_it_hears_the_other_tabs_too(self):
        (port, names), merged, pages = self._open([], tabs=True)
        self.assertEqual(names, "Web MIDI and other tabs")
        got = b""
        for _ in range(3):
            got += port.read() or b""
        self.assertIn(b"\xb0\x07\x64", got)
        self.assertIn(b"\x90\x3c\x64", got)

    def test_until_some_are_chosen_it_reads_every_input(self):
        (port, names), merged, pages = self._open([])
        self.assertEqual((names, pages), ("Web MIDI", [""]))
        self.assertEqual(port.read(), b"\x90\x3c\x64")


if __name__ == "__main__":
    unittest.main()
