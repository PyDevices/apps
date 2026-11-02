# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""See each other, and talk while you hold a button.

Open it from the appkit launcher on two devices, each with a camera, a
screen, a microphone and a speaker, each with its own NAME and the other's
as PEER. They find each other by name, and each shows what the other's
camera sees. Hold the button to talk; one side talks at a time, as on a
walkie-talkie, and the pictures keep coming both ways while you do.

The panel on the right says how many pictures went and came, how late they
were, and how the sound went. The same lines go to the console.

Needs: on each side, a camera that board_peripherals.camera() opens (an
ESP32-P4 with cameraif), or on a computer a folder of JPEG files named by
PICTURES; a display in board_config with jpegio (built into the firmware,
or Pillow on CPython); a microphone and a speaker boarddev reaches; and a
network with mdns. On a computer, hold the space bar or a mouse button in
the window that opens.

What is missing is named on screen, and the rest of the call keeps running.
Change the settings at the top of this file and open the app again.
"""

from devkit import ui

# Change these to match your setup.
NAME = "phone-1"  # this side's name on the network
PEER = "phone-2"  # the other side's
PEER_ADDRESS = None  # or ("192.168.1.20", PORT) to skip the search
PORT = 47800
BUTTON_PIN = None  # a board's button GPIO, pressed when low; None for the window
PICTURES = None  # a folder of JPEG files to send in place of a camera
FPS = 10  # pictures a second, at most
SIZE = "QVGA"  # a camera's picture size: "QVGA" is 320x240, "VGA" 640x480
QUALITY = 60  # 1 to 100; lower is smaller and quicker to send
RATE = 16000  # sound samples a second
LOOK_MS = 3000  # how often a side that isn't connected looks for its peer
STATS_MS = 5000  # how often the numbers are refreshed
PICTURE_SHARE = 2 / 3  # the part of the app's area the pictures take


def main(scope):
    # The libraries come in here, not at import time, so a missing one is
    # shown on screen rather than failing the launcher.
    try:
        import boarddev
        import events
        import medialink
        import multimer
        from audiodev import AudioFormat
    except ImportError as e:
        ui.missing(scope, "missing: medialink", "The videophone needs medialink, boarddev, multimer, audiodev and events: %s." % (e,))
        return

    scr = scope.root
    rect = scope.rect or (0, 0, scope.size[0], scope.size[1])
    status = ui.status(scope)
    status.set_text("starting")
    notes_text = []

    # The camera: a camera on a board, or a folder of pictures on a computer.
    # Without one, this side still shows the other's pictures and talks.
    camera = None
    try:
        if PICTURES:
            camera = medialink.FileCamera(PICTURES)
        else:
            import board_peripherals
            import cameraif

            camera = board_peripherals.camera()
            # Have the chip scale each picture down and encode it, so it is
            # quick to send and the other side decodes it in hardware.
            camera.reconfigure(pixel_format=cameraif.PixelFormat.JPEG, frame_size=getattr(cameraif.FrameSize, SIZE))
            camera.quality = QUALITY
    except Exception as e:
        if camera is not None:
            camera.deinit()
        camera = None
        notes_text.append("No camera here, so pictures aren't sent.")
        print("videophone: camera:", e)

    # The screen: the other side's pictures, on the left of the app's area.
    screen = None
    picture_w = int(rect[2] * PICTURE_SHARE)
    try:
        from board_config import display_drv

        screen = medialink.Screen(display_drv, rect=(rect[0], rect[1], picture_w, rect[3]))
    except Exception as e:
        notes_text.append("no display: pictures aren't shown (%s)" % (e,))
        print("videophone: screen:", e)

    # The button is a pin on a board, or a key or mouse button in the window.
    st = {"held": False, "refused": False, "searching": False, "taken": 0, "counted": 0, "reported": 0}
    pin = None
    if BUTTON_PIN is not None:
        from machine import Pin

        pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

        def held():
            return not pin.value()

    else:
        def down(event):
            st["held"] = True

        def up(event):
            st["held"] = False

        scope.on([events.KEYDOWN, events.MOUSEBUTTONDOWN], down)
        scope.on([events.KEYUP, events.MOUSEBUTTONUP], up)

        def held():
            return st["held"]

    # Listen on PORT with sound and pictures on one link. Without a network
    # there is no call, so this one stops the app, and says why.
    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
    except Exception as e:
        if camera is not None:
            camera.deinit()
        ui.missing(scope, "no network", "No network port here: %s. Connect to Wi-Fi, or use a computer with a free UDP port %d." % (e, PORT))
        return

    # The sound: the microphone the button talks into, the speaker the other
    # side's voice comes out of. Either may be missing.
    audio = AudioFormat(RATE, 1, 16)
    mic = speaker = None
    try:
        mic = boarddev.pcm_in(audio)
    except Exception as e:
        notes_text.append("no microphone: can't talk (%s)" % (e,))
        print("videophone: microphone:", e)
    try:
        speaker = boarddev.pcm_out(audio, latency="low")
    except Exception as e:
        notes_text.append("no speaker: can't hear (%s)" % (e,))
        print("videophone: speaker:", e)
    intercom = None
    if mic is not None or speaker is not None:
        intercom = medialink.Intercom(link, mic, speaker)
    video = medialink.Video(link)

    # Announce this side by name, and look for the peer by name.
    finder = None
    try:
        finder = medialink.MDNS()
        finder.advertise(NAME, PORT)
    except Exception as e:
        finder = None
        notes_text.append("no mdns, so no search: %s" % (e,))
        print("videophone: mdns:", e)

    # The panel on the right: the numbers, as the console gets them.
    left = picture_w + 16
    info = ui.label(scr, "", ui.small, ui.WHITE)
    info.set_pos(left, 16)
    info.set_width(max(120, rect[2] - left - 16))
    notes = ui.label(scr, "\n".join(notes_text), ui.tiny, ui.MUTED)
    notes.set_pos(left, rect[3] - 80)
    notes.set_width(max(120, rect[2] - left - 16))

    def say(line):
        info.set_text(line)
        print(line)

    say("This is %r; looking for %r" % (NAME, PEER))
    status.set_text("looking for %s" % PEER)
    for line in notes_text:
        print("videophone:", line)

    def connect(found):
        for _name, address in found:
            try:
                link.connect(address)
                status.set_text("connected")
                say("Connected to %r at %s" % (PEER, address))
            except medialink.PeerUnreachable:
                pass

    def found(value, error):
        st["searching"] = False
        if error is not None:
            print("videophone: search:", error)
            return
        connect(value)

    def look(t):
        # Call the peer while it isn't there. The search can take a second,
        # so it runs on the worker and the connect happens on this thread.
        if link.alive or st["searching"]:
            return
        if PEER_ADDRESS:
            connect([(PEER, PEER_ADDRESS)])
        elif finder is not None:
            st["searching"] = True
            scope.worker.submit(lambda: finder.find(PEER, timeout=1), found, key="videophone-find")

    def report(t):
        # Every few seconds, say how it is going.
        total_shown = video.stats["received"]
        sent = video.stats["sent"]
        latency = (intercom.stats["latency_ms"] or 0) if intercom is not None else 0
        underruns = intercom.stats["underruns"] if intercom is not None else 0
        say("Pictures: %d sent, %d shown, %s ms late at most. Sound: %s ms late, %d underruns"
            % (sent, total_shown, (video.stats["max_latency_ms"] or 0), latency, underruns))
        video.stats["max_latency_ms"] = None

    def close():
        # Release what the app opened, in the order the example does.
        if intercom is not None:
            intercom.close()
        link.close()
        if camera is not None:
            camera.deinit()

    scope.on_close(close)
    if finder is not None:
        scope.on_close(finder.deinit)
    scope.every(LOOK_MS, look)
    scope.every(STATS_MS, report)

    def step():
        # One pass of the example's loop, run by the program's main loop.
        now = multimer.ticks_ms()
        pressed = held()
        if intercom is not None:
            # Call the peer while it isn't there; talk while the button is held.
            if pressed and mic is not None and not intercom.talking and link.alive and not st["refused"]:
                try:
                    st["refused"] = not intercom.press()
                    status.set_text("the other side is talking" if st["refused"] else "talking")
                    print("The other side is talking" if st["refused"] else "Talking...")
                except medialink.PeerUnreachable:
                    st["refused"] = True
                    status.set_text("no answer")
                    print("No answer from the other side")
            elif not pressed:
                st["refused"] = False
                if intercom.talking:
                    intercom.release()
            intercom.service()

        # Send a picture whenever the last has gone and the next is due.
        if camera is not None and link.alive and video.ready and multimer.ticks_diff(now, st["taken"]) >= 1000 // FPS:
            st["taken"] = now
            jpeg = camera.take()
            if jpeg is not None:
                video.send(bytes(jpeg), now)
        video.service()

        # Show each one that arrives.
        frame = video.receive()
        if frame is not None and screen is not None:
            screen.show(frame.payload)
        if intercom is None or not intercom.talking:
            multimer.sleep_ms(1)

    scope.foreground(step)
