# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Home's pages and the board's own apps, on real LVGL with no window.

The repository's own apps run through a real Launcher under touchkit's
TouchShell, on a 480x320 screen with the status bar, as on a board. Home has
a tab per category, the tabs as tall as the bar, and the Home icon as its
title with nothing else on the bar; the board's own apps (Info, Settings,
Hidden apps, the REPL and the Shell) are on the System page and Gamepad on
Games. Settings saves the board's name through boarddev, and Wi-Fi power
saving through a stand-in for wifi_manager, saying when it's the default.

    APPKIT_DATA=/tmp/home python tests/appkit/home_contract.py
    micropython tests/appkit/home_contract.py

``HOME_SHOTS=<folder>`` saves each screen as a raw RGB565 frame.
``HOME_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks must
then fail. Exits 1 if a check fails, 2 if something it needs isn't there.
"""

import json
import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
# lib first: tests/appkit would hide the real appkit.
_PATHS = [_join(_ROOT, "lib"), _HERE, _TESTS,
          _join(_OMNI, "packages", "endpointkit"), _LIB]
# On MicroPython icons and ttfio come built in, so the font stays in flash and off the heap.
if sys.implementation.name != "micropython":
    _PATHS.insert(3, _join(_OMNI, "packages", "icons"))
    _PATHS.append(_join(_OMNI, "utils"))   # ttfio over freetype-py
sys.path[:0] = _PATHS

try:
    import boarddev
    import endpointkit
    import icons  # noqa: F401
    import lvgl as lv
    from endpointkit import fake
except ImportError as e:
    print("can't run the Home checks:", e)
    sys.exit(2)

import _headless  # noqa: E402

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


SW, SH = 480, 320
SHOTS = os.getenv("HOME_SHOTS")


class _Board:
    pass


# No display driver, BOOT button or battery: only the display made here.
sys.modules["board_config"] = _Board()
sys.modules["board_peripherals"] = _Board()


class _WifiManager:
    """wifi_manager's power saving calls, over a choice kept here."""

    def __init__(self):
        self.chosen = None
        self.battery = False
        self.bluetooth = False

    def _settings(self):
        return {} if self.chosen is None else {"power_save": self.chosen}

    def _bluetooth_on(self):
        return self.bluetooth

    def power_save(self):
        return self.battery if self.chosen is None else self.chosen

    def set_power_save(self, on):
        self.chosen = on


wm = _WifiManager()
sys.modules["wifi_manager"] = wm
_headless.display(SW, SH)
_headless.pointer()

import time  # noqa: E402

from appkit import connections  # noqa: E402
from appkit import launcher as L  # noqa: E402
from appkit.shell import Shell  # noqa: E402
from appdev import App  # noqa: E402
from touchkit import shell as touch  # noqa: E402

# The fakes are this device: the Shell registers no real provider beside them.
connections.register = lambda registry=None: []
fake.bench(endpointkit.registry, delay=1)

la = L.Launcher(App.current() or App())
la.scan(_join(_ROOT, "apps"))
la.home = "home"

import apps.home as home  # noqa: E402
import apps.settings as settings  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_tall_tabs():
    # The tabs keep their old 56 px, whatever the bar's height.
    home.tab_height = lambda scope: 56


def _plant_home_word():
    # The bar says "Home" in words on the home screen.
    Shell.home_title = lambda self: "Home"


def _plant_name_not_saved():
    # Save says it saved, and doesn't.
    settings.save_name = lambda text: "Saved"


def _plant_why_unsaid():
    # The switch shows on or off, and never says whether that's the default.
    real = settings.power_save_state
    settings.power_save_state = lambda: (real()[0], "")


def _plant_no_category():
    # Home puts every app on one page.
    real = home._pages
    home._pages = lambda info, hidden=(): [("More", [t for _, tiles in real(info, hidden) for t in tiles])]


PLANTS = {
    "tall_tabs": _plant_tall_tabs,
    "home_word": _plant_home_word,
    "name_not_saved": _plant_name_not_saved,
    "no_category": _plant_no_category,
    "why_unsaid": _plant_why_unsaid,
}
plant = os.getenv("HOME_PLANT")
if plant:
    PLANTS[plant]()
# The launcher unloads an app when it closes, and restarts the program when
# something still holds it: these checks hold none.
del home, settings


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def coords(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1


def tap(obj):
    x, y, w, h = coords(obj)
    _headless.touch(x + w // 2, y + h // 2, True, 50)
    _headless.touch(x + w // 2, y + h // 2, False, 50)


def walk(obj, cls, out=None):
    out = [] if out is None else out
    for i in range(obj.get_child_count()):
        c = obj.get_child(i)
        if c.check_type(cls):
            out.append(c)
        walk(c, cls, out)
    return out


def texts(obj):
    return [c.get_text() for c in walk(obj, lv.label_class)]


def find(obj, text):
    for c in walk(obj, lv.label_class):
        if c.get_text() == text:
            return c
    return None


def wait_for(name):
    # The launcher switches from a timer on the real clock: wait for it, up to 3 s.
    for _ in range(60):
        if la.current == name:
            break
        time.sleep(0.05)
        settle(40)
    settle()


def shot(name):
    if SHOTS:
        _headless.refresh()
        _headless.save_raw(_join(SHOTS, name + ".raw"), SW, SH)


def app_json(name):
    with open(_join(_ROOT, "apps", name, "app.json")) as f:
        return json.load(f)


restarts = []


def _no_restart(name, count=1):
    restarts.append(name)
    raise OSError("restarts are recorded, not done, in these checks")


L.restart_into = _no_restart

shell = touch.TouchShell(la)
la.shell = shell
bar = shell.bar
la.boot("home")
settle()
scope = la.scope
shot("home")

# -- the tabs -------------------------------------------------------------------

tv = walk(scope.root, lv.tabview_class)
tv = tv[0] if tv else None
check(tv is not None, "Home is a tab view")
tabs = tv.get_tab_bar() if tv is not None else None
names = [c.get_child(0).get_text() if c.get_child_count() else "" for c in walk(tabs, lv.button_class)] if tabs else []
check(names[:6] == ["Audio", "Desk", "Games", "Link", "System", "Video"] or names == ["Audio", "Desk", "Games", "Link", "System", "Video"],
      "a tab per category, in order, System and Games among them: %r" % (names,))
if tabs is not None:
    x, y, w, h = coords(tabs)
    check(h == bar.height and y + h == SH, "the tabs are as tall as the status bar, at the bottom: %r, bar %d" % ((y, h), bar.height))
    for c in walk(tabs, lv.label_class):
        lx, ly, lw, lh = coords(c)
        if not (y <= ly and ly + lh <= y + h):
            check(False, "a tab's label is inside its tab: %r in %r" % ((ly, lh), (y, h)))
            break


def page_of(category):
    """The titles on *category*'s page, from the tiles Home made."""
    if tv is None or category not in names:
        return []
    page = tv.get_content().get_child(names.index(category))
    return [t for t in texts(page)]


system = page_of("System")
check(all(t in system for t in ("Info", "Settings", "Hidden apps")),
      "Info, Settings and Hidden apps are on the System page: %r" % (system,))
check(page_of("Games") == ["Gamepad"], "Gamepad is alone on Games: %r" % (page_of("Games"),))
desk = page_of("Desk")
check("REPL" not in desk and "Shell" not in desk and "System" not in desk, "Desk has none of them now: %r" % (desk,))
# The REPL and the Shell need os.dupterm, which CPython lacks, so they aren't
# scanned here: their app.json says where they go.
check(app_json("repl").get("category") == "System" and app_json("shell").get("category") == "System",
      "the REPL and the Shell are System apps")
check(not any(e.get("gear") for e in la.info.values()), "no app asks for a gear button")
check(la.info.get("system", {}).get("tile") is False and "Info" not in desk,
      "the old System folder stands in for Info, off the pages: %r" % (la.info.get("system"),))

# -- the bar on the home screen ---------------------------------------------------

check(bar.title.get_text() == "" and bar.title_icon is not None, "Home's title on the bar is the Home icon: %r" % (bar.title.get_text(),))
check(bar.header.get_child_count() == (2 if bar.title_icon is not None else 1),
      "and Home puts nothing else on the bar, no System or hidden-apps button: %d" % bar.header.get_child_count())
check(not walk(bar.header, lv.button_class), "no button in the bar's header on the home screen")

# -- Settings: the board's name ----------------------------------------------------

before = boarddev.name()
# Home's objects go with it: hold none past the switch.
del scope, tv, tabs, c
la.switch("settings")
settle()
check(la.current == "settings", "Settings opens: %r" % (la.current,))
fields = walk(la.scope.root, lv.textarea_class)
field = fields[0] if fields else None
check(field is not None and field.get_text() == before, "Device name shows the board's name: %r" % (field and field.get_text(),))
save = find(la.scope.root, "Save")
check(save is not None, "with a Save button")
shot("settings")
if field is not None and save is not None:
    field.set_text("kitchen-zero")
    tap(save.get_parent())
    settle()
    check(boarddev.name() == "kitchen-zero", "Save gives the board the name: %r" % (boarddev.name(),))
    check(any(t.startswith("Saved") for t in texts(la.scope.root)), "and says so")
    field.set_text("-kitchen")
    tap(save.get_parent())
    settle()
    check(boarddev.name() == "kitchen-zero", "a name the board can't take isn't saved: %r" % (boarddev.name(),))
    check(any("hyphen" in t for t in texts(la.scope.root)), "and Settings says why: %r" % (texts(la.scope.root),))
    field.set_text("")
    tap(save.get_parent())
    settle()
    check(boarddev.name() == before, "an empty name goes back to the default: %r" % (boarddev.name(),))
    check(field.get_text() == before, "and the field shows it: %r" % (field.get_text(),))

# Wi-Fi power saving, on every screen size.
switches = walk(la.scope.root, lv.switch_class)
sw = switches[0] if switches else None
check(sw is not None and find(la.scope.root, "Wi-Fi power saving") is not None, "Settings has the Wi-Fi power saving switch")


def said():
    return [t for t in texts(la.scope.root) if t.startswith(("On ", "Off ", "Set by"))]


def flip(on):
    if on:
        sw.add_state(lv.STATE.CHECKED)
    else:
        sw.remove_state(lv.STATE.CHECKED)
    sw.send_event(lv.EVENT.VALUE_CHANGED, None)
    settle()


if sw is not None:
    check(not sw.has_state(lv.STATE.CHECKED) and said() == ["Off by default: no battery is fitted."],
          "with no battery it's off, and says that's the default: %r" % (said(),))
    flip(True)
    check(wm.chosen is True and said() == ["Set by you."], "turning it on is remembered, as set by you: %r %r" % (wm.chosen, said()))
    default = find(la.scope.root, "Default")
    if default is not None:
        tap(default.get_parent())
        settle()
    check(wm.chosen is None and not sw.has_state(lv.STATE.CHECKED), "Default forgets the choice: %r" % (wm.chosen,))
    wm.bluetooth = True
    la.switch("settings")
    settle()
    sw = walk(la.scope.root, lv.switch_class)[0]
    check(sw.has_state(lv.STATE.CHECKED) and said() == ["On by default: Bluetooth is running."],
          "while Bluetooth runs it's on, by default: %r" % (said(),))
    wm.bluetooth = False
    wm.battery = True
    la.switch("settings")
    settle()
    sw = walk(la.scope.root, lv.switch_class)[0]
    check(sw.has_state(lv.STATE.CHECKED) and said() == ["On by default: a battery is fitted."],
          "with a battery it's on, by default: %r" % (said(),))
    del sw
check(bar.title.get_text() == "Settings" and bar.title_icon is None, "an app's title is words again: %r" % (bar.title.get_text(),))

# -- Hidden apps and Info open --------------------------------------------------------

la.switch("hidden")
settle()
check(any(t.startswith("No app is hidden") for t in texts(la.scope.root)), "Hidden apps with none hidden says so")
shot("hidden")
# Unix MicroPython's sockets have no getsockname, which Info's network row reads.
if sys.implementation.name != "micropython":
    la.switch("info")
    settle()
    check(la.current == "info" and bar.title.get_text() == "Info", "Info opens, titled Info: %r" % (bar.title.get_text(),))
la.switch("home")
settle()
check(restarts == [], "nothing restarted: %r" % (restarts,))
la.stop()

import apps.info  # noqa: E402
import apps.system  # noqa: E402

check(not hasattr(apps.info, "_power_save_switch"), "Info has no power saving switch: Settings has the one")
check(apps.system.stats is apps.info.stats and apps.system.main is apps.info.main, "apps.system answers as apps.info")

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
