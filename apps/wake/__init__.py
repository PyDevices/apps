# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Wake word: listens for "Hey Jarvis" and flashes on each detection.

It listens on whatever microphone the device is set to, the one chosen
under Audio in, or the board's own microphones when nothing is chosen. A
USB mic chosen there is heard as soon as it's plugged in. The input is
asked for the model's own 16 kHz, mono; one without 16 kHz is taken at 48,
32 or 24 kHz and filtered down (``feed.py``). It needs firmware built with
``tflite`` and audiodsp's ``audiofeatures``, and omnipython's
``medialink``; a USB mic also needs ``usb-host-audio``.
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
FLASH_MS = 1500
TICK_MS = 20
READ_MS = 10  # audio per read
BUSY_MS = 12  # reading per tick, so a backlog can't hold the screen up

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


def _input_name(chosen):
    """What the status line calls the input in use."""
    for ep in chosen:
        return ep.label
    return "the built-in microphones"


def main(scope):
    global state
    try:
        import audiofeatures  # noqa: F401
        import tflite  # noqa: F401
        from medialink.wakeword import MicroWakeWord  # noqa: F401
    except ImportError as e:
        ui.missing(
            scope,
            "missing: tflite, audiofeatures or medialink",
            "Wake word needs firmware with tflite and audiofeatures, and the medialink package: %s." % (e,),
        )
        return
    scr = scope.root
    status = ui.status(scope)  # first: on a narrow screen it takes a row from scope.size
    status.set_text("starting")
    W, H = scope.size

    # The ring beside a column of text on a wide screen, above it on a tall
    # or square one, both centred in the app's area.
    wide = W * 3 >= H * 4
    if wide:
        d = max(80, min(260, H - 48, W * 2 // 5))
        col_w = min(340, W - d - 64)
    else:
        col_w = W - 24
        d = max(80, min(260, W - 48, H * 2 // 5))
    big = ui.big if col_w >= 300 else ui.font
    body = ui.plain(lv.obj(scr))
    body.set_size(W, H)
    body.set_flex_flow(lv.FLEX_FLOW.ROW if wide else lv.FLEX_FLOW.COLUMN)
    body.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    body.set_style_pad_column(40, 0)
    body.set_style_pad_row(16 if d >= 160 else 8, 0)

    ring = lv.obj(body)
    ring.set_size(d, d)
    ring.set_style_radius(d // 2, 0)
    ring.set_style_bg_color(ui.PANEL, 0)
    ring.set_style_border_color(ui.ACCENT, 0)
    ring.set_style_border_width(6 if d >= 160 else 4, 0)
    ring.remove_flag(lv.obj.FLAG.SCROLLABLE)
    icon = ui.label(ring, lv.SYMBOL.AUDIO, ui.huge if d >= 160 else ui.big, ui.ACCENT)
    icon.center()

    col = ui.plain(lv.obj(body))
    col.set_size(col_w, lv.SIZE_CONTENT)
    col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    col.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START if wide else lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.START)
    col.set_style_pad_row(12 if big is ui.big else 4, 0)
    align = lv.TEXT_ALIGN.LEFT if wide else lv.TEXT_ALIGN.CENTER

    def line(text, font, color):
        lbl = ui.label(col, text, font, color)
        lbl.set_width(col_w)
        lbl.set_style_text_align(align, 0)
        return lbl

    say = line('Say "%s"' % PHRASE, big, ui.WHITE)
    count = line("Detections: 0", big, ui.WHITE)
    last = line("", ui.font if big is ui.big else ui.small, ui.MUTED)
    bar = lv.bar(col)
    bar.set_size(col_w, 24 if big is ui.big else 12)
    bar.set_range(0, 100)
    line("model score", ui.small if big is ui.big else ui.tiny, ui.MUTED)

    st = state = {"mic": None, "feed": None, "ww": None, "buf": None, "hits": 0, "flash": None,
                  "t0": ticks_ms(), "best": 0.0, "chosen": [], "error": None}

    def close_mic():
        mic = st["mic"]
        st["mic"] = None
        if mic is not None:
            try:
                mic.close()
            except Exception as e:
                print("wake: mic close:", e)

    def close():
        close_mic()
        st["ww"] = None

    scope.on_close(close)

    def open_mic():
        # The input the device is set to: boarddev.pcm_in follows the
        # Audio in choice, and is the board's own microphones without one.
        import boarddev
        from audiodev import AudioFormat

        close_mic()
        name = _input_name(st["chosen"])
        try:
            mic, fd = feed.open_input(boarddev.pcm_in, lambda rate: AudioFormat(rate, 1, 16))
            mic.open()
        except Exception as e:  # noqa: BLE001 - say why on the screen, keep the app up
            status.set_text("can't listen on %s: %s" % (name, e))
            print("wake: input:", repr(e))
            return
        st["mic"], st["feed"] = mic, fd
        st["buf"] = bytearray(fd.rate // 1000 * READ_MS * 2)
        st["t0"] = ticks_ms()
        st["ww"].reset()
        status.set_text("listening on %s, %d kHz" % (name, fd.rate // 1000))
        print("wake: listening on %s, %d kHz" % (name, fd.rate // 1000))

    def moved(chosen):
        st["chosen"] = chosen
        if st["ww"] is not None:
            open_mic()

    def setup(t):
        # One step per tick, so the screen draws between them.
        t.deinit()
        status.set_text("loading the model")
        try:
            st["ww"] = _load_model()
        except Exception as e:
            status.set_text("no model: put %s in %s" % (MODEL, places.where_text(MODELS)))
            # Again under the ring, where it wraps: a narrow status line cuts it short.
            last.set_text("No model: put %s in %s." % (MODEL, places.where_text(MODELS)))
            print("wake: model:", e)
            return
        st["chosen"] = scope.follow("audio.in", moved)
        open_mic()
        scope.every(TICK_MS, listen)
        scope.every(250, show)

    def listen(t):
        mic, ww, fd, buf = st["mic"], st["ww"], st["feed"], st["buf"]
        if mic is None:
            return
        began = ticks_ms()
        while ticks_diff(ticks_ms(), began) < BUSY_MS:
            try:
                n = mic.readinto(buf)
            except OSError as e:  # a USB mic pulled out, a stalled codec
                status.set_text("%s stopped: %s" % (_input_name(st["chosen"]), e))
                print("wake: read:", e)
                close_mic()
                return
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

    scope.every(200, setup)
