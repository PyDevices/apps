# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Walkie-talkie: talk to another device while you hold a button.

Open Walkie-talkie from the appkit launcher on two boards, or on a board and
a computer, each with its own NAME and the other's as PEER. They find each
other on the network by name. Hold the button and speak; let go, and the
other one hears you. One talks at a time: while the other is talking, the
button does nothing.

The screen shows whether the peer is here, and a line when a turn ends: how
many frames went or came, how long the sound took from one microphone to the
other speaker, and how often the speaker ran dry waiting for the network. If
the network drops, the two find each other again when it comes back.

They find each other on the network they are on. Where the Wi-Fi is weak, set
HOTSPOT_PASSWORD on both: one board starts an access point, the other joins
it, and both go back to their own network when the app closes.

Needs: a microphone and a speaker that boarddev.pcm_in() and pcm_out() reach,
which a PyDevices board package or pydevices-desktop provides, and a network:
a board already on Wi-Fi, with mdns in its firmware. On a computer, hold any
key or a mouse button in the window; CPython also needs python-zeroconf for
mdns. Without a microphone, speaker, network port or mDNS, the screen says
which one is missing and the app stays open.
"""

import boarddev
import events
import lvgl as lv
import medialink
import multimer
from audiodev import AudioFormat
from touchkit import ui

# Change these to match your setup.
NAME = "walkie-1"  # this side's name on the network
PEER = "walkie-2"  # the other side's
PEER_ADDRESS = None  # or ("192.168.1.20", PORT) to skip the search
PORT = 47800
BUTTON_PIN = None  # a board's button GPIO, pressed when low; None for the window
RATE = 16000  # samples a second
HOTSPOT_PASSWORD = None  # a password to talk over a hotspot one board starts


def _close(thing):
    """Close a device that may or may not be open, without raising."""
    if thing is None:
        return
    for name in ("close", "deinit"):
        method = getattr(thing, name, None)
        if method is not None:
            try:
                method()
            except Exception:
                pass
            return


def main(scope):
    # Open the microphone and the speaker at one format: mono, 16-bit.
    audio = AudioFormat(RATE, 1, 16)
    try:
        mic = boarddev.pcm_in(audio)
    except Exception as e:
        ui.missing(scope, "no microphone", "Walkie-talkie needs a microphone: %s." % (e,))
        return
    try:
        speaker = boarddev.pcm_out(audio, latency="low")
    except Exception as e:
        _close(mic)
        ui.missing(scope, "no speaker", "Walkie-talkie needs a speaker: %s." % (e,))
        return

    # Listen on PORT, and announce this side by name.
    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
    except Exception as e:
        _close(speaker)
        _close(mic)
        ui.missing(scope, "no network port", "Walkie-talkie couldn't use port %d: %s." % (PORT, e))
        return

    # The button is a pin on a board, or a key or mouse button in a window.
    # The window's events arrive through the app's subscriptions.
    pad = {"held": False}
    if BUTTON_PIN is not None:
        from machine import Pin

        pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

        def held():
            return not pin.value()

    else:
        def down(event):
            pad["held"] = True

        def up(event):
            pad["held"] = False

        scope.on((events.KEYDOWN, events.MOUSEBUTTONDOWN), down)
        scope.on((events.KEYUP, events.MOUSEBUTTONUP), up)

        def held():
            return pad["held"]

    try:
        finder = medialink.Hotspot(HOTSPOT_PASSWORD) if HOTSPOT_PASSWORD else medialink.MDNS()
    except Exception as e:
        finder = None
        print("walkie-talkie: no mDNS: %s" % (e,))
    if finder is not None:
        finder.advertise(NAME, PORT)

    intercom = medialink.Intercom(link, mic, speaker)

    # The screen: the peer's state on the status line, and each turn in the
    # middle.
    scr = scope.root
    status = ui.status(scope)
    status.set_text("Looking for %r" % (PEER,))
    ui.label(scr, "Walkie-talkie: %s" % NAME, ui.big, ui.WHITE).align(lv.ALIGN.TOP_LEFT, 24, 80)
    if finder is None and PEER_ADDRESS is None:
        hint = "No mDNS here: set PEER_ADDRESS to reach %r." % (PEER,)
    else:
        hint = "Hold the button to talk to %r." % (PEER,)
    ui.label(scr, hint, ui.font, ui.MUTED).align(lv.ALIGN.TOP_LEFT, 24, 124)
    msg = ui.label(scr, "", ui.big, ui.ACCENT)
    msg.align(lv.ALIGN.CENTER, 0, 0)

    def show(text):
        msg.set_text(text)
        print(text)

    # The search runs on the worker, so the screen doesn't wait on it. The
    find_key = "walkie-talkie-find"
    searching = {"on": False}

    def connect(peers):
        for _name, address in peers:
            try:
                link.connect(address)
                print("Connected to %r at %s" % (PEER, address))
            except medialink.PeerUnreachable:
                pass

    def found(value, error):
        searching["on"] = False
        if error is not None:
            print("walkie-talkie: search:", error)
            return
        connect(value)

    def look_for_peer():
        """Find the peer and say hello. Either side may find the other first."""
        if PEER_ADDRESS:
            connect([(PEER, PEER_ADDRESS)])
        elif finder is not None and not searching["on"]:
            searching["on"] = True
            scope.worker.submit(lambda: finder.find(PEER, timeout=1), found, key=find_key)

    st = {
        "looked": multimer.ticks_add(multimer.ticks_ms(), -5000),
        "was_alive": False,
        "refused": False,
        "heard": 0,
        "sent": 0,
        "played": 0,
    }

    def close():
        intercom.close()
        link.close()

    scope.on_close(close)
    if finder is not None:
        scope.on_close(finder.deinit)

    def step():
        """One pass of the loop: find the peer, talk while the button is
        held, and listen the rest of the time. The program's main loop
        calls it."""
        if scope.closed:
            return
        if not link.alive and multimer.ticks_diff(multimer.ticks_ms(), st["looked"]) > 3000:
            look_for_peer()
            st["looked"] = multimer.ticks_ms()
        if link.alive != st["was_alive"]:
            st["was_alive"] = link.alive
            status.set_text("Peer here" if st["was_alive"] else "Peer gone: waiting for it")
        pressed = held()
        if pressed and not intercom.talking and link.alive and not st["refused"]:
            try:
                if intercom.press():
                    show("Talking...")
                    st["sent"] = intercom.stats["sent"]
                else:
                    show("The other side is talking")
                    st["refused"] = True
            except medialink.PeerUnreachable:
                show("No answer from the other side")
                st["refused"] = True
        elif not pressed:
            st["refused"] = False
            if intercom.talking:
                intercom.release()
                show("Sent %d frames" % (intercom.stats["sent"] - st["sent"]))
        intercom.service()

        # When the peer's turn ends, say how it went.
        if intercom.stats["spurts"] != st["heard"] and link.floor == medialink.IDLE:
            st["heard"] = intercom.stats["spurts"]
            show("Heard %d frames, %s ms mouth to ear, %d underruns so far, round trip %s ms"
                 % (intercom.stats["played"] - st["played"], intercom.stats["latency_ms"],
                    intercom.stats["underruns"], link.rtt_ms))
            st["played"] = intercom.stats["played"]
        if not intercom.talking:
            multimer.sleep_ms(2)

    scope.foreground(step)
