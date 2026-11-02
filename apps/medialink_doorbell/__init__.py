# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Doorbell: ring a house over the network, then talk to whoever answers.

Open Doorbell from the launcher on each side. Set ROLE in this file first:
"door" outside, "house" inside. A press of the door's button rings a chime
in the house. For a minute after that the door is hands-free: the visitor
just speaks, and the door sends while they do. Inside, hold the house's
button to answer, like a walkie-talkie. One side talks at a time.

The ring travels as a medialink event, which the link sends again until the
house says it arrived, so a lost packet doesn't lose a visitor.

Needs: a microphone and a speaker that boarddev.pcm_in() and pcm_out() reach,
which a PyDevices board package or pydevices-desktop provides, and a network:
a board on Wi-Fi with mdns in its firmware, or python-zeroconf on CPython.
On a computer, hold any key or a mouse button in the window. Without a
microphone, speaker, network port or mDNS, the screen says which one is
missing and the app stays open.
"""

import math

import boarddev
import events
import lvgl as lv
import medialink
import multimer
from audiodev import AudioFormat
from devkit import ui

# Change these to match your setup.
ROLE = "door"  # "door" outside, "house" inside
HOUSE = "doorbell-house"  # the house's name on the network
HOUSE_ADDRESS = None  # on the door, ("192.168.1.20", 47820) skips the search
PORT = 47820  # this side's port
BUTTON_PIN = None  # a board's button GPIO, pressed when low; None for the window
RATE = 16000  # samples a second
TALK_S = 60  # how long the door stays hands-free after a ring


def chime():
    """Two falling notes that fade, as 16-bit PCM."""
    pcm = bytearray()
    for freq, seconds in ((660, 0.35), (520, 0.6)):
        count = int(RATE * seconds)
        for n in range(count):
            level = int(9000 * (1 - n / count) * math.sin(2 * math.pi * freq * n / RATE))
            pcm += (level & 0xFFFF).to_bytes(2, "little")
    return bytes(pcm)


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
        ui.missing(scope, "no microphone", "Doorbell needs a microphone: %s." % (e,))
        return
    try:
        speaker = boarddev.pcm_out(audio, latency="low")
    except Exception as e:
        _close(mic)
        ui.missing(scope, "no speaker", "Doorbell needs a speaker: %s." % (e,))
        return

    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=3)
    except Exception as e:
        _close(speaker)
        _close(mic)
        ui.missing(scope, "no network port", "Doorbell couldn't use port %d: %s." % (PORT, e))
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
        finder = medialink.MDNS()
    except Exception as e:
        finder = None
        print("doorbell: no mDNS: %s" % (e,))

    voice = medialink.VoiceActivity(RATE) if ROLE == "door" else None
    intercom = medialink.Intercom(link, mic, speaker)
    ding_dong = None
    if ROLE == "house":
        if finder is not None:
            finder.advertise(HOUSE, PORT)
        ding_dong = chime()

    # The screen: the link's state on the status line, and what just
    # happened in the middle.
    scr = scope.root
    status = ui.status(scope)
    status.set_text("This is the %s" % ROLE)
    ui.label(scr, "Doorbell: %s" % ROLE, ui.big, ui.WHITE).align(lv.ALIGN.TOP_LEFT, 24, 80)
    if ROLE == "door":
        hint = "Press the button to ring the house."
    else:
        hint = "A ring plays a chime. Hold the button to answer."
    if finder is None and HOUSE_ADDRESS is None:
        hint = "No mDNS here: set HOUSE_ADDRESS to reach the house."
    ui.label(scr, hint, ui.font, ui.MUTED).align(lv.ALIGN.TOP_LEFT, 24, 124)
    msg = ui.label(scr, "", ui.big, ui.ACCENT)
    msg.align(lv.ALIGN.CENTER, 0, 0)

    def show(text):
        msg.set_text(text)

    # The search runs on the worker, so the screen doesn't wait on it. The
    find_key = "doorbell-find"
    searching = {"on": False}

    def connect(peers):
        for _name, address in peers:
            try:
                link.connect(address)
            except medialink.PeerUnreachable:
                pass

    def found(value, error):
        searching["on"] = False
        if error is not None:
            print("doorbell: search:", error)
            return
        connect(value)

    def look_for_house():
        """Find the house and say hello to it."""
        if HOUSE_ADDRESS:
            connect([(HOUSE, HOUSE_ADDRESS)])
        elif finder is not None and not searching["on"]:
            searching["on"] = True
            scope.worker.submit(lambda: finder.find(HOUSE, timeout=1), found, key=find_key)

    st = {
        "looked": multimer.ticks_add(multimer.ticks_ms(), -5000),
        "rang": None,
        "held": False,
        "alive": None,
        "heard": 0,
    }

    def close():
        intercom.close()
        link.close()

    scope.on_close(close)
    if finder is not None:
        scope.on_close(finder.deinit)

    def step():
        """One pass of the loop: the door's button, the house's chime and
        button, and the audio copy. The program's main loop calls it."""
        if scope.closed:
            return
        if ROLE == "door" and not link.alive:
            if multimer.ticks_diff(multimer.ticks_ms(), st["looked"]) > 3000:
                look_for_house()
                st["looked"] = multimer.ticks_ms()
        if link.alive != st["alive"]:
            st["alive"] = link.alive
            status.set_text("Connected" if st["alive"] else "Not connected: waiting")
        pressed = held()

        # At the door, a press rings, and the door listens for a while.
        if ROLE == "door":
            if pressed and not st["held"] and link.alive:
                try:
                    link.send_event("ring")
                    show("Ring! Speak when you are ready")
                    st["rang"] = multimer.ticks_ms()
                    intercom.voice = voice
                except medialink.PeerUnreachable:
                    show("The house didn't answer")
            if st["rang"] is not None and multimer.ticks_diff(multimer.ticks_ms(), st["rang"]) > TALK_S * 1000:
                st["rang"] = None
                intercom.voice = None
                voice.reset()

        # In the house, a ring plays the chime, and the button talks back.
        else:
            for event in link.events():
                if event == b"ring":
                    show("Ding dong: someone is at the door")
                    intercom.play(ding_dong)
            if pressed and not st["held"] and link.alive and not intercom.talking:
                try:
                    if intercom.press():
                        show("Talking to the door...")
                    else:
                        show("The door is talking")
                except medialink.PeerUnreachable:
                    show("No answer from the door")
            elif not pressed and intercom.talking:
                intercom.release()
        st["held"] = pressed
        intercom.service()

        # When the other side's turn ends, say so.
        if intercom.stats["spurts"] != st["heard"] and link.floor == medialink.IDLE:
            st["heard"] = intercom.stats["spurts"]
            show("Heard %s" % ("the visitor" if ROLE == "house" else "the house"))
        if not intercom.talking:
            multimer.sleep_ms(2)

    scope.foreground(step)
