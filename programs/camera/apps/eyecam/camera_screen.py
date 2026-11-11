# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The Camera screen, object for object as the factory's SquareLine export
builds it, in the same creation order (later objects draw on top).

The factory draws the live picture into an LVGL 8 canvas and hangs every
overlay off that canvas. Here the canvas is a 240x240 container whose first
child is an ``lv.image`` showing the preview buffer, so the overlays keep
their parent, offsets and stacking.
"""

import lvgl as lv

from . import assets
from .widgets import CENTER, bar, hide, image, label, panel, pin_to_panel, popup, rgb565_dsc, row
from .wheel import Wheel

ROWS_MAIN = (
    # (attribute, w, h, x, y, item text, item x)
    ("gyroscope", 172, 30, 1, -45, "Display Rotate", -26),
    ("od", 172, 30, 1, -10, "Obj Det(YOLO)", -28),
    ("res", 172, 27, 0, 25, "Resolution", -43),
    ("flash", 172, 27, 0, 60, "Flash", -43),
)
ROWS_CAMERA = (
    ("contrast", -55, "Contrast"),
    ("saturation", -15, "Saturation"),
    ("brightness", 25, "Brightness"),
    ("hue", 65, "Hue"),
)


class CameraScreen:
    def __init__(self, screen, frame_buf):
        self.screen = screen
        c = lv.obj(screen)
        c.remove_style_all()
        c.set_size(240, 240)
        c.align(CENTER, 0, 0)
        c.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.canvas = c

        self.preview = lv.image(c)
        self._dsc = rgb565_dsc(frame_buf, 240, 240)
        self.preview.set_src(self._dsc)
        self.preview.align(CENTER, 0, 0)

        # Right-side key hints, then the big menu mask.
        self.select = image(c, "button_select", 100, -47)
        self.up = image(c, "up_button", 100, 0)
        self.down = image(c, "button_down", 100, 55)
        self.hints = [(self.select, 100, -47), (self.up, 100, 0), (self.down, 100, 55)]
        self.mask_large = panel(c, 240, 240, -134, 0, radius=360, bg=0xD6D5D5)

        self.pop_camera = popup(c, 212, 213, -1, -3, [("Camera Mode", -2, -59)], 201, -1, -27,
                                "Rotate wheel to\n   adjust zoom", "semi24", -1, 35)[0]
        self.pop_ai = popup(c, 212, 213, -1, -3, [("AI Detect Mode", -2, -59)], 201, -1, -27,
                            "Rotate wheel to\n   adjust zoom", "semi24", -1, 35)[0]

        self.no_sd = image(c, "sdcard_no", -102, -101)
        self.sd = image(c, "sdcard_yes", -102, -101)
        self.menu = image(c, "button_menu", 100, -47)
        self.x2 = label(c, "2X", 100, 0, "semi18", hidden=True)
        self.x3 = label(c, "3X", 100, 55, "semi18", hidden=True)
        self.factor = label(c, "1X", 0, -100, "semi18", hidden=True)

        self.mask_camera = self._pill(c, "camera_small")
        self.mask_ai = self._pill(c, "ai_detect_small")
        self.pop_interval = popup(c, 212, 212, -3, 0, [("      Interval \n  Camera Mode", -4, -59)], 200, 0, -14,
                                  "1)  Set Interval\n2) Press wheel to \nstart shooting", "semi24", -1, 45)[0]
        self.mask_interval = self._pill(c, "interval_small")
        self.plus5 = label(c, "+5m", 100, 0, "semi18", hidden=True)
        self.minus5 = label(c, "-5m", 100, 55, "semi18", hidden=True)
        # The camera pages' own key hints, in the same column by the switches.
        self.hints += [(self.menu, 100, -47), (self.x2, 100, 0), (self.x3, 100, 55),
                       (self.plus5, 100, 0), (self.minus5, 100, 55)]
        self.interval_time = label(c, "30min", -90, 100, "semi18", hidden=True)

        self.pop_video = popup(c, 212, 212, -2, -1, [("Video Mode", -1, -66)], 183, -3, -32,
                               "Rotate wheel to \n  adjust zoom.", "semi24", 1, 32)[0]
        self.mask_video = self._pill(c, "video_small")
        self.pop_sd = popup(c, 212, 212, -2, -4, [("Warning", -4, -70)], 197, -1, -36,
                            "No SD card detected\n\n  Insert SD Card to \n          continue", "semi22", 3, 39,
                            title_color=0xFF0000)[0]
        p, titles, _ = popup(c, 212, 212, -3, 0, [("Starting 30 min", 1, -74), ("Interval Cam", -1, -38)], 199, 0, -13,
                             "   Display will be \n        dimmed\nPress any button to\n  end interval cam\n", "semi22", 0, 58)
        self.pop_start, self.start_title = p, titles[0]
        p, titles, body = popup(c, 212, 212, -3, -3, [("Ended 30 min", 1, -67), ("Interval Cam", 1, -23)], 194, 1, 10,
                                "3 photos saved to \n       SD Card", "semi22", 4, 61)
        self.pop_end, self.end_title, self.end_body = p, titles[0], body

        self.red_dot = image(c, "reddot_recording", 102, -102)
        self.red_time = label(c, "22:22", 69, -102, hidden=True)

        # Settings: the four rows, then "Back to Menu" beside the panel.
        self.settings = panel(c, 183, 170, -14, -16)
        label(self.settings, "Settings", 0, -72, "bold18")
        self.rows = []
        self.values = []
        for _name, w, h, x, y, text, tx in ROWS_MAIN:
            r = row(self.settings, w, h, x, y)
            label(r, text, tx, 0, "semi18")
            self.values.append(label(r, "Off", 55, 0, "semi18"))
            self.rows.append(r)
        self.back = panel(c, 181, 33, -12, 92)
        self.back.set_style_bg_color(lv.color_hex(0xC9C9C9), lv.PART.MAIN | lv.STATE.FOCUSED)
        self.back.set_style_bg_opa(120, lv.PART.MAIN | lv.STATE.FOCUSED)
        label(self.back, "Back to Menu", 0, 1, "semi18")

        self.prompt = panel(c, 125, 50, 3, 1, radius=10, bg=0xFFFFFF)
        self.prompt_value = label(self.prompt, "30", -20, 0, "semi24", 0xFF0000)
        label(self.prompt, "min", 21, -2, "semi24", None)
        self.pop_space = popup(c, 212, 212, -2, -4, [("Warning", -4, -70)], 197, -1, -36,
                               "   Insufficient \n\n SD card space!", "semi22", 3, 39, title_color=0xFF0000)[0]

        self.wheel = Wheel(c)
        self.info = self.wheel.info

        # On the screen, above the canvas: the camera image settings.
        self.cam_settings = panel(screen, 183, 170, -14, -16)
        self.cam_rows = []
        self.sliders = []
        for _name, y, text in ROWS_CAMERA:
            r = row(self.cam_settings, 172, 30, 0, y)
            label(r, text, -49, 0, "semi14")
            s = lv.slider(r)
            s.set_range(0, 100)
            s.set_value(0, False)
            s.set_size(84, 2)
            s.align(CENTER, 38, 0)
            s.set_style_bg_color(lv.color_hex(0x000000), lv.PART.INDICATOR)
            s.set_style_bg_opa(255, lv.PART.INDICATOR)
            s.set_style_bg_color(lv.color_hex(0x000000), lv.PART.KNOB)
            s.set_style_bg_opa(255, lv.PART.KNOB)
            self.cam_rows.append(r)
            self.sliders.append(s)

        self.ai_label = None  # made on the first visit to AI DETECT, as the factory does

        # Boxes drawn by the detector, above the picture and below the overlays.
        self.popups = (self.pop_camera, self.pop_interval, self.pop_video, self.pop_sd,
                       self.pop_start, self.pop_end, self.pop_ai)


    def pin_hints(self, turn):
        """The key hints stay beside the switches when the panel turns."""
        pin_to_panel(self.hints, turn)
    def _pill(self, parent, icon):
        p = panel(parent, 100, 87, -120, 0, radius=360)
        image(p, icon, 20, 0, hidden=False)
        return p

    def make_ai_label(self):
        if self.ai_label is None:
            lb = lv.label(self.screen)
            lb.set_style_text_font(assets.montserrat(16), 0)
            lb.set_style_text_color(lv.color_hex(0xFF0000), 0)
            lb.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
            lb.set_style_bg_opa(179, 0)
            lb.set_style_radius(5, 0)
            lb.set_style_pad_all(5, 0)
            lb.align(lv.ALIGN.BOTTOM_LEFT, 10, -10)
            self.ai_label = lb
        return self.ai_label

    def make_notice(self):
        """A line along the bottom of the picture for a message the factory
        UI has no popup for (a video size this board can't encode)."""
        if getattr(self, "notice", None) is None:
            lb = lv.label(self.screen)
            lb.set_style_text_font(assets.montserrat(16), 0)
            lb.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
            lb.set_style_bg_color(lv.color_hex(0x000000), 0)
            lb.set_style_bg_opa(200, 0)
            lb.set_style_radius(5, 0)
            lb.set_style_pad_all(5, 0)
            lb.set_width(220)
            lb.set_long_mode(lv.label.LONG_MODE.WRAP)
            lb.align(lv.ALIGN.BOTTOM_MID, 0, -10)
            self.notice = lb
        return self.notice

    def refresh_preview(self):
        self.preview.invalidate()

    def clear_page(self):
        """The factory's ``ui_extra_clear_page``: everything off but the
        space warning and the interval prompt."""
        hide(self.select, self.up, self.down, self.menu, self.x2, self.x3, self.plus5, self.minus5,
             self.mask_large, self.mask_camera, self.mask_ai, self.mask_interval, self.mask_video,
             self.pop_camera, self.pop_interval, self.pop_video, self.pop_sd, self.pop_start,
             self.pop_end, self.pop_ai, self.no_sd, self.sd, self.factor, self.interval_time,
             self.red_dot, self.red_time, self.settings, self.back,
             self.wheel.cont, self.info, self.ai_label)
