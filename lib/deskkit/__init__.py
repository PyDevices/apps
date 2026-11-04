# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit: put a clock and the weather on a screen that sits on a desk.

``main.py`` is two lines::

    import deskkit
    deskkit.run()

It joins Wi-Fi with `wifi_manager`, sets the clock and starts the first app.
A swipe left or right moves between the apps, and anything but the first goes
back to it after a minute without a touch. The screen goes dark outside the
hours you pass.
"""

APPS = ("clock", "weather")

launcher = None  # the running one, to reach from the REPL


def _say(lv, text):
    # Joining can take a minute on a weak link, and a dark screen looks broken.
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0), 0)
    label = lv.label(scr)
    label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    label.set_style_text_font(lv.font_montserrat_24, 0)
    label.set_text(text)
    label.center()
    lv.refr_now(None)
    return label


def run(*, hostname="deskclock", apps=APPS, awake=(7, 18), weekends=False, idle_ms=60_000):
    """Join Wi-Fi, set the clock and run *apps* until the program ends.

    Args:
        hostname (str): The name the board answers to on the network.
        apps (tuple): The apps to swipe between, first one the home screen.
            Each is a folder under ``apps/``.
        awake (tuple): The hours the screen stays lit, as ``(from, until)``,
            or None to leave it on.
        weekends (bool): True to keep those hours on Saturday and Sunday too.
        idle_ms (int): How long without a touch before going back to the first
            app, and before a screen woken at night goes dark again.
    """
    # Here rather than at the top, so an app can import deskkit.forecast without
    # opening the display.
    import lvgl as lv
    import wifi_manager
    from appkit import Launcher, serve
    from display_driver import app

    from . import forecast, localtime
    from .shell import DeskShell

    global launcher
    label = _say(lv, "Joining Wi-Fi")
    wifi_manager.connect(hostname=hostname)
    label.set_text("Setting the time")
    lv.refr_now(None)
    localtime.sync()
    label.delete()

    launcher = Launcher(app)
    for name in apps:
        launcher.add(name, "apps." + name)
    launcher.shell = DeskShell(launcher, apps, awake=awake, weekends=weekends, idle_ms=idle_ms)
    # With no place yet there's no timezone either, so the place comes first.
    launcher.boot(apps[0] if forecast.place() else "weather")
    serve(app)
