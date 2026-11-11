# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""What every button does on every page: a port of the factory's
``ui_extra.c`` (pages, popups, timers) and ``app_control.c`` (which button
calls what, and the knob).

Method names follow the factory's (``btn_up``, ``btn_menu``, ...) so the two
can be read side by side. Quirks are kept on purpose; each is marked.
"""

import framebuf
import time

import lvgl as lv

from . import controls, layout
from .camera_screen import CameraScreen
from .knob import Knob
from .other_screens import AlbumScreen, UsbScreen
from .settings import RESOLUTIONS
from .widgets import focus, hide, show, visible
from .wheel import NAMES

MAIN, CAMERA, INTERVAL, VIDEO, AI, ALBUM, USB, SETTINGS = (
    "MAIN", "CAMERA", "INTERVAL CAM", "VIDEO MODE", "AI DETECT", "ALBUM", "USB DISK", "SETTINGS")
CAMERA_PAGES = (CAMERA, INTERVAL, VIDEO, AI)

POPUP_MS = 5000
INTERVAL_START_MS = 7000
INTERVAL_END_MS = 5000
PROMPT_MS = 3000
USB_WARNING_MS = 5000
INTERVAL_STEP, INTERVAL_MIN, INTERVAL_MAX = 5, 5, 120
MAG_MIN, MAG_MAX = 1, 4
MIN_FREE_PHOTO = 5 * 1024 * 1024
MIN_FREE_VIDEO = 100 * 1024 * 1024

# Settings rows: (settings key, options in the factory's order)
OPTIONS = (
    ("gyroscope", ("Off", "On")),
    ("od", ("Off", "On")),
    ("resolution", RESOLUTIONS),
    ("flash", ("Off", "On")),
)
CAMERA_KEYS = ("contrast", "saturation", "brightness", "hue")

FRAME_MS = 50  # the frame timer's period when the display's refresh can't pace the frames
PACE_BY_REFRESH = True  # cut each frame as LVGL starts a refresh, so one clock paces both
# After a refresh longer than its period, the LVGL loop rests for as long as
# the refresh took (up to its cap), leaving the thread to everything else. A
# 25 ms refresh then comes every 50 ms. With nothing else to run, the preview
# wants the cap low; a recording wants the encoder's thread to get its share.
IDLE_REST_MS = 10
ROTATE_POLL_MS = 300


class Timer:
    """A one-shot that can be fired early, like ``lv_timer_ready``."""

    def __init__(self, scope, ms, fn):
        self.fn = fn
        self.t = scope.after(ms, lambda t: self.fire())

    def fire(self):
        if self.fn is not None:
            fn, self.fn = self.fn, None
            self.t.deinit()
            fn()

    def cancel(self):
        self.fn = None
        self.t.deinit()


class Eye:
    def __init__(self, scope, settings, hw, touch=False):
        self.scope = scope
        self.s = settings
        self.hw = hw
        self.page = MAIN
        self.mag = max(MAG_MIN, min(MAG_MAX, settings.magnify))
        self.interval = settings.int_time
        self.ai_mode = "pedestrian"
        self.cam_panel = False
        self.item = 0
        self.cam_item = 0
        self.recording = False
        self.rec_secs = 0
        self.usb_mounted = False
        self.sd_mounted = hw.storage.mounted()
        self.options = [getattr(settings, key) for key, _ in OPTIONS]
        self.camera_vals = [getattr(settings, key) for key in CAMERA_KEYS]
        self.knob = Knob()
        self.rotation = 0
        self.frame_stats = self._fresh_stats()
        self.popup_timer = None
        self.photo_timer = None  # the factory's lv_additional_photo_timer
        self.prompt_timer = None
        self.usb_timer = None
        self.video_timer = None
        self.events = []  # (what, detail): photos, recordings, sleeps; read by tests

        # A board draws at 240x240 on a display of its own and lets the PPA
        # enlarge it: LVGL transforming each frame in software takes 250 ms
        # at 2x. Make it first, so the screens below are made on it.
        self.scaled = None
        main = lv.display_get_default()
        width, height = main.get_horizontal_resolution(), main.get_vertical_resolution()
        factor = layout.scale_for(width, height)
        if factor > 1 and getattr(hw, "scaled", None) is not None:
            self.scaled = hw.scaled(factor)
        self.cam_scr = scope.screen()
        self.album_scr = scope.screen(load=False)
        self.usb_scr = scope.screen(load=False)
        disp = lv.display_get_default()
        width, height = disp.get_horizontal_resolution(), disp.get_vertical_resolution()
        boxes = [layout.stage(s, width, height) for s in (self.cam_scr, self.album_scr, self.usb_scr)]
        self.scale = boxes[0][1]
        self.cam = CameraScreen(boxes[0][0], hw.preview.frame(self.mag))
        self.album = AlbumScreen(boxes[1][0], hw.storage, hw.detector)
        self.usb = UsbScreen(boxes[2][0])
        self.touch = [controls.TouchControls(box, self, scale) for box, scale in boxes] if touch else []
        self.cam.wheel.on_main = lambda: self.page == MAIN
        self.fb = framebuf.FrameBuffer(hw.preview.buf, 240, 240, framebuf.RGB565)
        g = lv.group_get_default()
        if g is not None:
            g.remove_all_objs()  # the factory drives focus itself; no LVGL key group

        self.cam.factor.set_text("%dX" % self.mag)
        self.cam.interval_time.set_text("%dmin" % self.interval)
        self.init_settings_display()
        self.apply_settings()
        hw.usb.on_change(self.set_usb_disk_mounted)
        if hasattr(hw.storage, "on_change"):
            hw.storage.on_change(self.set_sd_card_mounted)
        self._refr_cb = None
        self._first_frame_seen = False
        self._lvgl_rest(IDLE_REST_MS)
        if PACE_BY_REFRESH and hasattr(lv.EVENT, "REFR_START") and disp is not None:
            # LVGL sends REFR_START before it gathers the dirty areas, so a
            # frame cut and invalidated here is rendered in the same cycle.
            self._refr_cb = lambda e: self._frame(None)
            self._refr_done = lambda e: self._refresh_done()
            self._refr_disp = disp
            disp.add_event_cb(self._refr_cb, lv.EVENT.REFR_START, None)
            disp.add_event_cb(self._refr_done, lv.EVENT.REFR_READY, None)
        else:
            scope.every(FRAME_MS, self._frame)
        scope.every(ROTATE_POLL_MS, self._rotate_poll)

        self.goto_page(MAIN)
        self.boot(hw.sleep.wake_reason())

    # -- boot, as app_storage_init ----------------------------------------

    def boot(self, reason):
        if reason != "timer":
            if self.s.int_active:
                self.goto_page(INTERVAL)
                self.clear_page()
                self.popup_interval_timer_warning()
            self.stop_interval_photo()
            self.s.set("photo_count", 0)
        elif self.s.int_active:
            self.goto_page(INTERVAL)
            self.clear_page()
            self.start_interval_photo(self.s.int_time)

    def start_interval_photo(self, minutes):
        self.s.set("int_active", 1)
        self.s.set("wake_time", minutes * 60)
        self.take_photo()
        self.s.set("photo_count", self.s.photo_count + 1)
        if self.s.int_active:
            self.events.append(("sleep", minutes))
            self.hw.sleep.sleep(minutes * 60000, self._woke)

    def stop_interval_photo(self):
        self.s.set("int_active", 0)
        self.s.set("wake_time", 0)

    def _woke(self, reason):
        """The board boots again after deep sleep; on a desktop the app
        carries on, so put it back where a fresh boot would."""
        self._cancel_timers()
        self.goto_page(MAIN)
        self.boot(self.hw.sleep.wake_reason())

    def _cancel_timers(self):
        for name in ("popup_timer", "photo_timer", "prompt_timer", "usb_timer"):
            t = getattr(self, name)
            if t is not None:
                t.cancel()
                setattr(self, name, None)
        hide(self.cam.prompt)

    # -- frames -------------------------------------------------------------

    def _frame(self, t):
        if self.hw.sleep.sleeping or self.page in (ALBUM, USB):
            return
        t0 = time.ticks_us()
        buf = self.hw.preview.frame(self.mag)
        t1 = time.ticks_us()
        if self.page == AI:
            self._draw_detections(buf)
        t2 = time.ticks_us()
        if self.recording:
            self.hw.recorder.tick(buf)
        t3 = time.ticks_us()
        self.cam.refresh_preview()
        t4 = time.ticks_us()
        fs = self.frame_stats
        if not self._first_frame_seen:
            self._first_frame_seen = True
            print("eyecam: first frame at %d ms" % time.ticks_ms())
        fs["cycle_t0"] = t0
        fs["n"] += 1
        fs["preview_us"] += time.ticks_diff(t1, t0)
        fs["detect_us"] += time.ticks_diff(t2, t1)
        fs["record_us"] += time.ticks_diff(t3, t2)
        if fs["last_us"]:
            fs["gap_us"] += time.ticks_diff(t0, fs["last_us"])
        fs["last_us"] = t0

    @staticmethod
    def _fresh_stats():
        return {"n": 0, "preview_us": 0, "detect_us": 0, "record_us": 0, "gap_us": 0, "last_us": 0,
                "cycle_us": 0, "cycle_n": 0, "cycle_t0": None}

    @staticmethod
    def _lvgl_rest(ms):
        """Cap the LVGL loop's rest after a slow refresh; None restores its default."""
        try:
            import display_driver

            loop = display_driver.event_loop.current_instance()
            if loop is not None:
                loop.max_yield_ms = display_driver.event_loop.max_yield_ms if ms is None else ms
        except Exception:
            pass  # a desktop display has no such loop

    def _refresh_done(self):
        """REFR_READY: how long LVGL's whole refresh took, cut included."""
        fs = self.frame_stats
        t0 = fs.get("cycle_t0")
        if t0 is not None:
            fs["cycle_us"] += time.ticks_diff(time.ticks_us(), t0)
            fs["cycle_n"] += 1
            fs["cycle_t0"] = None

    def close(self):
        if self.scaled is not None:
            self.scaled.close()
            self.scaled = None
        if self._refr_cb is not None:
            try:
                self._refr_disp.remove_event_cb(self._refr_cb)
            except Exception:
                pass
            self._refr_cb = None

    def frame_report(self):
        """Average times of the frame loop since the last call, in ms."""
        fs = self.frame_stats
        n = max(1, fs["n"])
        out = "frames %d: preview %.1f, detect %.1f, record %.1f, refresh cycle %.1f, between %.1f ms" % (
            fs["n"], fs["preview_us"] / n / 1000, fs["detect_us"] / n / 1000, fs["record_us"] / n / 1000,
            fs["cycle_us"] / max(1, fs["cycle_n"]) / 1000, fs["gap_us"] / max(1, n - 1) / 1000)
        self.frame_stats = self._fresh_stats()
        try:
            import board_config

            drv = board_config.display_drv
            d = drv.fps()
            if d is None:
                drv.measure_fps(True)
                out += "; display fps: measuring from now"
            else:
                out += "; display: %.1f fps, present %.1f ms (max %.1f), busy %.2f" % (d["fps"], d["present_ms"], d["present_ms_max"], d["busy"])
        except Exception as e:
            out += "; display fps: %r" % (e,)
        return out

    def _draw_detections(self, buf):
        det = self.hw.detector
        boxes = det.people(buf, 240, 240) if self.ai_mode == "pedestrian" else det.faces(buf, 240, 240)
        fb = self.fb
        for x0, y0, x1, y1, pts in boxes:
            for k in range(5):  # red, 5 px thick
                fb.rect(x0 + k, y0 + k, x1 - x0 - 2 * k, y1 - y0 - 2 * k, 0xF800)
            if pts:
                for px, py in pts:  # green key points, 7x7
                    fb.fill_rect(px - 3, py - 3, 7, 7, 0x07E0)

    def _rotate_poll(self, t):
        want = self.hw.accel.rotation() if self.options[0] == 1 else 0
        if want == self.rotation:
            return
        self.rotation = want
        turn = getattr(self.hw, "turn_screen", None)
        if turn is not None:
            panel = turn(want)  # the panel turns, and the UI with it
            self.hw.preview.rotate(panel)  # the camera turned with the board: turn its picture back
            self.cam.pin_hints(panel)  # the key hints stay by the switches
            self.album.pin_hints(panel)
            return
        try:
            lv.display_get_default().set_rotation(
                (lv.DISPLAY_ROTATION._0, lv.DISPLAY_ROTATION._90,
                 lv.DISPLAY_ROTATION._180, lv.DISPLAY_ROTATION._270)[want // 90])
        except (AttributeError, RuntimeError):
            pass
        self.hw.preview.rotate((360 - want) % 360)

    # -- settings -------------------------------------------------------------

    def init_settings_display(self):
        for i in range(4):
            self.update_setting_display(i)

    def update_setting_display(self, i):
        key, opts = OPTIONS[i]
        self.options[i] %= len(opts)
        self.cam.values[i].set_text(opts[self.options[i]])
        self.s.set(key, self.options[i])

    def apply_settings(self):
        self.hw.preview_color = tuple(self.camera_vals)
        self.album.od = self.options[1] == 1
        if hasattr(self.hw.recorder, "prepare"):
            self.hw.recorder.prepare(RESOLUTIONS[self.options[2]])

    def update_settings_focus(self, n):
        for r in self.cam.rows + [self.cam.back]:
            focus(r, False)
        self.item = n
        focus((self.cam.rows + [self.cam.back])[n], True)

    def update_camera_settings_focus(self, n):
        for r in self.cam.cam_rows + [self.cam.back]:
            focus(r, False)
        self.cam_item = n
        focus((self.cam.cam_rows + [self.cam.back])[n], True)

    def switch_to_camera_settings_panel(self):
        hide(self.cam.settings)
        show(self.cam.cam_settings)
        for s, v in zip(self.cam.sliders, self.camera_vals):
            s.set_value(v, False)
        self.update_camera_settings_focus(0)
        self.cam_panel = True

    def switch_to_main_settings_panel(self):
        hide(self.cam.cam_settings)
        show(self.cam.settings)
        self.cam_panel = False

    def _slider(self, delta):
        if self.page != SETTINGS or not self.cam_panel or self.cam_item >= 4:
            return
        i = self.cam_item
        v = max(0, min(100, self.camera_vals[i] + delta))
        self.camera_vals[i] = v
        self.cam.sliders[i].set_value(v, True)
        self.s.set(CAMERA_KEYS[i], v)
        self.apply_settings()

    def set_magnification(self, m):
        self.mag = max(MAG_MIN, min(MAG_MAX, m))
        self.cam.factor.set_text("%dX" % self.mag)
        self.s.set("magnify", self.mag)

    def set_interval_time(self, t):
        if t > INTERVAL_MAX:
            t = INTERVAL_MIN
        elif t < INTERVAL_MIN:
            t = INTERVAL_MAX
        self.interval = t
        self.cam.interval_time.set_text("%dmin" % t)
        self.cam.prompt_value.set_text("%d" % t)
        self.s.set("int_time", t)

    # -- pages ----------------------------------------------------------------

    def clear_page(self):
        self.cam.clear_page()

    def popup_visible(self):
        return any(visible(p) for p in self.cam.popups)

    def clear_popup_window(self):
        if not self.popup_visible():
            return
        if self.popup_timer is not None:
            self.popup_timer.fire()
        if self.photo_timer is not None:
            self.photo_timer.fire()
        hide(*self.cam.popups)
        if self.page == AI and self.cam.ai_label is not None:
            show(self.cam.ai_label)

    def _popup_page(self, page, pop):
        self.page = page
        self.clear_page()
        show(pop)
        if self.popup_timer is None:
            self.popup_timer = Timer(self.scope, POPUP_MS, lambda: self._popup_done(pop))

    def _popup_done(self, pop):
        c = self.cam
        hide(pop)
        if pop is c.pop_camera:
            show(c.mask_camera, c.factor, c.x2, c.x3, c.menu, c.sd if self.sd_mounted else c.no_sd)
        elif pop is c.pop_interval:
            show(c.mask_interval, c.factor, c.plus5, c.minus5, c.menu, c.interval_time,
                 c.sd if self.sd_mounted else c.no_sd)
        elif pop is c.pop_video:
            show(c.mask_video, c.menu, c.x2, c.x3, c.factor, c.sd if self.sd_mounted else c.no_sd)
        elif pop is c.pop_ai:
            show(c.mask_ai, c.factor, c.up, c.down, c.menu, c.ai_label)
        self.popup_timer = None

    def goto_page(self, page):
        if self.page == AI and page != AI and hasattr(self.hw.detector, "release"):
            self.hw.detector.release()  # the models' memory goes back on leaving the page
        self.page = page
        c = self.cam
        if page == CAMERA:
            self._popup_page(CAMERA, c.pop_camera)
        elif page == INTERVAL:
            self._popup_page(INTERVAL, c.pop_interval)
        elif page == VIDEO:
            self._popup_page(VIDEO, c.pop_video)
        elif page == AI:
            self.clear_page()
            lb = c.make_ai_label()
            hide(lb)
            self._update_ai_label()
            show(c.pop_ai)
            if self.popup_timer is None:
                self.popup_timer = Timer(self.scope, POPUP_MS, lambda: self._popup_done(c.pop_ai))
        elif page == ALBUM:
            self.album.refresh()
            self.clear_page()
            lv.screen_load(self.album_scr)
            (hide if self.sd_mounted else show)(self.album.sd_warning)
        elif page == USB:
            self.clear_page()
            lv.screen_load(self.usb_scr)
            u = self.usb
            if self.usb_mounted:
                hide(u.page1, u.warning)
                show(u.page2)
            else:
                show(u.page1)
                hide(u.page2, u.warning)
            (hide if self.sd_mounted else show)(u.no_sd)
        elif page == SETTINGS:
            self.clear_page()
            show(c.settings, c.back, c.select, c.up, c.down)
            self.init_settings_display()
            self.update_settings_focus(0)
            self.cam_panel = False
        else:
            self.page = MAIN
            self.clear_page()
            show(c.wheel.cont, c.info, c.select, c.up, c.down, c.mask_large)
            lv.screen_load(self.cam_scr)

    def _update_ai_label(self):
        lb = self.cam.ai_label
        if lb is not None:
            lb.set_text("Mode: Pedestrian" if self.ai_mode == "pedestrian" else "Mode: Face")

    def change_ai_mode(self, mode):
        self.ai_mode = mode
        self._update_ai_label()
        if self.cam.ai_label is not None and not visible(self.cam.pop_ai):
            show(self.cam.ai_label)

    def set_sd_card_mounted(self, mounted):
        self.sd_mounted = mounted
        if self.page not in (CAMERA, INTERVAL, VIDEO, ALBUM):
            return
        if mounted:
            hide(self.cam.no_sd)
            show(self.cam.sd)
        else:
            hide(self.cam.sd)
            show(self.cam.no_sd)

    def set_usb_disk_mounted(self, state):
        self.usb_mounted = state == "connected"
        # The host's events come from the USB stack, at any point of LVGL's own
        # refresh: change the page on the loop's own time (an LVGL assert hangs
        # the board otherwise).
        self.scope.after(1, lambda t: self.goto_page(USB))

    def handle_usb_disk_page(self):
        if self.page != USB:
            return False
        u = self.usb
        if visible(u.page1):
            self.goto_page(MAIN)
        elif visible(u.page2):
            show(u.warning)
            hide(u.page1, u.page2)
            if self.usb_timer is None:
                self.usb_timer = Timer(self.scope, USB_WARNING_MS, self._usb_warning_done)
        return True

    def _usb_warning_done(self):
        hide(self.usb.warning, self.usb.page1)
        show(self.usb.page2)
        self.usb_timer = None

    # -- interval -------------------------------------------------------------

    def _show_prompt(self):
        if not visible(self.cam.prompt):
            show(self.cam.prompt)
            if self.prompt_timer is None:
                self.prompt_timer = Timer(self.scope, PROMPT_MS, self._prompt_done)
        elif self.prompt_timer is not None:  # lv_timer_reset
            self.prompt_timer.cancel()
            self.prompt_timer = Timer(self.scope, PROMPT_MS, self._prompt_done)

    def _prompt_done(self):
        hide(self.cam.prompt)
        self.prompt_timer = None

    def start_interval_timer(self):
        self.clear_page()
        self.cam.start_title.set_text("Starting %d min" % self.interval)
        show(self.cam.pop_start)

    def popup_interval_timer_warning(self):
        if self.page != INTERVAL:
            return
        count = self.s.photo_count
        self.clear_page()
        self.cam.end_title.set_text("Ended %d min" % self.interval)
        self.cam.end_body.set_text("%d photos saved to \n       SD Card" % count)
        show(self.cam.pop_end)
        if self.photo_timer is None:
            self.photo_timer = Timer(self.scope, INTERVAL_END_MS, lambda: self._photo_popup_done(self.cam.pop_end))

    def _photo_popup_done(self, pop):
        c = self.cam
        hide(pop)
        show(c.mask_interval, c.factor, c.plus5, c.minus5, c.menu, c.interval_time,
             c.sd if self.sd_mounted else c.no_sd)
        self.photo_timer = None
        if pop is c.pop_start:
            self.start_interval_photo(self.interval)

    # -- photos and video ---------------------------------------------------

    def take_photo(self):
        path = self.hw.photo.take(self.mag, RESOLUTIONS[self.options[2]], self.options[3] == 1)
        self.events.append(("photo", path))
        return path

    def _video_tick(self, t):
        if not self.recording:
            return
        self.rec_secs += 1
        h, m, s = self.rec_secs // 3600, (self.rec_secs % 3600) // 60, self.rec_secs % 60
        if h:
            self.cam.red_time.set_text("%02d:%02d:%02d" % (h, m, s))
        else:
            self.cam.red_time.set_text("%02d:%02d" % (m, s))

    def _stop_video(self):
        self.hw.recorder.stop()
        self.events.append(("video", self.hw.recorder.frames))
        self.recording = False
        self._lvgl_rest(IDLE_REST_MS)

    # -- buttons: ui_extra_btn_* ---------------------------------------------

    def btn_up(self):
        if self.popup_visible():
            return
        p, c = self.page, self.cam
        if p == MAIN:
            c.wheel.step(40)
        elif p == SETTINGS:
            if self.cam_panel:
                if self.cam_item == 0:
                    self.switch_to_main_settings_panel()
                    self.update_settings_focus(3)
                else:
                    self.update_camera_settings_focus(self.cam_item - 1)
            elif self.item > 0:
                self.update_settings_focus(self.item - 1)
        elif p in (CAMERA, VIDEO):
            self.set_magnification(2)
        elif p == INTERVAL:
            self.set_interval_time(self.interval + INTERVAL_STEP)
            self._show_prompt()
        elif p == ALBUM:
            if self.album.dialog_open():
                self.album.toggle_choice()
        elif p == AI:
            self.change_ai_mode("face" if self.ai_mode == "pedestrian" else "pedestrian")

    def btn_down(self):
        if self.popup_visible():
            return
        p, c = self.page, self.cam
        if p == MAIN:
            c.wheel.step(-40)
        elif p == SETTINGS:
            if self.cam_panel:
                if self.cam_item < 4:
                    self.update_camera_settings_focus(self.cam_item + 1)
            elif self.item == 3:
                self.switch_to_camera_settings_panel()
            elif self.item < 4:
                self.update_settings_focus(self.item + 1)
        elif p in (CAMERA, VIDEO):
            self.set_magnification(3)
        elif p == INTERVAL:
            self.set_interval_time(self.interval - INTERVAL_STEP)
            self._show_prompt()
        elif p == ALBUM:
            if self.album.dialog_open():
                self.album.toggle_choice()
        elif p == AI:
            self.change_ai_mode("pedestrian" if self.ai_mode == "face" else "face")

    def btn_menu(self):
        c = self.cam
        if visible(c.pop_sd):
            return
        if self.popup_visible():
            self.clear_popup_window()
            return
        if c.wheel.scrolling and self.page == MAIN:
            return
        p = self.page
        if p == MAIN:
            self.goto_page(c.wheel.chosen())
        elif p == SETTINGS:
            if self.cam_panel and self.cam_item == 4:
                self.goto_page(MAIN)
                self.apply_settings()
                hide(c.cam_settings, c.settings)
            else:
                # Quirk kept: on the camera panel this cycles the main
                # panel's focused row (Flash), as the factory does.
                self.options[self.item] += 1
                self.update_setting_display(self.item)
                self.apply_settings()
        elif p == ALBUM:
            if self.album.dialog_open():
                if self.album.yes.has_state(lv.STATE.FOCUSED):
                    self.album.delete_current()
                hide(self.album.dialog)
            else:
                self.goto_page(MAIN)
        elif p == VIDEO:
            if not visible(c.red_dot):
                self.goto_page(MAIN)
            else:
                self._stop_video()
                hide(c.red_dot)
                show(c.red_time)  # quirk kept: the time stays up after a Menu stop
                if self.video_timer is not None:
                    self.video_timer.deinit()
                    self.video_timer = None
        else:
            self.goto_page(MAIN)
            if visible(c.pop_space):
                hide(c.pop_space)
            if self.prompt_timer is not None:
                self.prompt_timer.fire()
            if p == AI and c.ai_label is not None:
                hide(c.ai_label)

    def btn_encoder(self):
        c = self.cam
        if any(visible(x) for x in (c.pop_camera, c.pop_interval, c.pop_video, c.pop_start, c.pop_end)):
            self.clear_popup_window()
            return
        if visible(c.pop_sd):
            if self.page in (CAMERA, INTERVAL, VIDEO):
                self.goto_page(self.page)
            self.clear_popup_window()
            return
        if not self.sd_mounted:
            if self.page in (CAMERA, INTERVAL, VIDEO):
                self.clear_page()
                show(c.pop_sd)
            elif self.page == MAIN:
                self.btn_menu()
            return
        if c.wheel.scrolling and self.page == MAIN:
            return
        p = self.page
        if p == MAIN:
            self.btn_menu()
        elif p == INTERVAL:
            if self.prompt_timer is not None:
                self.prompt_timer.fire()
            self.start_interval_timer()
            if self.photo_timer is None:
                self.photo_timer = Timer(self.scope, INTERVAL_START_MS, lambda: self._photo_popup_done(c.pop_start))
        elif p == CAMERA:
            if self.hw.storage.free() <= MIN_FREE_PHOTO:
                self.clear_page()
                show(c.pop_space)
                return
            hide(c.pop_space)
            self.take_photo()
        elif p == ALBUM:
            if not self.album.dialog_open():
                show(self.album.dialog)
                self.album.toggle_choice()
                self.album.toggle_choice()  # as the factory: twice, so NO starts focused
            else:
                if self.album.yes.has_state(lv.STATE.FOCUSED):
                    self.album.delete_current()
                hide(self.album.dialog)
        elif p == VIDEO:
            if not visible(c.red_dot):
                if self.hw.storage.free() < MIN_FREE_VIDEO:
                    self.clear_page()
                    show(c.pop_space)
                    return
                hide(c.pop_space)
                if self.hw.recorder.start(self.mag, RESOLUTIONS[self.options[2]]) is False:
                    self._say(getattr(self.hw.recorder, "why", None) or "Video can't be recorded here")
                    return
                self.recording = True
                self._lvgl_rest(None)  # the encoder's thread gets its share
                show(c.red_dot, c.red_time)
                self.rec_secs = 0
                c.red_time.set_text("00:00")
                if self.video_timer is None:
                    self.video_timer = self.scope.every(1000, self._video_tick)
            else:
                self._stop_video()
                hide(c.red_dot, c.red_time)
                if self.video_timer is not None:
                    self.video_timer.deinit()
                    self.video_timer = None

    def _say(self, text, ms=4000):
        """Show *text* over the picture for a few seconds."""
        lb = self.cam.make_notice()
        lb.set_text(text)
        show(lb)
        if getattr(self, "notice_timer", None) is not None:
            self.notice_timer.fire()
        self.notice_timer = Timer(self.scope, ms, lambda: hide(lb))

    # -- app_control: buttons and knob ----------------------------------------

    def select_showing(self):
        """Whether the top hint reads Select (the knob press), not Menu."""
        return self.page not in (ALBUM, USB) and visible(self.cam.select)

    def button(self, name):
        """One press of "menu", "up", "down" or "encoder"."""
        if self.hw.sleep.sleeping:
            self.hw.sleep.wake("button")
            return
        if self.handle_usb_disk_page():
            return
        if name == "menu":
            self.btn_menu()
        elif name == "up":
            self.btn_up()
            if self.page == ALBUM and not self.album.dialog_open():
                self.album.prev()
        elif name == "down":
            self.btn_down()
            if self.page == ALBUM and not self.album.dialog_open():
                self.album.next()
        elif name == "encoder":
            self.btn_encoder()

    def detent(self, direction):
        """One knob detent: +1 right, -1 left. Three in a row make a step."""
        if self.hw.sleep.sleeping or self.page in (ALBUM, USB):
            return
        step = self.knob.detent(direction)
        if not step:
            return
        p = self.page
        if p in CAMERA_PAGES:
            self.set_magnification(self.mag - step)  # right: wider, left: closer
        elif p == MAIN:
            if step > 0:
                self.btn_up()
            else:
                self.btn_down()
        elif p == SETTINGS:
            self._slider(-5 * step)  # right lowers the slider, left raises it
