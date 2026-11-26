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
    def _open(self, chosen):
        provider = object()
        merged = _Port()
        merged.provider = provider
        pages = []
        kit = types.ModuleType("endpointkit")
        kit.selected = lambda kind: [types.SimpleNamespace(provider=provider, label=label) for label in chosen]
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
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(midiin, "sys", types.SimpleNamespace(platform="webassembly")):
            found = midiin.open_desktop()
        return found, merged, pages

    def test_a_page_reads_the_inputs_chosen_in_connections(self):
        (port, names), merged, pages = self._open(["Keys", "Pads"])
        self.assertIs(port, merged)
        self.assertEqual((names, pages), ("Keys + Pads", []))

    def test_until_some_are_chosen_it_reads_every_input(self):
        (port, names), merged, pages = self._open([])
        self.assertEqual((names, pages), ("Web MIDI", [""]))
        self.assertEqual(port.read(), b"\x90\x3c\x64")


if __name__ == "__main__":
    unittest.main()
