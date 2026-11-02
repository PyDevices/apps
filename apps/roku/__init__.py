# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Roku remote: a TV remote on the touch screen, over the LAN (Roku's ECP).

It finds the Rokus on the network (SSDP), lists them by name, and sends
keys to the one picked: the d-pad and OK, Back, the TV's Home, play/pause,
rewind and fast forward, volume and mute, and power.

Every request runs on ``scope.worker`` and closes its socket when it's
done, so a TV that doesn't answer never holds the screen up, and nothing is
left open when the app closes.

``config.json`` in its data folder: ``{"prefer": "Bedroom"}`` picks the TV
whose name or model holds that text when there are several. The one last
picked wins while the board stays up.
"""

import lvgl as lv

from devkit import ecp, net, settings, ui

DEFAULTS = {"prefer": None}

state = None  # the open remote's state, for the console


def main(scope):
    global state
    conf = settings.config(scope, DEFAULTS)
    root = scope.root
    W, H = scope.size
    status = ui.status(scope)
    st = state = {"tvs": [], "host": None, "phase": "wifi", "last": None, "sent": 0, "errors": 0}
    kept = scope.store()  # the TV last picked, while the board stays up
    w = scope.worker

    tv_dd = lv.dropdown(root)
    tv_dd.set_width(330)
    tv_dd.set_pos(W - 16 - 330, 10)
    tv_dd.set_options("looking for Rokus...")
    msg = ui.label(root, "", ui.font, ui.MUTED)
    msg.set_pos(W - 16 - 330, 60)
    msg.set_width(330)

    def send(key, label):
        host = st["host"]
        if host is None:
            msg.set_text("no TV yet")
            return

        def done(value, error):
            if error is not None:
                st["errors"] += 1
                msg.set_text("%s: %s" % (label, error))
            else:
                st["sent"] += 1
                msg.set_text("sent %s" % label)

        msg.set_text("%s..." % label)
        st["last"] = key
        w.submit(lambda: ecp.keypress(host, key), done, key="key:" + key)

    def btn(text, key, x, y, bw=104, bh=72, label=None, color=None):
        b, _ = ui.button(root, text, lambda: send(key, label or key), w=bw, h=bh, font=ui.big, color=color)
        b.set_pos(x, y)
        return b

    # The d-pad, OK in the middle, Back and the TV's Home above it.
    cx, cy = 190, 210
    btn(lv.SYMBOL.UP, "Up", cx - 52, cy - 128)
    btn(lv.SYMBOL.LEFT, "Left", cx - 52 - 116, cy - 36)
    btn("OK", "Select", cx - 52, cy - 36, label="OK", color=ui.WARN)
    btn(lv.SYMBOL.RIGHT, "Right", cx - 52 + 116, cy - 36)
    btn(lv.SYMBOL.DOWN, "Down", cx - 52, cy + 56)
    btn(lv.SYMBOL.LEFT + " Back", "Back", 24, 12, bw=150, bh=60, label="Back")
    btn(lv.SYMBOL.HOME + " TV", "Home", 206, 12, bw=150, bh=60, label="TV Home")
    # Playback, volume and power on the right.
    rx, ry = 420, 110
    btn(lv.SYMBOL.PREV, "Rev", rx, ry, bw=110, label="Rewind")
    btn(lv.SYMBOL.PLAY + lv.SYMBOL.PAUSE, "Play", rx + 122, ry, bw=110, label="Play/Pause")
    btn(lv.SYMBOL.NEXT, "Fwd", rx + 244, ry, bw=110, label="Fast forward")
    ry += 86
    btn(lv.SYMBOL.VOLUME_MID, "VolumeDown", rx, ry, bw=110, label="Volume down")
    btn(lv.SYMBOL.MUTE, "VolumeMute", rx + 122, ry, bw=110, label="Mute")
    btn(lv.SYMBOL.VOLUME_MAX, "VolumeUp", rx + 244, ry, bw=110, label="Volume up")
    ry += 86
    btn(lv.SYMBOL.POWER + " Power", "Power", rx, ry, bw=232, label="Power", color=ui.BAD)
    btn(lv.SYMBOL.REFRESH, "InstantReplay", rx + 244, ry, bw=110, label="Replay")

    def show_tvs():
        tvs = st["tvs"]
        if not tvs:
            tv_dd.set_options("no Roku found: tap to look again")
            return
        tv_dd.set_options("\n".join("%s (%s)" % (t["name"], t["host"].rsplit(".", 1)[-1]) for t in tvs))
        i = ecp.pick(tvs, conf.get("prefer"), kept.get("host"))
        if i is None:
            # A preferred TV that isn't on the network: send nothing rather
            # than drive whichever set answered first.
            st["host"] = None
            status.set_text("no TV matches %r: tap to choose" % (conf.get("prefer"),))
            return
        tv_dd.set_selected(i)
        choose(i)

    def choose(i):
        t = st["tvs"][i]
        st["host"] = t["host"]
        kept["host"] = t["host"]
        status.set_text("%s, %s" % (t["model"] or "Roku", t["power"] or "?"))

    def dd_changed(e):
        if st["tvs"]:
            choose(tv_dd.get_selected())
        else:
            look()

    tv_dd.add_event_cb(dd_changed, lv.EVENT.VALUE_CHANGED, None)

    def look():
        st["phase"] = "discovering"
        msg.set_text("looking for Rokus on the network...")

        def done(value, error):
            st["phase"] = "ready"
            if error is not None:
                msg.set_text("discovery failed: %s" % (error,))
                st["tvs"] = []
            else:
                st["tvs"] = value
                msg.set_text("%d Roku%s found" % (len(value), "" if len(value) == 1 else "s"))
            show_tvs()

        w.submit(ecp.discover, done, key="discover")

    def setup(t):
        if st["phase"] != "wifi":
            t.deinit()
            return
        if net.up():
            rssi = net.rssi()
            status.set_text("Wi-Fi %s dBm" % rssi if rssi else "Wi-Fi up")
            look()
        else:
            msg.set_text("joining Wi-Fi...")

    scope.every(500, setup)
