# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Puts Vamp on a board through mpftp: vamp and songmodel in /lib, hmilink
beside them, and a song to start with.

    python tools/vamp_files.py DEVICE [--hmilink DIR] [--song FILE]
    python tools/vamp_files.py DEVICE --panel [--hmilink DIR]

DEVICE is what mpftp takes (COM4, ws://<board-address>). Then, on the board::

    import vamp; vamp.run()

``--panel`` puts the front panel there instead, for a board with a touch
screen that joins a box somewhere else::

    import vamp; vamp.run_panel("<the box's address>")

``--hmilink`` names the hmilink package to copy (the folder holding
``__init__.py``); the default is an omnipython checkout beside this one, else
Ostinato's vendor/lib. ``--song`` is the song the box opens, /vamp_song.json
on the board (default: Ostinato's SoundFont check song).
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSTINATO = os.path.join(ROOT, "programs", "ostinato")

# Each package, its files, and the folder they come from in this checkout.
PACKAGES = {
    "vamp": (["__init__.py", "engine.py", "device.py", "record.py", "main.py"], "programs"),
    "songmodel": (["__init__.py", "model.py", "link.py", "page_data.py"], "lib"),
}
PANEL = {
    "vamp": (["__init__.py", "panel.py", "panel_view.py", "panel_main.py"], "programs"),
    "songmodel": (["__init__.py", "model.py"], "lib"),
}
HMILINK = ["__init__.py", "tcp.py"]
SONG = os.path.join(OSTINATO, "songs", "sketches", "soundfont_check.json")


def _hmilink():
    parent = ROOT
    for _ in range(3):
        parent = os.path.dirname(parent)
        for inside in (("packages", "hmilink", "hmilink"), ("hmilink", "hmilink")):
            p = os.path.join(parent, "omnipython", *inside)
            if os.path.isfile(os.path.join(p, "__init__.py")):
                return p
    return os.path.join(OSTINATO, "vendor", "lib", "hmilink")


def mpftp(*args):
    cmd = [os.environ.get("MPFTP", "mpftp")] + list(args)
    print(" ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    return r.stdout


def main(argv):
    device = argv[1]
    hmi = argv[argv.index("--hmilink") + 1] if "--hmilink" in argv else _hmilink()
    song = argv[argv.index("--song") + 1] if "--song" in argv else SONG
    for d in ("/lib", "/lib/vamp", "/lib/songmodel", "/lib/hmilink"):
        try:
            mpftp("mkdir", "-d", device, d)
        except SystemExit:
            pass                    # there already; a put into a missing one fails below
    panel = "--panel" in argv
    for package, (names, source) in (PANEL if panel else PACKAGES).items():
        for name in names:
            mpftp("put", "-d", device, os.path.join(ROOT, source, package, name), "/lib/%s/%s" % (package, name))
    for name in HMILINK:
        mpftp("put", "-d", device, os.path.join(hmi, name), "/lib/hmilink/" + name)
    if panel:
        print("Vamp's front panel is on %s: import vamp; vamp.run_panel(\"<the box's address>\")" % device)
        return
    mpftp("put", "-d", device, song, "/vamp_song.json")
    print("Vamp is on %s: import vamp; vamp.run()" % device)


if __name__ == "__main__":
    main(sys.argv)
