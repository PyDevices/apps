# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Build Ostinato's icon modules from Google's Material Design icons.

    .venv/bin/python scripts/make_icons.py PATH_TO_material-design-icons PATH_TO_make_icons.py

Writes app/ui/_icons_<size>.py for each size in SIZES, holding only the icons
of ICONS that iconkit's shared set at that size lacks (iconkit refuses a name
twice). The Material PNGs come in 18, 24, 36 and 48 px, so those are the sizes.
app/ui/theme.py registers each module with ``iconkit.add()``. The second argument is iconkit's generator, ``make_icons.py``, from
https://github.com/PyDevices/pydevices/tree/main/packages/iconkit. Needs Pillow. The icons are Apache-2.0
(iconkit's LICENSE-ICONS).
"""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import iconkit_lib  # noqa: E402

sys.path.insert(0, str(iconkit_lib.find()))

import iconkit  # noqa: E402

ICONS = [
    "play_arrow", "stop", "fiber_manual_record", "repeat", "add", "remove", "delete",
    "undo", "redo", "save", "folder_open", "file_download", "music_note", "piano",
    "tune", "graphic_eq", "volume_up", "volume_off", "headphones", "settings", "close",
    "more_vert", "content_copy", "grid_on", "queue_music", "timer", "speed", "keyboard",
    "equalizer", "mic", "edit", "expand_more", "chevron_left", "chevron_right", "usb",
    "memory", "check", "help_outline", "drag_indicator", "skip_previous", "layers",
    "power_settings_new", "auto_fix_high", "sensors", "album", "speaker", "expand_less",
]
SIZES = (18, 24, 36, 48)


def own_names(size):
    """The names of ICONS that iconkit's shipped module at *size* lacks."""
    try:
        shared = set(iconkit.names(size))
    except ValueError:
        shared = set()
    return [n for n in ICONS if n not in shared]


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: make_icons.py PATH_TO_material-design-icons PATH_TO_iconkit_make_icons.py "
                         "(iconkit's generator: https://github.com/PyDevices/pydevices/tree/main/packages/iconkit)")
    source, generator = sys.argv[1:]
    for size in SIZES:
        names = own_names(size)
        out = ROOT / "app" / "ui" / ("_icons_%d.py" % size)
        if not names:
            if out.exists():
                out.unlink()
            continue
        subprocess.run([sys.executable, generator, source, "--size", str(size),
                        "--names", ",".join(names), "--out", str(out)], check=True)


if __name__ == "__main__":
    main()
