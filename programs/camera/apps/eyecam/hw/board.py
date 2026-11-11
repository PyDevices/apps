# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""A board's side of the seams: the ESP32-P4X-EYE, and any other P4.

Everything comes through the board package: ``board_config.camera`` (cameraif,
the OV2710 on the Eye), ``sdcard``, ``led``, ``accelerometer``, ``pcm_in`` and
``sleep``. A board that lacks one steps down quietly: no camera of its own
means a USB camera, and then the test card; no accelerometer keeps the screen
upright; no microphone records without sound; no card slot leaves the album
saying there is no card; no sleep helper blanks the screen. The preview,
photos and video frames are cut
and scaled by the PPA from the camera's own frame buffer; photos go through
the hardware JPEG encoder, video through the H.264 encoder into an MP4 with
the microphone's sound; detection runs esp-dl's pedestrian and face models
from ``/pedestrian.espdl`` and ``/face.espdl``.
"""

import gc
import os
import time
import lvgl as lv
import uctypes

import machine
import ppa

from . import Hardware
from .crop import preview_side, video_crop
from .desktop import IntervalSleep as _BlankSleep
from .desktop import Storage as _FolderStorage
from .photo import SIZES, Photo
from .sources import open_source

SD = "/sd"
_here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
OUT = 240
FPS = 25
BITRATE = {"1080P": 6_000_000, "720P": 3_000_000, "480P": 1_500_000}
MODELS = {"people": "/pedestrian.espdl", "faces": "/face.espdl"}


def _aligned(n, align=64):
    """A writable view of *n* bytes on a cache-line boundary, for the PPA
    and the encoders, which write by DMA. Keep the first value alive."""
    raw = bytearray(n + align)
    off = (-uctypes.addressof(raw)) % align
    return raw, memoryview(raw)[off:off + n]


class Preview:
    """The camera, cut square and scaled to the screen by the PPA.

    Zoom N shows the centre 1/N of the frame's 960-pixel square (the
    factory's crop), turned by ``rotate()`` to undo a display rotation.
    The frame it was cut from stays borrowed in ``src`` until the next
    frame, for the recorder.
    """

    def __init__(self, camera):
        import _thread

        self.cam = camera  # a source (hw/sources.py): size(), frame(), deinit()
        self.w, self.h = camera.size()[0], camera.size()[1]
        self._raw, self.buf = _aligned(OUT * OUT * 2)
        self.rotation = 0
        self.src = None
        # While recording, the recorder's thread is the one caller of
        # cam.frame() (a borrowed frame is valid until the next call), and
        # the preview cuts its picture from that frame under this lock.
        self.lock = _thread.allocate_lock()
        self.external = False

    def frame(self, magnify):
        side = preview_side(self.w, self.h, magnify)
        x0, y0 = (self.w - side) // 2, (self.h - side) // 2
        if self.external:
            with self.lock:
                f = self.src
                if f is None:
                    return self.buf
                ppa.srm(f, self.w, self.h, self.buf, OUT, OUT, src_rect=(x0, y0, side, side), rotate=self.rotation, hardware=True)
            return self.buf
        f = self.cam.frame(timeout=200)
        if f is None:
            return self.buf  # keep the last picture up
        self.src = f
        ppa.srm(f, self.w, self.h, self.buf, OUT, OUT, src_rect=(x0, y0, side, side), rotate=self.rotation, hardware=True)
        return self.buf

    def source(self):
        """A fresh full frame for a photo (borrowed until the next frame)."""
        f = self.cam.frame(timeout=500)
        if f is not None:
            self.src = f
        return self.src, self.w, self.h

    def rotate(self, degrees):
        self.rotation = degrees % 360

    def close(self):
        self.src = None
        self.cam.deinit()


class Storage(_FolderStorage):
    """The card at /sd, in the factory's folders, watched for insertion."""

    def __init__(self, make_card, present=None):
        """*present* is the card-detect pin's reading. A board with no such
        pin passes None: the card is taken to be there and mounted at start,
        trying a few more times a poll apart if that fails."""
        self.root = SD
        self.full = False
        self.card_in = False
        self._make = make_card
        self._tries = 6 if present is None else 0
        self._present = present if present is not None else self._try
        self._fns = []
        self.bdev = None
        self._first_mount = []
        if self._present():
            self._mount()

    def _try(self):
        """Stand-in for the pin: a card is assumed to be there until a few
        mounts have failed (the first can come while the USB host or the
        camera is still starting)."""
        if self.card_in:
            return True
        if self._tries > 0:
            self._tries -= 1
            return True
        return False

    def _mount(self):
        try:
            self.bdev = self._make()
            os.mount(self.bdev, SD)
        except OSError as e:
            if e.args and e.args[0] == 1:  # EPERM: already mounted there
                pass
            else:
                print("eyecam: card not mounted:", e)
                self.bdev = None
                return False
        for d in (self.PICS, self.VIDS):
            try:
                os.mkdir("%s/%s" % (SD, d))
            except OSError:
                pass
        self.card_in = True
        for fn in self._first_mount:
            fn(self.bdev)
        self._first_mount = []
        return True

    def _unmount(self):
        try:
            os.umount(SD)
        except OSError:
            pass
        self.card_in = False

    def poll(self):
        """Mount or unmount to follow the card-detect pin; tells the
        ``on_change`` listeners when it changes."""
        present = self._present()
        if present == self.card_in:
            return
        if present:
            time.sleep_ms(50)  # let the contacts settle
            if not self._mount():
                return
        else:
            self._unmount()
        for fn in self._fns:
            fn(self.card_in)

    def on_change(self, fn):
        self._fns.append(fn)

    def on_first_mount(self, fn):
        """Call *fn(bdev)* once, when a card is first mounted (now, if one is)."""
        if self.card_in:
            fn(self.bdev)
        else:
            self._first_mount.append(fn)

    def mounted(self):
        return self.card_in

    def free(self):
        if not self.card_in:
            return 0
        st = os.statvfs(SD)
        return st[0] * st[3]

    def next_video(self):
        nums = self._numbers(self.VIDS, "mp4_", ".mp4")
        return "%s/%s/mp4_%d.mp4" % (self.root, self.VIDS, (max(nums) if nums else 0) + 1)


class Recorder:
    """H.264 video with the microphone's sound in an MP4, from the frame the
    preview just showed. One ``tick()`` per preview frame."""

    def __init__(self, preview, storage, make_mic, work):
        self.preview = preview
        self.storage = storage
        self._make_mic = make_mic
        self._work = work  # shared with Photo: a full frame's worth, 64-byte aligned
        self.recording = False
        self.frames = 0
        self.why = None  # what to tell the person when start() says no
        self._enc = None
        self._mp4 = None
        self._mic = None
        self._block_ms = 100
        self._scaled = None
        self._thread_done = True
        self._block = bytearray(32 * self._block_ms)  # 16 kHz mono: 32 bytes a millisecond

    def prepare(self, resolution):
        """Open the encoder for *resolution* now, while PSRAM is still in
        large pieces: a 1080P encoder needs 7 MB with 3 MB in one block, and
        an app that has run a while cannot find that. It stays open between
        recordings."""
        import h264enc

        if self._enc is not None and self.resolution == resolution:
            return
        if self._enc is not None:
            self._enc.close()
            self._enc = None
        self.resolution = resolution
        w, h = SIZES[resolution]
        h -= h % 16  # 1080 lines become 1072: the encoder wants multiples of 16
        self.size = (w, h)
        # 720P and 480P overlap the colour conversion with the encode; at
        # 1080P the pipeline needs more internal RAM than the board has left
        # beside the display's DMA ring, and the PPA conversion is the limit
        # there anyway (about 12 fps).
        try:
            self._enc = h264enc.Encoder(w, h, fps=FPS, gop=FPS, bitrate=BITRATE[resolution],
                                        out_size=1024 * 1024, pipeline=(h <= 720))
        except (ValueError, MemoryError) as e:
            print("eyecam: no %s video encoder: %s" % (resolution, e))
            self.why = "%s video needs more memory than this board has free: choose a smaller size" % resolution
        self._scaled = self._scaled_raw = None
        if self._enc is not None and (w != self.preview.w or h > self.preview.h):
            gc.collect()
            try:
                self._scaled_raw, self._scaled = _aligned(w * h * 2)
            except MemoryError:
                self._enc.close()
                self._enc = None
                print("eyecam: no room for a %s picture to encode" % resolution)
                self.why = "%s video needs more memory than this board has free: choose a smaller size" % resolution

    def start(self, magnify, resolution="1080P"):
        """Begin a recording. False when this board can't make one (no encoder,
        no ``mp4mux`` package), so the page doesn't claim it is recording."""
        try:
            import mp4mux
        except ImportError:
            print("eyecam: no mp4mux in /lib: no video (mip install mp4mux)")
            self.why = "No video: mp4mux isn't installed"
            return False
        self.why = None
        self.magnify = max(1, min(4, magnify))
        self.prepare(resolution)
        if self._enc is None:
            return False
        w, h = self.size
        self._frame = memoryview(self._work)[: w * h * 2]
        self._enc.force_idr()  # a new file starts on a keyframe with its SPS and PPS
        self._mp4 = mp4mux.Writer(self.storage.next_video(), w, h, fps_hint=FPS, audio_rate=16000)
        self._mic = None
        if self._make_mic is not None:
            try:
                self._mic = self._make_mic()
                self._mic.readinto(memoryview(self._block)[:64])  # capture starts on the first read
            except Exception as e:
                print("eyecam: recording without sound:", e)
                self._mic = None
        self._t0 = time.ticks_ms()
        self._pts = 0
        self._heard_ms = 0
        self.audio_bytes = 0
        self._last_tick = 0
        self.frames = 0
        self.stats = {"crop_us": 0, "encode_us": 0, "gap_ms": 0, "wait_us": 0, "ppa_us": 0, "mux_us": 0, "sound_us": 0}
        self.recording = True
        # Frames are taken and encoded on their own thread: the encoder and
        # the PPA let go of the interpreter while the hardware works, so the
        # preview and the UI carry on in the gaps. The sound is read there too.
        import _thread

        self._thread_done = False
        self.preview.external = True
        _thread.stack_size(16 * 1024)
        _thread.start_new_thread(self._loop, ())
        return True

    def _loop(self):
        cam = self.preview.cam
        w, h = self.size
        sw, sh = self.preview.w, self.preview.h
        lock = self.preview.lock
        try:
            while self.recording:
                t0 = time.ticks_us()
                with lock:  # not while the preview is cutting from the last frame
                    f = cam.frame(timeout=200)
                    if f is None:
                        continue
                    self.preview.src = f
                tw = time.ticks_us()
                if self._scaled is None:
                    # The sensor's own size: the frame less 4 rows top and bottom, no copy.
                    off = ((sh - h) // 2) * sw * 2
                    frame = memoryview(f)[off: off + w * h * 2]
                else:
                    # approx: 3x zoom is not a whole number of sixteenths; the PPA then fills a few pixels less.
                    # Under the lock: the PPA takes one operation at a time, and the preview's
                    # cut from another thread at the same moment is refused, not queued.
                    with lock:
                        ppa.srm(f, sw, sh, self._scaled, w, h, src_rect=self._crop(sw, sh), hardware=True, approx=True)
                    frame = self._scaled
                t1 = time.ticks_us()
                au = self._enc.encode(frame)
                t2 = time.ticks_us()
                st = self.stats
                st["wait_us"] += time.ticks_diff(tw, t0)
                st["ppa_us"] += time.ticks_diff(t1, tw)
                now = time.ticks_diff(time.ticks_ms(), self._t0)
                if now <= self._pts:
                    now = self._pts + 1  # two frames in one millisecond: the MP4 wants its times to climb
                st["crop_us"] += time.ticks_diff(t1, t0)
                st["encode_us"] += time.ticks_diff(t2, t1)
                if self._last_tick:
                    st["gap_ms"] += time.ticks_diff(now, self._last_tick)
                self._last_tick = now
                mp4 = self._mp4
                if mp4 is None:
                    break  # stop() gave up waiting and closed the file
                t3 = time.ticks_us()
                if au:
                    mp4.add_video(au, self._pts if self._enc.pipeline else now, self._enc.keyframe)
                    self.frames += 1
                self._pts = now
                t4 = time.ticks_us()
                self._sound(now)
                st["mux_us"] += time.ticks_diff(t4, t3)
                st["sound_us"] += time.ticks_diff(time.ticks_us(), t4)
        except Exception as e:
            print("eyecam: recording stopped:", e)
        self.preview.external = False
        self._thread_done = True

    def _sound(self, now):
        """Take the sound that has already been captured, never a block the
        microphone hasn't made yet: a read for sound that doesn't exist yet
        blocks, and a blocking read on a thread holds the interpreter too
        (measured: a 245 ms pause in the main loop; on a P4 Devkit and Panel
        the recording and the screen stopped altogether). A microphone that
        says how much it has queued is read for exactly that; one that
        doesn't is read a 100 ms block at a time, never ahead of the clock."""
        mic = self._mic
        queued = _queued_fn(mic)
        while self._mic is not None:
            mp4 = self._mp4
            if mp4 is None:
                break
            if queued is not None:
                n = min(queued(), len(self._block)) & ~1
                if n < 64:
                    break
                n = mic.readinto(memoryview(self._block)[:n])
            elif now - self._heard_ms >= 2 * self._block_ms:
                # Two blocks behind the clock, so the read finds its block
                # already captured and never waits on the recording thread.
                n = mic.readinto(self._block)
            else:
                break
            if not n:
                break
            mp4.add_audio(memoryview(self._block)[:n], self._heard_ms)
            self.audio_bytes += n
            self._heard_ms += n // 32  # 32 bytes a millisecond at 16 kHz mono

    def _crop(self, sw, sh):
        """The factory's cut for this zoom and size, in source pixels: see
        `video_crop`."""
        return video_crop(sw, sh, self.size[1], self.resolution, self.magnify)

    def tick(self, buf):
        pass  # the recording thread takes its own frames

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        for _ in range(400):  # the thread's last frame: a 200 ms frame wait, a 90 ms encode, and the GIL
            if self._thread_done:
                break
            time.sleep_ms(5)
        if self._enc is not None and self._mp4 is not None and self._enc.pipeline:
            last = self._enc.flush()
            if last:
                self._mp4.add_video(last, self._pts, self._enc.keyframe)
        if self._mp4 is not None:
            if self._mic is not None:
                self._sound(time.ticks_diff(time.ticks_ms(), self._t0))
            self._mp4.close()
            self._mp4 = None
        n = max(1, self.frames)
        st = self.stats
        print("eyecam: %d frames, %.1f fps; per frame wait %d ms, scale %d ms, encode %d ms, file %d ms, sound %d ms (%d bytes), between ticks %d ms"
              % (self.frames, n * 1000 / max(1, self._pts), st["wait_us"] // n // 1000, st["ppa_us"] // n // 1000,
                 st["encode_us"] // n // 1000, st["mux_us"] // n // 1000, st["sound_us"] // n // 1000, self.audio_bytes, st["gap_ms"] // n))
        if self._mic is not None:
            close = getattr(self._mic, "close", None)
            if close:
                close()
            self._mic = None
        self._frame = None


class IntervalSleep:
    """Deep sleep for N minutes; the buttons or the RTC timer wake the board,
    which boots into the app again."""

    sleeping = False

    def __init__(self, go_to_sleep, lights, preview):
        self._go = go_to_sleep
        self.lights = lights
        self.preview = preview

    def wake_reason(self):
        # wake_reason() outlives a soft reset (a tool taking the REPL after
        # the wake); reset_cause() does not.
        wr = machine.wake_reason()
        if not wr and machine.reset_cause() != machine.DEEPSLEEP_RESET:
            return None
        return "timer" if wr == machine.TIMER_WAKE else "button"

    def sleep(self, ms, on_wake):
        self.sleeping = True
        self.lights.backlight(False)
        try:
            self.preview.close()
        except Exception as e:
            print("eyecam: camera off before sleep:", e)
        self._go(ms, deep=True)

    def wake(self, reason):
        pass


class UsbDisk:
    """The card as a USB drive on the USB 2.0 port, from the first mount on,
    as the factory does. ``state`` follows the host: "connected" once it has
    configured the device, "instruction" when it is unplugged or resets."""

    def __init__(self):
        self.state = "instruction"
        self._fns = []
        self.msc = None

    def on_change(self, fn):
        self._fns.append(fn)

    def _set(self, state):
        if state == self.state:
            return
        self.state = state
        for fn in self._fns:
            fn(state)

    def attach(self, bdev):
        if self.msc is not None:
            return
        import usb.device
        from usb.device.msc import MSCInterface

        disk = self

        class _Drive(MSCInterface):
            def on_open(self):
                super().on_open()
                disk._set("connected")

            def on_reset(self):
                super().on_reset()
                disk._set("instruction")

        self.msc = _Drive(bdev)
        try:
            usb.device.get().init(
                self.msc,
                builtin_driver=False,
                manufacturer_str="Espressif",
                product_str="ESP32-P4X-EYE",
                id_vendor=0x303A,
                id_product=0x4002,
            )
        except Exception as e:  # a board whose USB port is a host's
            print("eyecam: card not offered as a USB disk:", e)


class Accel:
    """The QMA6100P read as a screen rotation, with the orientation helper's
    hysteresis (two agreeing readings before it changes)."""

    def __init__(self, sensor):
        from orientation import Orientation

        self.sensor = sensor
        self._o = Orientation()
        self.angle = 0

    def rotation(self):
        r = self._o.update(*self.sensor.acceleration)
        if r is not None:
            self.angle = r
        return self.angle


class _Still:
    def rotation(self):
        return 0


class Lights:
    def __init__(self, led, display):
        self.led = led
        self.display = display

    def flash(self, on):
        if self.led is not None:
            self.led.value(1 if on else 0)

    def backlight(self, on):
        if self.display is not None:
            self.display.brightness = 1.0 if on else 0.0


class Detector:
    """esp-dl's pedestrian and face detectors on the 240x240 preview."""

    def __init__(self, preload=False):
        self._models = {}
        self._img = None
        if preload:
            for kind in MODELS:
                self._model(kind)

    def release(self):
        """Drop the loaded models. Each takes 20 to 30 KB of internal RAM in
        small pieces, which fragments what the PPA and the encoder need, so
        the app loads them on the AI page and lets them go on leaving it."""
        for kind, m in self._models.items():
            if m:
                try:
                    m.deinit()
                except Exception:
                    pass
        self._models = {}
        self._img = None

    def _image(self, buf, w, h):
        import image

        if self._img is None or (self._img.width(), self._img.height()) != (w, h):
            self._img = image.Image(w, h, image.RGB565)
        self._img.bytearray()[:] = buf
        return self._img

    def _model(self, kind):
        m = self._models.get(kind)
        if m is None:
            try:
                import espdl
            except ImportError:
                self._models[kind] = False
                print("eyecam: no vision module in this firmware: no detection")
                return False
            path = MODELS[kind]
            try:
                os.stat(path)
            except OSError:
                self._models[kind] = False
                print("eyecam: no %s model at %s" % (kind, path))
                return False
            try:
                m = espdl.PedestrianDetect(path) if kind == "people" else espdl.ESPDet(path, score=0.5)
            except MemoryError as e:
                print("eyecam: %s model: %s" % (kind, e))
                self._models[kind] = False
                return False
            self._models[kind] = m
        return m

    def _boxes(self, kind, buf, w, h):
        m = self._model(kind)
        if not m:
            return []
        out = []
        for d in m.detect(self._image(buf, w, h)):
            x, y, bw, bh = d[0], d[1], d[2], d[3]
            pts = d[6] if len(d) > 6 and d[6] else None
            out.append((x, y, x + bw, y + bh, pts))
        return out

    def people(self, buf, w, h):
        return self._boxes("people", buf, w, h)

    def faces(self, buf, w, h):
        return self._boxes("faces", buf, w, h)

    def objects(self, buf, w, h):
        return []  # no COCO model in this build; the album shows no boxes


def _queued_fn(mic):
    """How many bytes the microphone has captured and not yet handed over,
    or None when it can't say: the pump's input says so in ``stats()``, and a
    plain I2S microphone (the Eye's) says nothing, so the clock decides."""
    stats = getattr(mic, "stats", None)
    if callable(stats):
        try:
            stats()["waiting"]
            return lambda: stats()["waiting"]
        except (KeyError, TypeError, OSError):
            pass
    return None  # not queued_size(): on most inputs that is the output side's, or reads 0


def _mic_16k(make):
    """The board's microphone opened as 16 kHz mono, which is what the MP4's
    sound track says it is. A board's own default can be another rate (the
    P4 boards' codecs open at 24 kHz, which would play 1.5 times too slow); one
    whose factory takes no format keeps its default."""

    def open_mic():
        try:
            from audiodev import AudioFormat

            return make(format=AudioFormat(rate=16000, channels=1, bits=16))
        except (ImportError, TypeError):
            return make()

    return open_mic


def _optional(bc, name):
    """A board_config peripheral, or None when the board hasn't got it (or
    can't make it)."""
    try:
        return getattr(bc, name, None)
    except Exception as e:
        print("eyecam: no %s: %s" % (name, e))
        return None


def _scaled(bc, scale, lock):
    """The 240x240 display that the PPA enlarges onto this board's panel."""
    from .scaled import ScaledDisplay

    def home():
        try:
            from touchkit import shell

            if shell.launcher is not None:
                shell.go(shell.launcher.home)
        except ImportError:
            pass  # not under a touch launcher: there is no Home to go to

    return ScaledDisplay(bc.display_drv, scale, lock, home)


def build(scope):
    import board_config as bc

    # board_config's peripherals are made on first use: bc.camera is the
    # Camera, bc.sdcard the card, bc.led the pin, bc.accelerometer the sensor.
    source = open_source(bc, _here + "/testcard.jpg")
    print("eyecam: picture from the %s source" % source.kind)
    preview = Preview(source)
    # One full frame of scratch for photos and video frames, made once: a
    # 4 MB buffer per photo would grow the Python heap into the PSRAM the
    # encoder and the models need. The factory's largest picture is 1920x1080,
    # whatever the camera sends.
    work_raw, work = _aligned(max(preview.w * preview.h, SIZES["1080P"][0] * SIZES["1080P"][1]) * 2)
    if hasattr(bc, "sdcard"):
        storage = Storage(lambda: bc.sdcard, bc.sdcard_present if hasattr(bc, "sdcard_present") else None)
    else:
        storage = Storage(lambda: None, lambda: False)
    lights = Lights(_optional(bc, "led"), _optional(bc, "display_drv"))
    usb = UsbDisk()
    storage.on_first_mount(usb.attach)
    scope.every(500, lambda t: storage.poll())
    accel = _Still()
    if _optional(bc, "accelerometer") is not None:
        try:
            accel = Accel(bc.accelerometer)
        except (OSError, ImportError) as e:
            print("eyecam: no accelerometer:", e)
    mic = _optional(bc, "pcm_in")
    if mic is not None:
        mic = _mic_16k(mic)
    if mic is None:
        print("eyecam: no microphone: video has no sound")
    recorder = Recorder(preview, storage, mic, work)
    recorder.prepare("1080P")  # the setting's default; control re-prepares on change

    def turn_screen(degrees):
        """Turn the panel itself (the ST7789's MADCTL, through displaydev):
        the UI and the preview turn with it, so both stay upright when the
        board is turned. LVGL's own rotation leaves a square panel through
        our flush path untouched."""
        turn = (360 - degrees) % 360  # the panel turns the other way from the sensor's sectors
        drv = bc.display_drv
        # The 240x240 glass sits on a 240x320 controller: turned so that the
        # addressing runs bottom-to-top, the window has to start 80 rows in,
        # or the picture lands off the glass.
        col, row = {0: (0, 0), 90: (0, 0), 180: (0, 80), 270: (0, 80)}[turn]
        for name, v in (("colstart", col), ("rowstart", row)):
            try:
                setattr(drv, name, v)
            except AttributeError:
                setattr(drv, "_" + name, v)
        drv.rotation = turn
        lv.screen_active().invalidate()  # the panel's init cleared it
        return turn

    sleep_fn = _optional(bc, "sleep")
    sleep = IntervalSleep(sleep_fn, lights, preview) if sleep_fn else _BlankSleep(scope, 60000)
    parts = dict(
        scaled=lambda scale: _scaled(bc, scale, preview.lock),
        preview=preview,
        photo=Photo(preview, storage, lights, work),
        recorder=recorder,
        work=work_raw,
        sleep=sleep,
        storage=storage,
        usb=usb,
        accel=accel,
        lights=lights,
        detector=Detector(),
        desktop=False,
    )
    if accel.__class__ is Accel:
        parts["turn_screen"] = turn_screen  # the Eye's panel is the one that needs this
    return Hardware(**parts)
