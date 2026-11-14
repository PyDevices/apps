# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hands free: talk to another device without a button.

Each side listens to its own microphone. When someone starts to speak, that
side takes the turn and sends, from a moment before the first word so the
word isn't clipped. When they stop, the turn goes back. One side talks at a
time: while the other is talking, this one plays and doesn't listen, so it
doesn't send the other side's voice back.

The screen shows whose turn it is and the state of the link to the peer.
medialink.VoiceActivity decides what counts as speech: audiodsp's speech
detector where the firmware has it, and a level gate over the room's own
noise elsewhere. Set WAKE_WORD to a microWakeWord model's manifest and a turn
starts only with the word, so the room's talk stays home. That needs
firmware with tflite and audiodsp. A model under ``/sd`` is read from the SD
card, mounted just while the model loads.

Needs: a microphone and a speaker that boarddev.pcm_in() and pcm_out()
reach, which a PyDevices board package or pydevices-desktop provides, and a
network: a board already on Wi-Fi with mdns in its firmware, or
python-zeroconf on CPython. Headphones on a computer keep its speaker out of
its microphone. A piece that is missing is named on the screen, and the rest
of the app keeps running.

To open it, put this app in the apps folder of an app set, run appkit.run()
from its main.py, and choose "Hands free" on the home screen.
"""

import boarddev
import medialink
import multimer
from audiodev import AudioFormat
from touchkit import ui

# Change these to match your setup.
NAME = "hands-free-1"  # this side's name on the network
PEER = "hands-free-2"  # the other side's
PEER_ADDRESS = None  # or ("192.168.1.20", 47830) to skip the search
PORT = 47830  # this side's port
RATE = 16000  # samples a second
HOLD_MS = 800  # how long a turn lasts after the last word
WAKE_WORD = None  # or "/sd/models/hey_jarvis.json" to start a turn by name

TICK_MS = 100  # how often the screen and the link are checked
LOOK_EVERY_MS = 3000  # between searches for the peer while it's gone


def _wake_word(voice):
    """The wake word in front of *voice*. A model on the card (``/sd/...``)
    mounts it for the load, unless something else already has it there."""
    if not WAKE_WORD.startswith("/sd/"):
        return medialink.WakeWord(WAKE_WORD, RATE, voice=voice)
    import os

    try:
        os.listdir("/sd")
        card = None  # someone else's mount: leave it
    except OSError:
        import board_peripherals as bp

        card = bp.sdcard()
        os.mount(card, "/sd", readonly=True)
    try:
        return medialink.WakeWord(WAKE_WORD, RATE, voice=voice)
    finally:
        if card is not None:
            os.umount("/sd")
            card.deinit()


def main(scope):
    scr = scope.root
    status = ui.status(scope)
    status.set_text("starting")

    # The audio and the network. Each piece that fails is named on the screen
    # and the app runs without it.
    intercom = link = finder = None
    try:
        audio = AudioFormat(RATE, 1, 16)
        voice = medialink.VoiceActivity(RATE, hold_ms=HOLD_MS)
        if WAKE_WORD:
            voice = _wake_word(voice)
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
        intercom = medialink.Intercom(
            link, boarddev.pcm_in(audio), boarddev.pcm_out(audio, latency="low"), voice=voice
        )
    except Exception as e:
        ui.missing(
            scope,
            "no microphone, speaker or network port",
            "Hands free needs a microphone and a speaker that boarddev reaches, "
            "and a UDP port %d: %s." % (PORT, e),
        )
        print("hands free: audio or network:", e)
        if link is not None:
            link.close()
        return

    heading = ui.label(scr, "Hands free", ui.big, ui.WHITE)
    heading.set_pos(40, 40)
    who = ui.label(scr, "", ui.font, ui.MUTED)
    who.set_pos(40, 110)
    turn = ui.label(scr, "Quiet", ui.huge, ui.ACCENT)
    turn.set_pos(40, 170)
    peer = ui.label(scr, "", ui.big, ui.WHITE)
    peer.set_pos(40, 290)
    note = ui.label(scr, "", ui.small, ui.MUTED)
    note.set_pos(40, 350)
    note.set_width(scope.size[0] - 80)

    try:
        finder = medialink.MDNS()
        finder.advertise(NAME, PORT)
        finder_note = ""
    except Exception as e:
        if finder is not None:
            finder.deinit()
        finder = None
        finder_note = "No mDNS here (%s), so the peer is found only at PEER_ADDRESS." % (e,)
        print("hands free: mdns:", e)

    who.set_text("This is %r, deciding by %s" % (NAME, voice.detector))
    note.set_text(finder_note)
    print("This is %r, deciding by %s; looking for %r" % (NAME, voice.detector, PEER))

    # The search runs on the worker, so the link check doesn't wait on it. The
    find_key = "hands-free-find"
    searching = {"on": False}

    def close():
        try:
            intercom.close()
        except Exception as e:
            print("hands free: intercom close:", e)
        link.close()

    scope.on_close(close)
    if finder is not None:
        scope.on_close(finder.deinit)

    st = {"looked": multimer.ticks_add(multimer.ticks_ms(), -LOOK_EVERY_MS - 1),
          "was_alive": False, "was_floor": medialink.IDLE}

    def connect(peers):
        for _name, address in peers:
            try:
                link.connect(address)
            except medialink.PeerUnreachable:
                pass

    def found(value, error):
        searching["on"] = False
        if error is not None:
            print("hands free: search:", error)
            return
        connect(value)

    def look_for_peer():
        """Find the peer and say hello. Either side may find the other first."""
        if PEER_ADDRESS:
            connect([(PEER, PEER_ADDRESS)])
        elif finder is not None and not searching["on"]:
            searching["on"] = True
            scope.worker.submit(lambda: finder.find(PEER, timeout=1), found, key=find_key)

    def check(t):
        # The link and the floor, shown on the screen and printed as they change.
        if not link.alive and multimer.ticks_diff(multimer.ticks_ms(), st["looked"]) > LOOK_EVERY_MS:
            look_for_peer()
            st["looked"] = multimer.ticks_ms()
        if link.alive != st["was_alive"]:
            st["was_alive"] = link.alive
            print("Peer", "here" if link.alive else "gone: waiting for it")
        if link.alive:
            peer.set_text("Peer %s is here" % (PEER,))
            status.set_text("connected to %s" % (PEER,))
        else:
            peer.set_text("Waiting for %s" % (PEER,))
            status.set_text("waiting for %s" % (PEER,))

        if link.floor != st["was_floor"]:
            st["was_floor"] = link.floor
            if st["was_floor"] == medialink.TALKING:
                print("You're talking")
                turn.set_text("You're talking")
            elif st["was_floor"] == medialink.LISTENING:
                print("The other side is talking")
                turn.set_text("They're talking")
            else:
                print("Quiet")
                turn.set_text("Quiet")

    def step():
        # The audio loop: move one step, then give the others a moment when
        # nobody is talking. The program's main loop calls it over and over.
        intercom.service()
        if not intercom.talking:
            multimer.sleep_ms(2)

    scope.every(TICK_MS, check)
    scope.foreground(step)
