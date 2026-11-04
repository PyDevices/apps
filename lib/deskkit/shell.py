# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.shell: swipe between apps, drift back to the first, and sleep at night."""

import board_config
import lvgl as lv
from appkit import Shell

from . import localtime

_CHECK_MS = 1000


def is_awake(hour, weekday, awake, weekends):
    """Return True when the screen belongs on at this time.

    Args:
        hour (int): The local hour.
        weekday (int): 0 for Monday through 6 for Sunday.
        awake (tuple): ``(from, until)`` hours, or None for always.
        weekends (bool): True to keep those hours on Saturday and Sunday.
    """
    if awake is None:
        return True
    if weekday >= 5 and not weekends:
        return False
    return awake[0] <= hour < awake[1]


class DeskShell(Shell):
    """Give each app the whole screen, with no buttons around it.

    Args:
        launcher (Launcher): The launcher it serves.
        apps (tuple): The apps to swipe between; the first is the home screen.
        awake (tuple): The hours the screen is lit, or None for always.
        weekends (bool): True to keep those hours on Saturday and Sunday.
        idle_ms (int): How long a touch keeps the screen awake, and how long
            an app other than the first stays up without one.
    """

    def __init__(self, launcher, apps, *, awake, weekends, idle_ms):
        super().__init__(launcher)
        self.apps = apps
        self.awake = awake
        self.weekends = weekends
        self.idle_ms = idle_ms
        self._lit = True
        self._timer = lv.timer_create(self._check, _CHECK_MS, None)

    def make_root(self, scope):
        root = super().make_root(scope)
        root.add_event_cb(self._gesture, lv.EVENT.GESTURE, None)
        return root

    def _gesture(self, _event):
        direction = lv.indev_active().get_gesture_dir()
        if direction == lv.DIR.LEFT:
            step = 1
        elif direction == lv.DIR.RIGHT:
            step = -1
        else:
            return  # up and down are the app's
        lv.indev_active().wait_release()
        apps = self.apps
        current = self.launcher.current
        if current in apps:
            self.launcher.request(apps[(apps.index(current) + step) % len(apps)])

    def _set_lit(self, lit):
        if lit == self._lit:
            return
        self._lit = lit
        backlight = getattr(board_config, "backlight", None)
        if backlight is not None:
            backlight.value(1 if lit else 0)
        else:
            board_config.display_drv.brightness = 1.0 if lit else 0.0

    def _check(self, _timer):
        idle = lv.display_get_default().get_inactive_time()
        if idle >= self.idle_ms and self.launcher.current != self.apps[0]:
            if self.launcher.current in self.apps:
                self.launcher.request(self.apps[0])
        # Without the real time, a dark screen could be dark for no reason.
        if not localtime.is_set():
            self._set_lit(True)
            return
        t = localtime.now()
        self._set_lit(is_awake(t[3], t[6], self.awake, self.weekends) or idle < self.idle_ms)
