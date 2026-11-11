# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""``soundmodule.names``: the MIDNAM and the Cakewalk ``.ins`` it builds from
the catalogs audioinstruments and audioeffects carry, parsed back.

    python -m unittest tests.test_soundmodule_names

The catalogs are ``$AUDIOINSTRUMENTS_CATALOG`` and ``$AUDIOEFFECTS_CATALOG``,
else ``catalog.json`` in the checkouts the engine tests use. A catalog that
isn't there fails the test: the names are only worth checking against the
real ones.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "lib"))
sys.path.insert(0, str(TESTS))

from soundmodule import engine, names  # noqa: E402
from test_engine import audio_checkout  # noqa: E402


def catalog(package):
    path = os.environ.get(package.upper() + "_CATALOG")
    if not path:
        checkout = audio_checkout(package)
        if checkout is None:
            raise unittest.SkipTest("no %s checkout" % package)
        path = os.path.join(checkout, "lib", package, "catalog.json")
    if not os.path.isfile(path):
        raise AssertionError("%s has no catalog.json at %s" % (package, path))
    return names.load(path)


def ins_sections(text):
    """The ``.ins`` file as {section: {[list]: [(key, value)]}}, refusing any
    line that isn't a comment, a section, a list or ``key=value``."""
    sections = {}
    section = block = None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("."):
            section = sections.setdefault(line, {})
            block = None
        elif line.startswith("[") and line.endswith("]"):
            if section is None:
                raise ValueError("line %d: a list before any section" % number)
            if line[1:-1] in section:
                raise ValueError("line %d: %s twice" % (number, line))
            block = section[line[1:-1]] = []
        elif "=" in line and block is not None:
            key, value = line.split("=", 1)
            block.append((key, value))
        else:
            raise ValueError("line %d: %r" % (number, line))
    return sections


class TheNames(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.instruments = catalog("audioinstruments")
        cls.effects = catalog("audioeffects")
        cls.by_name = {e["name"]: e for e in cls.instruments["instruments"]}
        cls.reverb = {e["name"]: e for e in cls.effects["effects"]}["Reverb"]["display_name"]

    def played(self):
        """(msb, program, entry) for every instrument the engine plays."""
        out = []
        for msb, table in ((engine.BANK_INSTRUMENTS, engine.INSTRUMENTS),
                           (engine.BANK_DRUM_MACHINES, engine.DRUM_MACHINES)):
            for program, name in enumerate(table):
                if name is not None:
                    out.append((msb, program, self.by_name[name]))
        return out

    def test_the_midnam_parses_and_selects_each_patch(self):
        root = ET.fromstring(names.midnam(self.instruments, self.effects).encode())
        self.assertEqual(root.tag, "MIDINameDocument")
        device = root.find("MasterDeviceNames")
        sets = {s.get("Name"): s for s in device.findall("ChannelNameSet")}
        notes = {n.get("Name") for n in device.findall("NoteNameList")}
        controls = {c.get("Name"): c for c in device.findall("ControlNameList")}
        for mode in device.findall("CustomDeviceMode"):
            for assign in mode.iter("ChannelNameSetAssign"):
                self.assertIn(assign.get("NameSet"), sets)
        for s in sets.values():
            self.assertIn(s.find("UsesControlNameList").get("Name"), controls)
            for uses in s.iter("UsesNoteNameList"):
                self.assertIn(uses.get("Name"), notes)
        banks = {b.get("Name"): b for b in sets["All"].findall("PatchBank")}
        self.assertEqual(len(list(banks["General MIDI"].iter("Patch"))), 128)
        for msb, program, e in self.played():
            bank = banks[e["display_name"]]
            got = []
            for patch in bank.iter("Patch"):
                commands = patch.find("PatchMIDICommands")
                cc = {int(c.get("Control")): int(c.get("Value"))
                      for c in commands.findall("ControlChange")}
                self.assertEqual(cc[0], msb)
                self.assertEqual(int(commands.find("ProgramChange").get("Number")), program)
                got.append((cc[32], patch.get("Name")))
                self.assertEqual(patch.find("UsesNoteNameList") is not None, bool(e.get("notes")))
            self.assertEqual(got, [(p["index"], p["name"]) for p in e["patches"]])

    def test_the_midnam_names_the_macros_and_sends(self):
        root = ET.fromstring(names.midnam(self.instruments, self.effects).encode())
        controls = {c.get("Name"): {int(x.get("Number")): x.get("Name") for x in c}
                    for c in root.iter("ControlNameList")}
        default = controls["All"]
        self.assertEqual(default[engine.CC_REVERB], "%s send" % self.reverb)
        self.assertEqual(default[engine.MACRO_CC], "Macro 0")
        self.assertEqual(len([cc for cc in default if cc >= engine.MACRO_CC]), engine.MACRO_CCS)
        for _, _, e in self.played():
            if e["macros"]:
                own = controls[e["name"]]
                for i, m in enumerate(e["macros"]):
                    self.assertEqual(own[engine.MACRO_CC + i], m["label"])

    def test_the_ins_parses_and_every_reference_resolves(self):
        sections = ins_sections(names.cakewalk_ins(self.instruments, self.effects))
        patches = sections[".Patch Names"]
        keys = sections[".Note Names"]
        controllers = sections[".Controller Names"]
        definitions = sections[".Instrument Definitions"]
        self.assertTrue(definitions)
        for definition in definitions.values():
            fields = dict(definition)
            self.assertIn(fields["Control"], controllers)
            for key, value in definition:
                if key.startswith("Patch["):
                    self.assertIn(value, patches)
                elif key.startswith("Key["):
                    self.assertIn(value, keys)
        for block in list(patches.values()) + list(keys.values()) + list(controllers.values()):
            for key, _ in block:
                self.assertTrue(0 <= int(key) <= 127, key)
        default = dict(definitions["%s %s" % (names.MANUFACTURER, names.MODEL)])
        for msb, program, e in self.played():
            for p in e["patches"]:
                bank = "Patch[%d]" % (msb * 128 + p["index"])
                listed = dict(patches[default[bank]])
                self.assertEqual(listed[str(program)], "%s: %s" % (e["display_name"], p["name"]))

    def test_it_writes_both_files(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "i.json"), "w", encoding="utf-8") as f:
                f.write(json.dumps(self.instruments))
            with open(os.path.join(folder, "e.json"), "w", encoding="utf-8") as f:
                f.write(json.dumps(self.effects))
            with contextlib.redirect_stdout(io.StringIO()):
                code = names.main(["names", "--out", folder,
                                   "--instruments", os.path.join(folder, "i.json"),
                                   "--effects", os.path.join(folder, "e.json")])
            self.assertEqual(code, 0)
            written = sorted(f for f in os.listdir(folder) if not f.endswith(".json"))
            self.assertEqual(written, ["PyDevices Sound Module.ins",
                                       "PyDevices Sound Module.midnam"])
            ET.parse(os.path.join(folder, "PyDevices Sound Module.midnam"))


if __name__ == "__main__":
    unittest.main()
