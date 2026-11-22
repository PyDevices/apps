# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Make a Backline sample kit from a drum machine: one WAV per pad and a kit.json.

    python tools/backline/make_kit.py MACHINE FOLDER [--name NAME] [--seconds S]

Each General MIDI pad the machine has (kick, snares, hats, toms, cymbals) is
struck once at full velocity and recorded for ``S`` seconds (1.5), trimmed
where it falls silent. The closed, pedal and open hats share a choke group.
The folder is a kit `kits.SampleKit` plays, so it is also a starting point
for a kit of your own: replace a WAV, keep its name.
"""

import json
import os
import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path[:0] = [ROOT + "/apps", ROOT + "/lib"]

import audiocore  # noqa: E402
import audioinstruments  # noqa: E402

from backline import kits  # noqa: E402

PADS = {35: "kick2", 36: "kick", 37: "stick", 38: "snare", 39: "clap", 40: "snare2", 41: "tom_floor", 42: "hat_closed",
        43: "tom_floor2", 44: "hat_pedal", 45: "tom_low", 46: "hat_open", 47: "tom_lowmid", 48: "tom_himid",
        49: "crash", 50: "tom_high", 51: "ride", 53: "ride_bell", 56: "cowbell", 57: "crash2"}


def strike(machine, pitch, seconds):
    inst = audioinstruments.create(machine, kits.RATE, 2)
    inst.note_on(pitch, 127)
    mono = bytearray()
    want = int(seconds * kits.RATE)
    got = 0
    while got < want:
        if hasattr(inst, "fill"):
            inst.fill()
        _r, b = audiocore.get_buffer(inst.output)
        b = bytes(b)
        for i in range(0, len(b), 4):
            left = b[i] | (b[i + 1] << 8)
            right = b[i + 2] | (b[i + 3] << 8)
            left = left - 65536 if left > 32767 else left
            right = right - 65536 if right > 32767 else right
            v = (left + right) // 2
            mono.append(v & 255)
            mono.append((v >> 8) & 255)
        got += len(b) // 4
    inst.deinit()
    # Trim the silence at the end, keeping a short fade's worth.
    end = len(mono) // 2
    while end > 0:
        v = mono[2 * end - 2] | (mono[2 * end - 1] << 8)
        v = v - 65536 if v > 32767 else v
        if abs(v) > 40:
            break
        end -= 1
    return bytes(mono[: min(len(mono), 2 * (end + kits.RATE // 50))])


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    machine, folder = argv[0], argv[1].rstrip("/")
    name = argv[argv.index("--name") + 1] if "--name" in argv else kits.NAMES.get(machine, machine) + " samples"
    seconds = float(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 1.5
    have = [p for p, _label in audioinstruments.load(machine).NOTE_MAP]
    os.makedirs(folder, exist_ok=True)
    pads = {}
    for pitch, label in sorted(PADS.items()):
        if pitch not in have:
            continue
        data = strike(machine, pitch, seconds)
        kits.write_wav("%s/%s.wav" % (folder, label), data, kits.RATE)
        pads[str(pitch)] = label + ".wav"
    info = {"name": name, "pads": pads, "choke": [[p for p in (42, 44, 46) if str(p) in pads]]}
    with open(folder + "/kit.json", "w") as f:
        json.dump(info, f, indent=1)
    print("%s: %d pads in %s" % (name, len(pads), folder))


if __name__ == "__main__":
    main(sys.argv[1:])
