# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Wake word: listens on a USB microphone for "Hey Jarvis" and flashes on
each detection.

The mic is asked for the model's own 16 kHz, mono (a stereo-only mic, like
a webcam's, is downmixed as the packets land); one without 16 kHz is
taken at 48, 32 or 24 kHz and filtered down (``feed.py``). The host starts
at high speed, which reaches a webcam's mic behind the board's hub, and
if no mic turns up it starts again at full speed, which is how a
full-speed mic behind the hub is reached. It needs pydevices' ``usb-core``,
``usb-host-audio`` and ``medialink``, and firmware built with ``tflite`` and
audiodsp's ``audiofeatures``.
The model, ``hey_jarvis.json``, loads from a ``models`` folder: the SD card's
``/sd/models``, then ``/models`` on flash, then ``/data/models``
(`appkit.places`). The card is mounted read-only and unmounted again at
once: the model is read in before that. ``hey_jarvis.json`` and
``hey_jarvis.tflite`` are downloaded from ESPHome's micro-wake-word-models; the
links are at https://github.com/PyDevices/apps/blob/main/docs/reference/models.md
"""

import lvgl as lv
from multimer import ticks_diff, ticks_ms
from appkit import places
from touchkit import ui

from . import feed

MODEL = "hey_jarvis.json"
MODELS = "models"  # the folder name, on the card, flash and the data root
PHRASE = "Hey Jarvis"
READ = 960  # bytes per read: 30 ms at 16 kHz, 10 ms at 48 kHz
HIGH_SPEED_MS = 8000  # then full speed, for a full-speed mic behind the hub
NO_MIC_MS = 15000
FLASH_MS = 1500
TICK_MS = 20
MAX_BLOCKS = 12  # per tick, so a backlog can't hold the screen up

state = None  # for the console


def _load_model():
    """The detector. OSError when no ``models`` folder has the model."""
    from medialink.wakeword import MicroWakeWord

    card = places.mount_card()
    try:
        path = places.find(MODELS, MODEL)
        if path is None:
            raise OSError("%s is in none of %s" % (MODEL, places.where_text(MODELS)))
        return MicroWakeWord(path)
    finally:
        places.unmount_card(card)


def main(scope):
    global state
    try:
        import audiofeatures  # noqa: F401
        import tflite  # noqa: F401
        import usb.core
        from medialink.wakeword import MicroWakeWord  # noqa: F401
        from usb.host.audio import Microphone  # noqa: F401

        usb.core.start  # PyUSB on a desktop has no host to start
    except (ImportError, AttributeError) as e:
        ui.missing(
            scope,
            "missing: tflite, audiofeatures, medialink or usb host",
            "Wake word needs firmware with tflite and audiofeatures, the medialink package, and the "
            "board's USB host with usb-host-audio, for a USB microphone: %s." % (e,),
        )
        return
    scr = scope.root
    status = ui.status(scope)
    status.set_text("starting")

    ring = lv.obj(scr)
    ring.set_size(260, 260)
    ring.align(lv.ALIGN.CENTER, -170, -2)
    ring.set_style_radius(130, 0)
    ring.set_style_bg_color(ui.PANEL, 0)
    ring.set_style_border_color(ui.ACCENT, 0)
    ring.set_style_border_width(6, 0)
    ring.remove_flag(lv.obj.FLAG.SCROLLABLE)
    icon = ui.label(ring, lv.SYMBOL.AUDIO, ui.huge, ui.ACCENT)
    icon.center()
    say = ui.label(scr, 'Say "%s"' % PHRASE, ui.big, ui.WHITE)
    say.set_pos(420, 70)
    count = ui.label(scr, "Detections: 0", ui.big, ui.WHITE)
    count.set_pos(420, 130)
    last = ui.label(scr, "", ui.font, ui.MUTED)
    last.set_pos(420, 180)
    bar = lv.bar(scr)
    bar.set_size(340, 24)
    bar.set_pos(420, 240)
    bar.set_range(0, 100)
    ui.label(scr, "model score", ui.small, ui.MUTED).set_pos(420, 270)

    st = state = {"host": None, "mic": None, "feed": None, "ww": None, "hits": 0, "flash": None,
                  "t0": ticks_ms(), "best": 0.0, "dev": None, "since": ticks_ms()}

    def close():
        if st["mic"] is not None:
            try:
                st["mic"].stop()
            except Exception as e:
                print("wake: mic stop:", e)
            st["mic"] = None
        if st["host"]:
            import usb.core

            usb.core.stop()
            st["host"] = None
        st["ww"] = None

    scope.on_close(close)

    buf = bytearray(READ)

    def setup(t):
        # One step per tick, so the screen draws between them.
        import usb.core
        from usb.host.audio import Microphone

        if st["ww"] is None:
            status.set_text("loading the model")
            try:
                st["ww"] = _load_model()
            except Exception as e:
                status.set_text("no model: put %s in %s" % (MODEL, places.where_text(MODELS)))
                print("wake: model:", e)
                t.deinit()
            return
        if not st["host"]:
            status.set_text("looking for the USB mic")
            try:
                usb.core.start(classes=("uac",))
                st["host"] = "high"
            except OSError as e:
                if e.errno != 95:  # EOPNOTSUPP: an earlier app ran the host at full speed
                    raise
                usb.core.start(full_speed=True, classes=("uac",))  # the hub can't restart at high speed
                st["host"] = "full"
            st["since"] = ticks_ms()
            return
        if st["mic"] is None:
            st["dev"] = usb.core.find(custom_match=Microphone.match)
            if st["dev"] is None:
                waited = ticks_diff(ticks_ms(), st["since"])
                if st["host"] == "high" and waited > HIGH_SPEED_MS:
                    # A full-speed mic behind the hub isn't reachable from a
                    # high-speed host; at full speed the hub passes it through.
                    status.set_text("looking for the USB mic at full speed")
                    usb.core.stop()
                    usb.core.start(full_speed=True, classes=("uac",))
                    st["host"] = "full"
                    st["since"] = ticks_ms()
                elif st["host"] == "full" and waited > NO_MIC_MS:
                    status.set_text("no USB microphone: plug one into the hub")
                return
            try:
                mic, fd = feed.open_mic(Microphone, st["dev"])
            except feed.Unsupported as e:
                status.set_text(str(e))
                print("wake:", e)
                st["dev"] = None
                setup_timer.deinit()
                return
            mic.start()
            st["mic"], st["feed"] = mic, fd
            st["t0"] = ticks_ms()
            how = "%d kHz%s" % (mic.rate // 1000, ", stereo mixed to mono" if mic.downmix else "")
            status.set_text("listening on the USB mic, " + how)
            print("wake: listening, %s, %s-speed host" % (how, st["host"]))
            setup_timer.deinit()
            scope.every(TICK_MS, listen)
            scope.every(250, show)

    def listen(t):
        mic, ww, fd = st["mic"], st["ww"], st["feed"]
        for _ in range(MAX_BLOCKS):
            n = mic.read(buf)
            if not n:
                return
            for pcm in fd.push(memoryview(buf)[:n]):
                if ww.feed(pcm, feed.MODEL_RATE, 1):
                    hit()
                if ww.probability > st["best"]:
                    st["best"] = ww.probability

    def hit():
        st["hits"] += 1
        st["flash"] = ticks_ms()
        secs = ticks_diff(ticks_ms(), st["t0"]) // 1000
        print("wake: %s (#%d at %d s)" % (PHRASE, st["hits"], secs))
        count.set_text("Detections: %d" % st["hits"])
        last.set_text("last at %d:%02d after it started listening" % (secs // 60, secs % 60))
        ring.set_style_bg_color(ui.GOOD, 0)
        ring.set_style_border_color(ui.WHITE, 0)
        icon.set_text(lv.SYMBOL.OK)
        icon.set_style_text_color(ui.WHITE, 0)
        say.set_text("%s!" % PHRASE)

    def show(t):
        bar.set_value(int(st["best"] * 100), 0)
        st["best"] = 0.0
        f = st["flash"]
        if f is not None and ticks_diff(ticks_ms(), f) > FLASH_MS:
            st["flash"] = None
            ring.set_style_bg_color(ui.PANEL, 0)
            ring.set_style_border_color(ui.ACCENT, 0)
            icon.set_text(lv.SYMBOL.AUDIO)
            icon.set_style_text_color(ui.ACCENT, 0)
            say.set_text('Say "%s"' % PHRASE)

    setup_timer = scope.every(200, setup)
