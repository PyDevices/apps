# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch and listen to a camera in another room.

Open it from the appkit launcher on two devices. The one with the camera
keeps CAMERA = True: it sends what it sees and hears for as long as the
other side watches. The other keeps CAMERA = False: it finds the camera by
name, shows the pictures on its left-hand side and plays the sound. Sound
goes out between a picture's packets, so a big picture doesn't hold it up.

The status line and the panel say what each side is doing: how many
pictures went or came, how fast, how late they were and, on the watching
side, how often the speaker ran dry. The same lines go to the console.

Needs: on the camera side, a camera that board_peripherals.camera() opens
(an ESP32-P4 with cameraif), or on a computer a folder of JPEG files named
by PICTURES, and a microphone boarddev.pcm_in() reaches. On the watching
side, a display in board_config with jpegio (built into the firmware, or
Pillow on CPython) and a speaker. Both on one network, with mdns: a board
already on Wi-Fi, or a computer with python-zeroconf.

What is missing is named on screen, and the rest of the app keeps running.
Change the settings at the top of this file and open the app again.
"""

from devkit import ui

# Change these to match your setup.
CAMERA = True  # True on the side with the camera, False on the side that watches
CAMERA_NAME = "porch-camera"  # the camera side's name on the network
CAMERA_ADDRESS = None  # or ("192.168.1.20", PORT) to skip the search
PORT = 47800
PICTURES = None  # a folder of JPEG files to send in place of a camera
FPS = 10  # pictures a second, at most
SIZE = "VGA"  # a camera's picture size: "QVGA" is 320x240, "VGA" 640x480
QUALITY = 60  # 1 to 100; lower is smaller and quicker to send
RATE = 16000  # sound samples a second
STATS_MS = 5000  # how often the numbers are refreshed
LOOK_MS = 3000  # how often the watching side looks for the camera
PICTURE_SHARE = 2 / 3  # the part of the app's area the pictures take


def main(scope):
    # The libraries come in here, not at import time, so a missing one is
    # shown on screen rather than failing the launcher.
    try:
        import boarddev
        import medialink
        import multimer
        from audiodev import AudioFormat
    except ImportError as e:
        ui.missing(scope, "missing: medialink", "Surveillance camera needs medialink, boarddev, multimer and audiodev: %s." % (e,))
        return

    scr = scope.root
    rect = scope.rect or (0, 0, scope.size[0], scope.size[1])
    status = ui.status(scope)
    status.set_text("starting")

    # A camera side needs a camera; a watching side needs a display.
    camera = None
    if CAMERA:
        if PICTURES:
            camera = medialink.FileCamera(PICTURES)
        else:
            try:
                import board_peripherals
                import cameraif
            except ImportError as e:
                ui.missing(scope, "no camera", "No camera here: this app's camera side needs board_peripherals and cameraif (an ESP32-P4), or PICTURES set to a folder of JPEG files. %s" % (e,))
                return
            # Have the chip scale each picture down and encode it, so it is
            # quick to send and the other side decodes it in hardware.
            camera = board_peripherals.camera()
            camera.reconfigure(pixel_format=cameraif.PixelFormat.JPEG, frame_size=getattr(cameraif.FrameSize, SIZE))
            camera.quality = QUALITY
    else:
        try:
            from board_config import display_drv
        except ImportError as e:
            ui.missing(scope, "no display", "No display here: the watching side needs a display in board_config. %s" % (e,))
            return

    # Open the link, with sound on it one way and pictures the same way.
    link = None
    video = None
    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
        video = medialink.Video(link)
    except Exception as e:
        ui.missing(scope, "no network", "No network port here: %s. Connect to Wi-Fi, or use a computer with a free UDP port %d." % (e, PORT))
        if link is not None:
            link.close()
        return

    # Each thing that's missing is named in the notes; the rest still runs.
    notes_text = []

    # Find and be found by name. Without mdns, CAMERA_ADDRESS still works.
    finder = None
    try:
        finder = medialink.MDNS()
    except Exception as e:
        notes_text.append("no mdns, so no search: %s" % (e,))
        print("surveillance camera: mdns:", e)

    # The sound: the camera side's microphone, or the watching side's speaker.
    intercom = None
    try:
        audio = AudioFormat(RATE, 1, 16)
        if CAMERA:
            intercom = medialink.Intercom(link, boarddev.pcm_in(audio), None)
        else:
            intercom = medialink.Intercom(link, None, boarddev.pcm_out(audio, latency="low"))
    except Exception as e:
        notes_text.append("no sound: %s" % (e,))
        print("surveillance camera: sound:", e)

    # The pictures take the left part of the area; the status is on the right.
    picture_w = int(rect[2] * PICTURE_SHARE)
    screen = None
    if not CAMERA:
        try:
            screen = medialink.Screen(display_drv, rect=(rect[0], rect[1], picture_w, rect[3]))
        except Exception as e:
            notes_text.append("no picture decoder (jpegio): %s" % (e,))
            print("surveillance camera: screen:", e)

    # The status on the right: the numbers, as the console gets them.
    left = picture_w + 16 if not CAMERA else 16
    info = ui.label(scr, "", ui.small, ui.WHITE)
    info.set_pos(left, 16)
    info.set_width(max(120, rect[2] - left - 16))
    notes = ui.label(scr, "\n".join(notes_text), ui.tiny, ui.MUTED)
    notes.set_pos(left, rect[3] - 80)
    notes.set_width(max(120, rect[2] - left - 16))

    def say(line):
        info.set_text(line)
        print("surveillance camera:", line)

    if CAMERA:
        if finder is not None:
            finder.advertise(CAMERA_NAME, PORT)
        status.set_text("waiting to be watched")
        say("This is %r, waiting to be watched" % CAMERA_NAME)
    else:
        status.set_text("looking for the camera")
        say("Looking for %r" % CAMERA_NAME)

    # The search runs on the worker, so the picture doesn't wait on it. The
    find_key = "surveillance-find"
    searching = {"on": False}

    def connect(peers):
        for _name, address in peers:
            try:
                link.connect(address)
                status.set_text("watching")
                say("Watching %r at %s" % (CAMERA_NAME, address))
            except medialink.PeerUnreachable:
                pass

    def found(value, error):
        searching["on"] = False
        if error is not None:
            print("surveillance camera: search:", error)
            return
        connect(value)

    def look_for_camera():
        """Find the camera by name and say hello to it."""
        if CAMERA_ADDRESS:
            connect([(CAMERA_NAME, CAMERA_ADDRESS)])
        elif finder is not None and not searching["on"]:
            searching["on"] = True
            scope.worker.submit(lambda: finder.find(CAMERA_NAME, timeout=1), found, key=find_key)

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

    now = multimer.ticks_ms()
    st = {"looked": now, "taken": now, "reported": now, "counted": 0}

    def step():
        # One pass of the example's loop, run by the program's main loop.
        now = multimer.ticks_ms()
        if CAMERA:
            # Talk whenever someone watches, and take a picture whenever the
            # last one has gone and the next is due.
            if intercom is not None:
                if link.alive and not intercom.talking:
                    try:
                        intercom.press()
                    except medialink.PeerUnreachable:
                        pass
                elif intercom.talking and not link.alive:
                    intercom.release()
            if link.alive and video.ready and multimer.ticks_diff(now, st["taken"]) >= 1000 // FPS:
                st["taken"] = now
                jpeg = camera.take()
                if jpeg is not None:
                    video.send(bytes(jpeg), st["taken"])
            video.service()
        else:
            # Look for the camera while it isn't there, and show each picture.
            if not link.alive and multimer.ticks_diff(now, st["looked"]) > LOOK_MS:
                look_for_camera()
                st["looked"] = multimer.ticks_ms()
            frame = video.receive()
            if frame is not None and screen is not None:
                screen.show(frame.payload)
        if intercom is not None:
            intercom.service()

        # Every few seconds, say how it is going.
        if multimer.ticks_diff(now, st["reported"]) >= STATS_MS:
            total = video.stats["sent" if CAMERA else "received"]
            rate = (total - st["counted"]) * 1000 / multimer.ticks_diff(now, st["reported"])
            if CAMERA:
                say("%d pictures sent, %.1f a second" % (total, rate))
            else:
                latency = intercom.stats["latency_ms"] if intercom is not None else None
                underruns = intercom.stats["underruns"] if intercom is not None else 0
                say("%d pictures shown, %.1f a second, %s ms late at most; sound %s ms late, %d underruns"
                    % (total, rate, video.stats["max_latency_ms"], latency, underruns))
                video.stats["max_latency_ms"] = None
            st["counted"], st["reported"] = total, now
        if intercom is None or not intercom.talking:
            multimer.sleep_ms(1)

    scope.foreground(step)
