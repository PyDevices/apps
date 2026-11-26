# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""A browser page's side of the seams: its camera and its object detector.

The picture is the camera the browser gives the page, the one chosen in
Home's Connections (``board_peripherals.camera()``, which is
``displaydev.page_camera.Camera`` in a browser). Zoom crops the centre of
its frame as a board crops its sensor's. There is no test card here: when
the camera won't open, `build` raises, and the app says why on screen.

Detection runs the page's ``espdl.YOLO11`` (YOLOX-nano, the 80 COCO
classes): the AI page's Pedestrian mode boxes the people it finds, and the
album's object overlay names everything it finds. The page has no face
model, so Face mode finds nothing and says so on the picture. A page with
no ``espdl`` says so too, and finds nothing.

The card, the recorder, interval sleep, the USB drive, the accelerometer and
the lights are the desktop's stand-ins (``hw.desktop``).
"""

try:
    import ppa
except ImportError:  # CPython: the page has ppa, scaling in software
    ppa = None

from . import Hardware
from .crop import preview_side
from .desktop import Accel, IntervalSleep, Lights, Recorder, Storage, UsbDisk
from .photo import Photo

OUT = 240
#: The short side of the frame the preview is cut from. A webcam's full
#: frame is only needed for a photo, and copying it out of the browser for
#: every preview frame would cost more than the preview shows.
PREVIEW_SHORT = 540
FRAME_MS = 200  # how long a preview frame may wait for the camera
PHOTO_MS = 1000

#: The page's note of where its ONNX model is, in a ``models`` folder.
MODEL = "yolo11n_coco.espdl"
SCORE = 0.25
PERSON = 0  # the COCO class of a person

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

NO_FACES = "No face model in a browser: Face mode finds nothing here. Pedestrian mode finds people."


class Preview:
    """The page's camera, cut square and scaled to 240x240.

    Zoom N shows the centre 1/N of the frame's square, as a board's preview
    does (`preview_side`). The browser's camera neither crops nor turns by a
    quarter, so each frame comes out of the browser whole, at most
    `PREVIEW_SHORT` pixels on its short side, and the PPA module cuts and
    turns it in software. Its RGB565 is little-endian, LVGL's byte order.
    """

    def __init__(self, camera):
        self.cam = camera  # displaydev.page_camera.Camera, or anything with its calls
        size = camera.size()
        self.w, self.h = size[0], size[1]
        k = min(1, PREVIEW_SHORT / min(self.w, self.h))
        self.pw, self.ph = int(self.w * k) & ~1, int(self.h * k) & ~1
        self.small = bytearray(self.pw * self.ph * 2)
        self.buf = bytearray(OUT * OUT * 2)
        self.rotation = 0
        self._shot = None

    def frame(self, magnify):
        """The next frame at this zoom, in `buf`; the last one when none came."""
        if self.cam.capture_scaled(self.small, self.pw, self.ph, timeout=FRAME_MS) is None:
            return self.buf
        side = preview_side(self.pw, self.ph, magnify)
        x0, y0 = (self.pw - side) // 2, (self.ph - side) // 2
        ppa.srm(self.small, self.pw, self.ph, self.buf, OUT, OUT, src_rect=(x0, y0, side, side), rotate=self.rotation)
        return self.buf

    def source(self):
        """The camera's whole frame, at its own size, for a photo."""
        if self._shot is None:
            self._shot = bytearray(self.w * self.h * 2)
        self.cam.capture_scaled(self._shot, self.w, self.h, timeout=PHOTO_MS)
        return self._shot, self.w, self.h

    def rotate(self, degrees):
        self.rotation = degrees % 360

    def close(self):
        """Let the camera go, so the browser stops showing it in use."""
        self.cam.close()


def _find_model():
    from appkit import places

    return places.find("models", MODEL)


class Detector:
    """The page's YOLOX-nano on a 240x240 picture.

    The model loads the first time something asks for boxes (the AI page,
    or the album's overlay) and `release` lets it go. `why` holds what the
    person should be told when a call found nothing because it can't: no
    face model, no ``espdl`` in the page, or a model that didn't load.

    Args:
        find: returns the path of the page's model note, or None.
    """

    def __init__(self, find=_find_model):
        self._find = find
        self._yolo = None  # None: not tried yet; False: tried, and it can't
        self.why = None

    def release(self):
        """Let the model go; the next call loads it again."""
        if self._yolo:
            try:
                self._yolo.deinit()
            except Exception as e:
                print("eyecam: detector didn't close:", e)
        self._yolo = None

    def _model(self):
        if self._yolo is None:
            self._yolo = False
            try:
                import espdl
                import image
            except ImportError:
                self.why = "No object detection: this page has no espdl module"
                print("eyecam: " + self.why)
                return False
            path = self._find()
            if path is None:
                self.why = "No object detection: this page has no models/%s" % MODEL
                print("eyecam: " + self.why)
                return False
            try:
                self._yolo = espdl.YOLO11(path, score=SCORE)
            except Exception as e:
                self.why = "The detector didn't load: %s" % (e,)
                print("eyecam: " + self.why)
                return False
            self._image = image.Image
            self._rgb565 = image.RGB565
            self.why = None
        return self._yolo

    def _found(self, buf, w, h):
        m = self._model()
        if not m:
            return []
        self.why = None
        return m.detect(self._image(w, h, self._rgb565, buffer=buf))

    def objects(self, buf, w, h):
        """Everything the model found, as ``(x0, y0, x1, y1, name, score)``."""
        out = []
        for x, y, bw, bh, score, cls in self._found(buf, w, h):
            name = COCO[cls] if 0 <= cls < len(COCO) else "class %d" % cls
            out.append((x, y, x + bw, y + bh, name, score))
        return out

    def people(self, buf, w, h):
        """The people the model found, as ``(x0, y0, x1, y1, None)``."""
        out = []
        for x, y, bw, bh, score, cls in self._found(buf, w, h):
            if cls == PERSON:
                out.append((x, y, x + bw, y + bh, None))
        return out

    def faces(self, buf, w, h):
        """Nothing: the page has no face model, and `why` says so."""
        self.why = NO_FACES
        return []


def _open_camera():
    import board_peripherals as bp

    return bp.camera()


def build(scope, open_camera=_open_camera):
    """The browser's seams. Raises the camera's error when it won't open."""
    preview = Preview(open_camera())
    scope.adopt(preview)
    storage = Storage(scope.data_dir)
    lights = Lights()
    detector = Detector()
    scope.on_close(detector.release)
    return Hardware(
        preview=preview,
        photo=Photo(preview, storage, lights),
        recorder=Recorder(preview, storage),
        sleep=IntervalSleep(scope),
        storage=storage,
        usb=UsbDisk(),
        accel=Accel(),
        lights=lights,
        detector=detector,
        desktop=True,
        browser=True,
    )
