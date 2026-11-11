# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Patch, note and controller names a DAW can read: a MIDNAM file and a
Cakewalk instrument definition (``.ins``) for the sound module.

    python -m soundmodule.names --out names/

Both are built from the catalogs audioinstruments and audioeffects carry
(``catalog.json`` in each package), so the names match the instruments you
have installed. ``--instruments`` and ``--effects`` read a catalog from a
file instead.

Every instrument's patches are listed under it, with the Bank Select and
Program Change that play them on the sound module (bank ``BANK_INSTRUMENTS``
or ``BANK_DRUM_MACHINES``, the instrument's program, its patch as the LSB),
and General MIDI's programs are bank 0. A drum machine's patches name its
keys. The macros are CC 102 to 117: the default mode names them "Macro 0"
and on, and each instrument has a mode of its own (a ``CustomDeviceMode`` in
the MIDNAM, an instrument definition in the ``.ins``) that gives them its
names. CC91 and CC93 are named after the reverb and chorus the module plays.
"""

import json
import sys

from . import engine

MANUFACTURER = "PyDevices"
MODEL = "Sound Module"
#: The CCs every part answers, beside the macros.
CONTROLS = (
    (1, "Modulation"),
    (7, "Volume"),
    (10, "Pan"),
    (11, "Expression"),
    (64, "Sustain"),
)
#: The master effects CC91 and CC93 send to, by their catalog name.
SENDS = ((engine.CC_REVERB, "Reverb"), (engine.CC_CHORUS, "Chorus"))


def load(path):
    """A catalog read from ``path``."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def installed(package):
    """The catalog that the installed ``package`` carries."""
    module = __import__(package)
    folder = module.__file__.replace("\\", "/").rsplit("/", 1)[0]
    try:
        return load(folder + "/catalog.json")
    except OSError:
        raise SystemExit("%s in %s has no catalog.json: install a newer release, or pass its"
                         " file with --%s" % (package, folder, package[5:]))


def _by_name(catalog, key):
    return {e["name"]: e for e in catalog[key]}


def parts(instruments):
    """``(bank MSB, program, entry)`` for each instrument the module plays,
    melodic first, in program order."""
    found = _by_name(instruments, "instruments")
    out = []
    for msb, table in ((engine.BANK_INSTRUMENTS, engine.INSTRUMENTS),
                       (engine.BANK_DRUM_MACHINES, engine.DRUM_MACHINES)):
        for program, name in enumerate(table):
            if name is None:
                continue
            if name not in found:
                raise ValueError("the catalog has no instrument %r" % name)
            out.append((msb, program, found[name]))
    return out


def controls(effects, macros=None):
    """``(cc, name)`` for every controller: the fixed ones, the two sends and
    the macros, named from ``macros`` (a catalog entry's) where given."""
    found = _by_name(effects, "effects")
    out = list(CONTROLS)
    for cc, name in SENDS:
        if name not in found:
            raise ValueError("the effects catalog has no %r" % name)
        out.append((cc, "%s send" % found[name]["display_name"]))
    labels = [m["label"] for m in macros] if macros else []
    for i in range(engine.MACRO_CCS):
        label = labels[i] if i < len(labels) else "Macro %d" % i
        out.append((engine.MACRO_CC + i, label))
    return sorted(out)


def _xml(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def midnam(instruments, effects):
    """The MIDNAM document, as text."""
    entries = parts(instruments)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE MIDINameDocument PUBLIC "-//MIDI Manufacturers Association//DTD'
        ' MIDINameDocument 1.0//EN" "http://www.midi.org/dtds/MIDINameDocument10.dtd">',
        "<MIDINameDocument>",
        "  <Author>%s</Author>" % MANUFACTURER,
        "  <MasterDeviceNames>",
        "    <Manufacturer>%s</Manufacturer>" % MANUFACTURER,
        "    <Model>%s</Model>" % MODEL,
    ]
    modes = [("Default", "All", None)]
    for msb, program, e in entries:
        if e["macros"]:
            modes.append((e["display_name"], e["name"], e))
    for mode, nameset, _ in modes:
        out.append('    <CustomDeviceMode Name="%s">' % _xml(mode))
        out.append("      <ChannelNameSetAssignments>")
        for ch in range(1, 17):
            out.append('        <ChannelNameSetAssign Channel="%d" NameSet="%s"/>'
                       % (ch, _xml(nameset)))
        out.append("      </ChannelNameSetAssignments>")
        out.append("    </CustomDeviceMode>")
    for mode, nameset, only in modes:
        out.append('    <ChannelNameSet Name="%s">' % _xml(nameset))
        out.append("      <AvailableForChannels>")
        for ch in range(1, 17):
            out.append('        <AvailableChannel Channel="%d" Available="true"/>' % ch)
        out.append("      </AvailableForChannels>")
        out.append('      <UsesControlNameList Name="%s"/>' % _xml(nameset))
        if only is None:
            out.append('      <PatchBank Name="General MIDI">')
            out.append("        <MIDICommands>")
            out.append('          <ControlChange Control="0" Value="0"/>')
            out.append('          <ControlChange Control="32" Value="0"/>')
            out.append("        </MIDICommands>")
            out.append("        <PatchNameList>")
            for program, name in enumerate(engine.GM_NAMES):
                out.append('          <Patch Number="%d" Name="%s" ProgramChange="%d"/>'
                           % (program + 1, _xml(name), program))
            out.append("        </PatchNameList>")
            out.append("      </PatchBank>")
        for msb, program, e in entries:
            if only is not None and e is not only:
                continue
            out.append('      <PatchBank Name="%s">' % _xml(e["display_name"]))
            out.append("        <MIDICommands>")
            out.append('          <ControlChange Control="0" Value="%d"/>' % msb)
            out.append('          <ControlChange Control="32" Value="0"/>')
            out.append("        </MIDICommands>")
            out.append("        <PatchNameList>")
            for p in e["patches"]:
                out.append('          <Patch Number="%d" Name="%s" ProgramChange="%d">'
                           % (p["index"] + 1, _xml(p["name"]), program))
                out.append("            <PatchMIDICommands>")
                out.append('              <ControlChange Control="0" Value="%d"/>' % msb)
                out.append('              <ControlChange Control="32" Value="%d"/>' % p["index"])
                out.append('              <ProgramChange Number="%d"/>' % program)
                out.append("            </PatchMIDICommands>")
                if e.get("notes"):
                    out.append('            <UsesNoteNameList Name="%s"/>' % _xml(e["name"]))
                out.append("          </Patch>")
            out.append("        </PatchNameList>")
            out.append("      </PatchBank>")
        out.append("    </ChannelNameSet>")
    for msb, program, e in entries:
        if e.get("notes"):
            out.append('    <NoteNameList Name="%s">' % _xml(e["name"]))
            for n in e["notes"]:
                out.append('      <Note Number="%d" Name="%s"/>' % (n["key"], _xml(n["name"])))
            out.append("    </NoteNameList>")
    for mode, nameset, only in modes:
        out.append('    <ControlNameList Name="%s">' % _xml(nameset))
        for cc, name in controls(effects, only["macros"] if only else None):
            out.append('      <Control Type="7bit" Number="%d" Name="%s"/>' % (cc, _xml(name)))
        out.append("    </ControlNameList>")
    out.append("  </MasterDeviceNames>")
    out.append("</MIDINameDocument>")
    return "\n".join(out) + "\n"


def cakewalk_ins(instruments, effects):
    """The Cakewalk instrument definition file, as text.

    An ``.ins`` bank is one MSB and LSB, so the module's patches are listed a
    bank per patch number: bank 80/k holds patch k of each instrument, at the
    instrument's program.
    """
    entries = parts(instruments)
    title = "%s %s" % (MANUFACTURER, MODEL)
    out = ["; %s: patch, key and controller names." % title, "", ".Patch Names", ""]
    out.append("[%s General MIDI]" % MODEL)
    out += ["%d=%s" % (i, name) for i, name in enumerate(engine.GM_NAMES)]
    out.append("")
    banks = []
    for msb in (engine.BANK_INSTRUMENTS, engine.BANK_DRUM_MACHINES):
        group = [(program, e) for m, program, e in entries if m == msb]
        most = max(len(e["patches"]) for _, e in group)
        kind = "Instruments" if msb == engine.BANK_INSTRUMENTS else "Drum Machines"
        for lsb in range(most):
            name = "%s %s, patch %d" % (MODEL, kind, lsb + 1)
            banks.append((msb * 128 + lsb, name, msb))
            out.append("[%s]" % name)
            for program, e in group:
                for p in e["patches"]:
                    if p["index"] == lsb:
                        out.append("%d=%s: %s" % (program, e["display_name"], p["name"]))
            out.append("")
    out += [".Note Names", ""]
    for _, _, e in entries:
        if e.get("notes"):
            out.append("[%s]" % e["display_name"])
            out += ["%d=%s" % (n["key"], n["name"]) for n in e["notes"]]
            out.append("")
    out += [".Controller Names", ""]
    defs = [(title, MODEL, None)]
    for _, _, e in entries:
        if e["macros"]:
            defs.append(("%s: %s" % (title, e["display_name"]),
                         "%s %s" % (MODEL, e["display_name"]), e))
    for _, control, e in defs:
        out.append("[%s]" % control)
        out += ["%d=%s" % (cc, name) for cc, name in controls(effects, e["macros"] if e else None)]
        out.append("")
    out += [".Instrument Definitions", ""]
    for definition, control, _ in defs:
        out.append("[%s]" % definition)
        out.append("Control=%s" % control)
        out.append("BankSelMethod=0")
        out.append("Patch[0]=%s General MIDI" % MODEL)
        for bank, name, _ in banks:
            out.append("Patch[%d]=%s" % (bank, name))
        for msb, program, e in entries:
            if e.get("notes"):
                for bank, _, bank_msb in banks:
                    if bank_msb == msb:
                        out.append("Key[%d,%d]=%s" % (bank, program, e["display_name"]))
                        out.append("Drum[%d,%d]=1" % (bank, program))
        out.append("")
    return "\n".join(out)


def main(argv):
    folder = "."
    instruments = effects = None
    i = 1
    while i < len(argv):
        if argv[i] == "--out":
            folder = argv[i + 1]
        elif argv[i] == "--instruments":
            instruments = load(argv[i + 1])
        elif argv[i] == "--effects":
            effects = load(argv[i + 1])
        else:
            print(__doc__)
            return 2
        i += 2
    instruments = instruments or installed("audioinstruments")
    effects = effects or installed("audioeffects")
    import os

    os.makedirs(folder, exist_ok=True)
    for filename, text in (("PyDevices Sound Module.midnam", midnam(instruments, effects)),
                           ("PyDevices Sound Module.ins", cakewalk_ins(instruments, effects))):
        path = folder.rstrip("/") + "/" + filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
