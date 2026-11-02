# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Listen to a room from another one, like a baby monitor.

Open it on two devices. On the monitor beside the cot it listens all the
time but sends only while there is sound worth sending, a voice or a cry,
and goes quiet again a moment after it stops. On the listener, where you
are, it plays what comes and shows "Sound" while it plays and "Quiet" when
it stops, so you can see at a glance which it is.

The monitor decides what is worth sending with medialink.VoiceActivity:
audiodsp's speech detector where the firmware has it, and a level gate
over the room's own noise elsewhere.

Needs: on the monitor, a microphone that boarddev.pcm_in() reaches; on the
listener, a speaker that boarddev.pcm_out() reaches. A PyDevices board
package or pydevices-desktop provides both. Both need a network: a board
already on Wi-Fi with mdns in its firmware, or python-zeroconf on CPython.
Set PEER_ADDRESS on the listener to skip the search. A device that lacks
any of these says so on screen and the app stays open.

Open it from the appkit launcher: pick "Baby monitor" on the home screen.
Set ROLE on each device first, since the same app runs on both.
"""

from devkit import ui

# Change these to match your setup.
ROLE = "monitor"  # "monitor" in the room to hear, "listener" where you are
NAME = "baby-monitor"  # the monitor's name on the network
PEER_ADDRESS = None  # on the listener, ("192.168.1.20", 47810) skips the search
PORT = 47810  # this side's port
RATE = 16000  # samples a second
HOLD_MS = 1500  # how long the monitor keeps sending after the last sound


def main(scope):
    try:
        import boarddev
        import medialink
        import multimer
        from audiodev import AudioFormat
    except ImportError as e:
        ui.missing(
            scope,
            "missing: medialink",
            "The baby monitor needs medialink, multimer and audiodev: %s." % (e,),
        )
        return

    scr = scope.root
    status = ui.status(scope)
    status.set_text("starting")

    # The screen: what this device is doing, the link, and the sound.
    if ROLE == "monitor":
        role_text = "Monitor %r in the room" % NAME
    else:
        role_text = "Listening for %r" % NAME
    role = ui.label(scr, role_text, ui.big, ui.WHITE)
    role.set_pos(40, 40)
    link_line = ui.label(scr, "Not connected: waiting", ui.font, ui.MUTED)
    link_line.set_pos(40, 100)
    sound_line = ui.label(scr, "Quiet", ui.huge, ui.ACCENT)
    sound_line.set_pos(40, 170)
    note = ui.label(scr, "", ui.font, ui.WARN)
    note.set_pos(40, 300)
    note.set_width(scope.size[0] - 80)

    # The link and the search for the other side. Each may be missing here.
    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
    except Exception as e:
        note.set_text("No network port here: %s" % (e,))
        return

    finder = None
    try:
        finder = medialink.MDNS()
        if ROLE == "monitor":
            finder.advertise(NAME, PORT)
    except Exception as e:
        finder = None
        note.set_text("No name search here, so set PEER_ADDRESS: %s" % (e,))

    # The sound: a microphone on the monitor, a speaker on the listener.
    # Without one, the screen says so and nothing else runs.
    audio = AudioFormat(RATE, 1, 16)
    intercom = None
    try:
        if ROLE == "monitor":
            voice = medialink.VoiceActivity(RATE, hold_ms=HOLD_MS)
            intercom = medialink.Intercom(link, boarddev.pcm_in(audio), None, voice=voice)
            role.set_text("Monitor %r, deciding by %s" % (NAME, voice.detector))
        else:
            intercom = medialink.Intercom(link, None, boarddev.pcm_out(audio, latency="low"))
    except Exception as e:
        what = "microphone" if ROLE == "monitor" else "speaker"
        sound_line.set_text("No " + what)
        note.set_text("No %s here: %s" % (what, e))
        sound_line.set_style_text_color(ui.BAD, 0)

    def close():
        if intercom is not None:
            intercom.close()
        link.close()
        if finder is not None:
            finder.deinit()

    scope.on_close(close)

    if intercom is None:
        status.set_text("no %s" % ("microphone" if ROLE == "monitor" else "speaker"))
        return

    def look_for_monitor():
        """Find the monitor and say hello to it."""
        if PEER_ADDRESS:
            found = [(NAME, PEER_ADDRESS)]
        elif finder is not None:
            found = finder.find(NAME, timeout=1)
        else:
            found = []
        for _name, address in found:
            try:
                link.connect(address)
            except medialink.PeerUnreachable:
                pass

    # The link runs in the main loop, one pass at a time, so the screen
    # stays responsive while audio moves.
    st = {
        "looked": multimer.ticks_add(multimer.ticks_ms(), -5000),
        "alive": None,
        "sound": False,
        "started": multimer.ticks_ms(),
    }

    def step():
        if ROLE != "monitor" and not link.alive:
            if multimer.ticks_diff(multimer.ticks_ms(), st["looked"]) > 3000:
                look_for_monitor()
                st["looked"] = multimer.ticks_ms()
        if link.alive != st["alive"]:
            st["alive"] = link.alive
            status.set_text("connected" if st["alive"] else "not connected: waiting")
            link_line.set_text("Connected" if st["alive"] else "Not connected: waiting")
        intercom.service()

        # On the monitor a turn is its own sending; on the listener, the
        # monitor's.
        if ROLE == "monitor":
            sound = intercom.talking
        else:
            sound = link.floor == medialink.LISTENING
        if sound != st["sound"]:
            st["sound"] = sound
            if sound:
                st["started"] = multimer.ticks_ms()
                sound_line.set_text("Sound")
                sound_line.set_style_text_color(ui.GOOD, 0)
            else:
                heard = multimer.ticks_diff(multimer.ticks_ms(), st["started"])
                sound_line.set_text("Quiet")
                sound_line.set_style_text_color(ui.ACCENT, 0)
                note.set_text("Last sound lasted %d ms" % heard)
        if not intercom.talking:
            multimer.sleep_ms(2)

    scope.foreground(step)
