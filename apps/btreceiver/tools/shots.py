# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Save the receiver's screen in each of its states, from the demo, as PNGs.

    python apps/btreceiver/tools/shots.py OUT_DIR [STATE ...] [--size WxH]

Run it from the repository's root with CPython, lvgl, svgio, jpegio and
Pillow. The states are the demo's: pairing, idle, playing, paused,
nocover and long. Each one opens the app under Home's shell, the way a board shows
it, waits for the demo to settle and saves ``OUT_DIR/<state>.png``. No
window opens.
"""

import os
import subprocess
import sys

STATES = ("pairing", "idle", "playing", "paused", "nocover", "long")
WAIT_MS = 1500


def one(out, state, size):
    """Open the app in *state* in this process and save the screen."""
    root = os.getcwd()
    sys.path.insert(0, os.path.join(root, "lib"))
    sys.path.insert(0, root)
    w, h = size.split("x")
    os.environ.update({"OMNIPYTHON_WIDTH": w, "OMNIPYTHON_HEIGHT": h, "OMNIPYTHON_SCALE": "1",
                       "SDL_VIDEODRIVER": "dummy", "BTRECEIVER_DEMO": state})
    import lvgl as lv
    from PIL import Image

    import appkit
    from display_driver import app
    from multimer import ticks_diff, ticks_ms
    from touchkit import shell

    launcher = shell.TouchLauncher(app, home="home")
    launcher.scan("apps")
    launcher.shell = shell.TouchShell(launcher)
    launcher.boot("btreceiver")
    t0 = ticks_ms()

    def grab(obj):
        snap = lv.snapshot_take(obj, lv.COLOR_FORMAT.ARGB8888)
        sw, sh, stride = snap.header.w, snap.header.h, snap.header.stride
        px = bytes(snap.data.__dereference__(snap.data_size))
        snap.destroy() if hasattr(snap, "destroy") else None
        rows = b"".join(px[y * stride : y * stride + sw * 4] for y in range(sh))
        return Image.frombytes("RGBA", (sw, sh), rows, "raw", "BGRA")

    def poll(_):
        try:
            _poll()
        except BaseException:
            import traceback

            traceback.print_exc()
            os._exit(1)

    def _poll():
        if ticks_diff(ticks_ms(), t0) < WAIT_MS:
            return
        img = grab(lv.screen_active()).convert("RGB")
        # The Home button is on the system layer, over every app.
        b = launcher.shell.home_button
        if b is not None and not b.has_flag(lv.obj.FLAG.HIDDEN):
            area = lv.area_t()
            b.get_coords(area)
            img.paste(grab(b), (area.x1, area.y1), grab(b))
        path = os.path.join(out, state + ".png")
        img.save(path)
        print("saved", path, flush=True)
        os._exit(0)

    timer = lv.timer_create(poll, 50, None)  # kept: a dropped timer is deleted
    appkit.serve()
    return timer


def main():
    args = sys.argv[1:]
    size = "800x480"
    if "--size" in args:
        i = args.index("--size")
        size = args[i + 1]
        del args[i : i + 2]
    if "--one" in args:
        args.remove("--one")
        one(args[0], args[1], size)
        return
    out = args[0]
    os.makedirs(out, exist_ok=True)
    for state in args[1:] or STATES:
        # One process per state: the display opens once per process.
        subprocess.run([sys.executable, __file__, "--one", out, state, "--size", size], timeout=120, check=True)


if __name__ == "__main__":
    main()
