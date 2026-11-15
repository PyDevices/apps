# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Vamp's front panel: a touch screen that edits the song a box plays.

On a board with an 800x480 touch screen, with the files from
``tools/vamp_files.py --panel`` on it::

    import vamp; vamp.run_panel("192.168.1.50")

On a desktop, with this repository's ``programs/`` and ``lib/`` and hmilink on
the path, and pydevices-desktop for the window::

    PYDEVICES_WIDTH=800 PYDEVICES_HEIGHT=480 PYDEVICES_SCALE=1 python -m vamp.panel_main --box HOST[:9100]

The box is a running Vamp (``vamp.main``). The board joins the Wi-Fi network it
already knows before it looks for the box; with ``--ap SSID PASSWORD`` it is
an access point as well, for a box and a panel with no router between them.
"""

import sys

import lvgl as lv

from vamp.panel import Front, join
from vamp.panel_view import View

try:
    import network
except ImportError:
    network = None

DEFAULTS = {"box": "127.0.0.1", "port": 9100, "ap": None}
STEP_MS = 30


def _args(argv):
    opts = dict(DEFAULTS)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--box":
            opts["box"] = argv[i + 1]
            i += 2
        elif a == "--ap":
            opts["ap"] = (argv[i + 1], argv[i + 2])
            i += 3
        elif not a.startswith("--") and i == 0:
            opts["box"] = a
            i += 1
        else:
            raise ValueError("unknown option %r" % (a,))
    host = opts["box"]
    if ":" in host:
        host, port = host.rsplit(":", 1)
        opts["box"] = host
        opts["port"] = int(port)
    return opts


def _wifi(ap):
    """Join the known network, be an access point if asked, and keep the radio
    awake: a radio that naps between beacons makes every press late."""
    if network is None:
        return
    sta = network.WLAN(network.STA_IF)
    if ap is not None:
        point = network.WLAN(network.AP_IF)
        point.active(True)
        point.config(ssid=ap[0], password=ap[1], security=network.WLAN.SEC_WPA2)
        print("panel: access point %s at %s" % (ap[0], point.ifconfig()[0]))
    if not sta.isconnected() and ap is None:
        import wifi_manager

        wifi_manager.connect()
    if sta.active():
        sta.config(pm=network.WLAN.PM_NONE)


def start(argv=()):
    """Build the panel on the board's display and start it. Returns its
    `View`; LVGL's own loop runs it from here."""
    opts = _args(list(argv))
    _wifi(opts["ap"])
    import display_driver  # noqa: F401  (the board's display and touch, on LVGL)

    front = Front(lambda: join(opts["box"], opts["port"]))
    screen = lv.obj(None)         # its own screen, whatever was on the display before
    lv.screen_load(screen)
    view = View(front, screen)
    view.timer = lv.timer_create(lambda t: view.step(), STEP_MS, None)
    print("panel: looking for the box at %s:%d" % (opts["box"], opts["port"]))
    return view


def main(argv=None):
    """Run the panel until the window closes or Ctrl-C."""
    view = start(sys.argv[1:] if argv is None else argv)
    import display_driver

    try:
        display_driver.app.run()
    except KeyboardInterrupt:
        pass
    finally:
        view.timer.delete()
        view.front.close()
    return view


if __name__ == "__main__":
    main()
