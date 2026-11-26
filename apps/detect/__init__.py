# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Object detection: the camera through YOLO11n, boxes drawn on the preview.

The model is Espressif's YOLO11n for ESP-DL, trained on COCO: its 80 classes
are everyday things (people, cups, bottles, chairs, phones, cats, cars). It
looks at a 160 x 160 copy of each frame, so a thing that fills a fair part of
the picture is found and a small one far away isn't.

Each loop takes a preview-sized frame into a buffer of its own, runs the
detector on it, draws the boxes into it and copies it to the panel's
framebuffer, or on a panel with none redraws the LVGL image that shows it
(`touchkit.cam.Preview`); the list on the right names what was found,
in the colour of its box. On a narrow screen the list is under the picture.
Flip, mirror, light and brightness are the Camera app's.

It needs a firmware with the ``espdl`` and ``image`` modules, and the model
file, ``yolo11n_coco.espdl``, in a ``models`` folder: ``/sd/models`` on the SD
card (mounted while the app is open), ``/models`` on flash or
``/data/models``, looked at in that order (`appkit.places`). It checks for
all three, and for the camera, when it opens, and says what's missing.
Where to download the model: https://github.com/PyDevices/apps/blob/main/docs/reference/models.md

In a browser the page brings its own model, YOLOX-nano, and fetches it the
first time the app opens, so its boxes can differ a little from a board's.
The status line names the model that runs.
"""

import lvgl as lv
from multimer import ticks_diff, ticks_ms

from appkit import places
from touchkit import cam, ui

MODEL = "yolo11n_coco.espdl"
MODELS = "models"  # the folder name, on the card, flash and the data root
PREVIEW = 520
WIDE = 640  # the narrowest app area with the list beside the picture
SCORE = 0.15  # two clear bottles in a dim room scored 0.27 and 0.18
LISTED = 8

COCO = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
)  # fmt: skip

# A colour per class, from a short wheel: the box on the picture and its line
# in the list share it.
WHEEL = (0xFF5A5A, 0x5AD15A, 0x5A9BFF, 0xFFD24A, 0xD25AFF, 0x4AE0E0, 0xFF9A3C, 0xB4FF5A)

state = None  # the open app's state, for the console


def _rgb565(rgb):
    return ((rgb >> 8) & 0xF800) | ((rgb >> 5) & 0x07E0) | ((rgb >> 3) & 0x001F)


def _model(scope):
    places.hold_card(scope)
    return places.find(MODELS, MODEL)


def main(scope):
    global state
    root = scope.root
    status = ui.status(scope)
    W, H = scope.size
    RX, RY = scope.rect[:2]
    st = state = {"cam": None, "det": None, "found": [], "ms": 0, "frames": 0, "t0": ticks_ms()}

    def missing(text):
        ui.missing(scope, text.split(":")[0], text)

    try:
        import espdl
        import image
        from pygraphics import RGB565, FrameBuffer
    except ImportError as e:
        missing("No vision modules: %s. Object detection needs the board's espdl, image and pygraphics modules." % (e,))
        return
    path = _model(scope)
    if path is None:
        missing("No model: put %s in %s." % (MODEL, places.where_text(MODELS)))
        return
    opts = cam.options(scope)
    try:
        c0 = cam.open_camera(opts)
    except Exception as e:
        missing(cam.no_camera_text(e, "Object detection"))
        return

    st["cam"] = c0
    try:
        det = espdl.YOLO11(path, score=SCORE)
    except Exception as e:
        c0.deinit()
        st["cam"] = None
        missing("The model didn't load: %s" % (e,))
        return
    st["det"] = det
    cam.apply_controls(c0, opts)

    wide = W >= WIDE
    if wide:
        pw, ph = cam.preview_size(c0, PREVIEW)
        x0, y0 = 24, 8
    else:
        # Under the row the Home button and the status line share.
        pw, ph = cam.preview_size(c0, W - 8)
        x0, y0 = (W - pw) // 2, ui.small.line_height + 14
    c0 = None
    pv = cam.Preview(root, x0, y0, pw, ph, (RX, RY), own=True)
    buf = pv.buf
    canvas = FrameBuffer(buf, pw, ph, RGB565)
    img = image.Image(pw, ph, image.RGB565, buffer=buf)
    if pv.fb is not None:
        from board_config import display_drv as d

        panel = FrameBuffer(pv.fb, d.width, d.height, RGB565)

        def show():
            # The finished frame onto the panel. Not row by row through memoryview
            # slices: into a buffer this big, that took 7 s a frame on an ESP32-P4.
            panel.blit(canvas, pv.x, pv.y)
            d.flush_rect(pv.x, pv.y, pw, ph)
    else:
        show = pv.show  # the image redraws from the buffer

    if wide:
        rx, ry, rw, font, step = x0 + pw + 24, 64, W - x0 - pw - 48, ui.font, 34
        title = ui.label(root, lv.SYMBOL.GPS + "  Seeing", ui.big, ui.ACCENT)
        title.set_pos(rx, 12)
        listed = LISTED
    else:
        # Under the picture: as many rows as fit, and the speed line.
        rx, ry, rw, font = x0, y0 + ph + 4, pw, ui.small
        step = font.line_height + 2
        listed = max(1, min(LISTED, (H - ry - step) // step))
    rows = []
    for i in range(listed):
        r = ui.label(root, "", font, ui.WHITE)
        r.set_pos(rx, ry + i * step)
        r.set_width(rw)
        r.set_long_mode(lv.label.LONG_MODE.CLIP)
        rows.append(r)
    note = ui.label(root, "", ui.small, ui.MUTED)
    note.set_pos(rx, ry + listed * step + (8 if wide else 0))
    speed = "%.1f frames a second, %d ms to look at each" if wide else "%.1f fps, %d ms a look"
    note.set_width(rw)

    def loop():
        c = st["cam"]
        if c is None:
            return
        if not pv.capture(c):
            return
        t = ticks_ms()
        found = st["det"].detect(img)
        st["ms"] = ticks_diff(ticks_ms(), t)
        for x, y, w, h, score, cat in found:
            col = _rgb565(WHEEL[cat % len(WHEEL)])
            canvas.rect(x, y, w, h, col)
            canvas.rect(x + 1, y + 1, w - 2, h - 2, col)
            canvas.rect(x + 2, y + 2, w - 4, h - 4, col)
        st["found"] = found
        st["frames"] += 1
        show()

    def tick(t=None):
        found = sorted(st["found"], key=lambda f: -f[4])
        for i, r in enumerate(rows):
            if i < len(found):
                cat, score = found[i][5], found[i][4]
                name = COCO[cat] if cat < len(COCO) else "class %d" % cat
                r.set_text("%s  %d%%" % (name, int(score * 100 + 0.5)))
                r.set_style_text_color(lv.color_hex(WHEEL[cat % len(WHEEL)]), 0)
            else:
                r.set_text("")
        if not found:
            rows[0].set_text("nothing I know")
            rows[0].set_style_text_color(ui.MUTED, 0)
        dt = ticks_diff(ticks_ms(), st["t0"]) or 1
        note.set_text(speed % (st["frames"] * 1000 / dt, st["ms"]))
        st["frames"] = 0
        st["t0"] = ticks_ms()

    def close():
        c, st["cam"] = st["cam"], None
        if c is not None:
            c.deinit()
        dd, st["det"] = st["det"], None
        if dd is not None:
            dd.deinit()

    scope.on_close(close)
    scope.every(500, tick)
    status.set_text("%s, 80 COCO classes" % getattr(det, "model", "YOLO11n"))
    scope.foreground(loop)
