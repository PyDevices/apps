# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Video doorbell: see who is at the door, and talk to them.

Open it on two devices. On the one at the door, with a camera, leave
DOOR = True: it advertises itself on the network and sends a picture of
what its camera sees a few times a second. On the one inside, with a
screen, set DOOR = False: it finds the door by name and shows its pictures.
Each side has a button to hold while talking, as on a walkie-talkie: the
visitor presses the doorbell to speak, and you press yours to answer.

The inside side says when the visitor starts talking, and every few
seconds how many pictures it has shown and how late they were.

Needs: at the door, a camera that board_peripherals.camera() opens (an
ESP32-P4 with cameraif), or on a computer a folder of JPEG files named by
PICTURES. Inside, a display and a JPEG decoder (jpegio, built into the
firmware, or Pillow on CPython). On both, a microphone and a speaker
boarddev reaches, and a network with mdns. On a computer, hold the space
bar or a mouse button in the window that opens. Whatever is missing shows
on the screen, and the app keeps running with the rest.

Open it from the appkit launcher: choose "Video doorbell" on its home
screen.
"""

import events
import lvgl as lv
from devkit import ui
from multimer import sleep_ms, ticks_diff, ticks_ms

# Change these to match your setup.
DOOR = True  # True at the door, False inside
DOOR_NAME = "front-door"  # the door's name on the network
DOOR_ADDRESS = None  # or ("192.168.1.20", PORT) to skip the search
PORT = 47800
BUTTON_PIN = None  # a board's button GPIO, pressed when low; None for the window
PICTURES = None  # a folder of JPEG files to send in place of a camera
FPS = 10  # pictures a second, at most
SIZE = "VGA"  # a camera's picture size: "QVGA" is 320x240, "VGA" 640x480
QUALITY = 60  # 1 to 100; lower is smaller and quicker to send
RATE = 16000  # sound samples a second

FIND_MS = 3000  # how often, inside, to look for the door while it's not linked
REPORT_MS = 5000  # how often, inside, to say how the pictures are coming
TICK_MS = 10  # how often the control checks the button and the link


def main(scope):
    # Pictures and sound need medialink; without it there is nothing to run.
    try:
        import boarddev
        import medialink
        from audiodev import AudioFormat
    except ImportError as e:
        ui.missing(
            scope,
            "missing: medialink",
            "The video doorbell needs medialink, boarddev and audiodev: %s." % (e,),
        )
        return

    scr = scope.root
    status = ui.status(scope)
    status.set_text("door" if DOOR else "inside")

    body = ui.label(scr, "", ui.big, ui.WHITE)
    body.set_width(scope.size[0] - 64)
    body.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    body.align(lv.ALIGN.TOP_MID, 0, 80)
    stats = ui.label(scr, "", ui.font, ui.MUTED)
    stats.align(lv.ALIGN.BOTTOM_MID, 0, -16)
    # Inside, the door's pictures go here.
    picture = lv.image(scr)
    picture.align(lv.ALIGN.CENTER, 0, 30)

    s = {
        "held": False,  # the window's button, while a key or mouse button is down
        "refused": False,
        "floor": None,
        "looked": ticks_ms(),
        "taken": ticks_ms(),
        "reported": ticks_ms(),
        "finding": False,
        "bad": 0,
        "keep": {},
    }

    def say(text):
        body.set_text(text)
        print(text)

    # The door's camera. Without one the door can't send pictures, and says so.
    camera = None
    if DOOR:
        try:
            if PICTURES:
                camera = medialink.FileCamera(PICTURES)
            else:
                import board_peripherals
                import cameraif

                # Have the chip scale each picture down and encode it, so it is
                # quick to send and the other side decodes it in hardware.
                camera = board_peripherals.camera()
                camera.reconfigure(pixel_format=cameraif.PixelFormat.JPEG, frame_size=getattr(cameraif.FrameSize, SIZE))
                camera.quality = QUALITY
        except Exception as e:
            say("No camera: %s. The door can't send pictures." % (e,))

    # The link, its video, and the sound both ways.
    link = video = intercom = finder = None
    mic = speaker = None
    try:
        link = medialink.Link(medialink.UDPTransport(PORT), retries=2)
        video = medialink.Video(link)
    except Exception as e:
        link = video = None
        say("No network for the link: %s" % (e,))

    audio = AudioFormat(RATE, 1, 16)
    try:
        mic = boarddev.pcm_in(audio)
        speaker = boarddev.pcm_out(audio, latency="low")
        if link is not None:
            intercom = medialink.Intercom(link, mic, speaker)
    except Exception as e:
        for dev in (mic, speaker):
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
        mic = speaker = intercom = None
        say("No microphone or speaker: %s. Pictures only." % (e,))

    try:
        finder = medialink.MDNS()
    except Exception as e:
        say("No name search on this network: %s" % (e,))

    if link is not None and DOOR and camera is not None and finder is not None:
        finder.advertise(DOOR_NAME, PORT)
        say("This is %r" % DOOR_NAME)
    elif not DOOR and link is not None and finder is not None:
        say("Looking for %r" % DOOR_NAME)


    def close():
        if intercom is not None:
            intercom.close()
        if link is not None:
            link.close()
        if camera is not None:
            camera.deinit()

    scope.on_close(close)
    if finder is not None:
        scope.on_close(finder.deinit)

    # The button is a pin on a board, or a key or mouse button in the window.
    pin = None
    if BUTTON_PIN is not None:
        from machine import Pin

        pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

    def on_down(event):
        s["held"] = True

    def on_up(event):
        s["held"] = False

    if pin is None:
        scope.on([events.KEYDOWN, events.MOUSEBUTTONDOWN], on_down)
        scope.on([events.KEYUP, events.MOUSEBUTTONUP], on_up)

    def held():
        return (not pin.value()) if pin is not None else s["held"]

    def connect(address):
        try:
            link.connect(address)
            say("Watching the door at %s" % (address,))
        except medialink.PeerUnreachable:
            pass

    def found(value, error):
        s["finding"] = False
        if error is not None:
            print("door search failed: %s" % (error,))
            return
        for _name, address in value or ():
            connect(address)

    def show(jpeg):
        try:
            px, w, h = ui.decode_jpeg(jpeg, scope.size[0] - 32, scope.size[1] - 120)
            ui.rgb565_image(picture, px, w, h, s["keep"])
        except Exception as e:
            s["bad"] += 1
            print("picture not shown: %s" % (e,))

    def control(t):
        # Inside, call the door while it isn't there. Both sides start and end
        # talking with the button, and say when the other side is talking.
        if link is None:
            return
        now = ticks_ms()
        if not DOOR and not link.alive and ticks_diff(now, s["looked"]) > FIND_MS:
            s["looked"] = now
            if DOOR_ADDRESS:
                connect(DOOR_ADDRESS)
            elif not s["finding"]:
                s["finding"] = True
                scope.worker.submit(lambda: finder.find(DOOR_NAME, timeout=1), found, key="find")

        if intercom is not None:
            pressed = held()
            if pressed and not intercom.talking and link.alive and not s["refused"]:
                try:
                    s["refused"] = not intercom.press()
                    say("The other side is talking" if s["refused"] else "Talking...")
                except medialink.PeerUnreachable:
                    s["refused"] = True
                    say("No answer from the other side")
            elif not pressed:
                s["refused"] = False
                if intercom.talking:
                    intercom.release()

        if link.floor != s["floor"]:
            s["floor"] = link.floor
            if link.floor == medialink.LISTENING:
                say("Someone at the door is talking" if not DOOR else "Inside is answering")

        # Inside, every few seconds, say how the pictures are coming.
        if not DOOR and video is not None and ticks_diff(now, s["reported"]) >= REPORT_MS:
            s["reported"] = now
            sound = intercom.stats["latency_ms"] if intercom is not None else "no"
            underruns = intercom.stats["underruns"] if intercom is not None else 0
            stats.set_text("%d pictures shown, %s ms late at most; sound %s ms late, %d underruns"
                           % (video.stats["received"], video.stats["max_latency_ms"], sound, underruns))
            video.stats["max_latency_ms"] = None

    def step():
        # The main loop calls this over and over: the sound, and the pictures
        # either way. A camera frame waits for the chip, so it can't be a timer.
        now = ticks_ms()
        if intercom is not None:
            intercom.service()
        if video is not None:
            if DOOR:
                if camera is not None and link.alive and video.ready and ticks_diff(now, s["taken"]) >= 1000 // FPS:
                    s["taken"] = now
                    jpeg = camera.take()
                    if jpeg is not None:
                        video.send(bytes(jpeg), now)
                video.service()
            else:
                frame = video.receive()
                if frame is not None:
                    show(frame.payload)
        if intercom is None or not intercom.talking:
            sleep_ms(1)

    scope.every(TICK_MS, control)
    scope.foreground(step)
