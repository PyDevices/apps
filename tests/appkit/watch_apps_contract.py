# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Steps, Battery and LoRa, the watch's own apps, on real LVGL with no window.

Each runs through a real Launcher under touchkit's TouchShell on a 240x240
screen, against a board whose accelerometer, battery and radio are fakes:
Steps shows the count and resets it, Battery shows the charge and switches
the charger, LoRa sends a packet and listens, and the radio's power goes
off when LoRa closes. On a board without the part, each says so.

    python tests/appkit/watch_apps_contract.py

``WATCH_SHOTS=<folder>`` saves each screen as a raw RGB565 frame.
``WATCH_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks must
then fail. Exits 1 if a check fails, 2 if something it needs isn't there.
"""

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
_PATHS = [_join(_ROOT, "lib"), _HERE, _TESTS, _join(_OMNI, "packages", "endpointkit"), _LIB]
if sys.implementation.name != "micropython":
    _PATHS.insert(3, _join(_OMNI, "packages", "icons"))
    _PATHS.append(_join(_OMNI, "utils"))
sys.path[:0] = _PATHS

try:
    import endpointkit
    import icons  # noqa: F401
    import lvgl as lv
    from endpointkit import fake
except ImportError as e:
    print("can't run the watch apps' checks:", e)
    sys.exit(2)

import _headless  # noqa: E402

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


W = 240
SHOTS = os.getenv("WATCH_SHOTS")


class _Accel:
    features_running = True
    steps = 4321
    activity = "walking"
    acceleration = (0.01, -0.02, 0.98)

    def reset_steps(self):
        self.steps = 0


class _Battery:
    percent = 64
    voltage = 3.91
    battery_status = "discharging"
    vbus_voltage = 0
    on = True

    def charger(self, enable=None):
        if enable is not None:
            self.on = bool(enable)
        return self.on


class _Radio:
    version = "SX1262 V2D 2D02"

    def __init__(self):
        self.sent = []
        self.listened = 0

    def configure(self, freq_mhz, **kw):
        self.freq = freq_mhz

    def send(self, data, timeout_ms=None):
        self.sent.append(bytes(data))
        return 41

    def channel_active(self, symbols=4):
        self.listened += 1
        return False


class _Drv:
    brightness = 1.0


accel, battery, radio = _Accel(), _Battery(), _Radio()
released = []


class _Board:
    PERIPHERALS = frozenset({"accelerometer", "battery", "lora"})
    display_drv = _Drv()
    accelerometer = accel
    lora = radio


class _Peripherals:
    PERIPHERALS = _Board.PERIPHERALS

    @staticmethod
    def battery():
        return battery

    @staticmethod
    def release(role):
        released.append(role)


sys.modules["board_config"] = _Board()
sys.modules["board_peripherals"] = _Peripherals()
_headless.display(W, W)
_headless.pointer()

import time  # noqa: E402

from appkit import connections  # noqa: E402
from appkit import launcher as L  # noqa: E402
from appdev import App  # noqa: E402
from touchkit import shell as touch  # noqa: E402

connections.register = lambda registry=None: []
fake.bench(endpointkit.registry, delay=1)

la = L.Launcher(App.current() or App())
la.scan(_join(_ROOT, "apps"))
la.home = "watch"

import apps.battery as battery_app  # noqa: E402
import apps.lora as lora_app  # noqa: E402
import apps.steps as steps_app  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_no_count():
    # Steps shows the live reading and never the count.
    steps_app.ui.huge = steps_app.ui.small
    _Accel.features_running = False


def _plant_charger_stuck():
    # The switch moves and the charger doesn't.
    _Battery.charger = lambda self, enable=None: self.on


def _plant_radio_left_on():
    # LoRa leaves the radio's power on when it closes.
    _Peripherals.release = staticmethod(lambda role: None)


def _plant_no_percent():
    # Battery leaves the charge out.
    real = battery_app.lines
    battery_app.lines = lambda b: real(b)[1:]


PLANTS = {
    "no_count": _plant_no_count,
    "charger_stuck": _plant_charger_stuck,
    "radio_left_on": _plant_radio_left_on,
    "no_percent": _plant_no_percent,
}
plant = os.getenv("WATCH_PLANT")
if plant:
    PLANTS[plant]()
del battery_app, lora_app, steps_app


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
    settle()


def walk(obj, cls, out=None):
    out = [] if out is None else out
    for i in range(obj.get_child_count()):
        c = obj.get_child(i)
        if c.check_type(cls):
            out.append(c)
        walk(c, cls, out)
    return out


def texts():
    return [c.get_text() for c in walk(lv.screen_active(), lv.label_class)]


def button(text):
    for b in walk(lv.screen_active(), lv.button_class):
        for lbl in walk(b, lv.label_class):
            if lbl.get_text() == text:
                return b
    return None


def open_app(name, shot=True):
    la.request(name)
    for _ in range(60):
        if la.current == name:
            break
        time.sleep(0.05)
        settle(40)
    settle(400)
    check(la.current == name, "%s opens: %r" % (name, la.current))
    if SHOTS and shot:
        _headless.refresh()
        _headless.save_raw(_join(SHOTS, name + ".raw"), W, W)


L.restart_into = lambda name, count=1: (_ for _ in ()).throw(OSError("no restarts in these checks"))
shell = touch.TouchShell(la)
la.shell = shell
la.boot("watch")
settle(400)

for name in ("steps", "battery", "lora"):
    check(name in la.names, "%s is installed" % (name,))

# -- Steps -------------------------------------------------------------------------

open_app("steps")
check("4321" in texts(), "Steps shows the count: %r" % (texts(),))
check("walking" in texts(), "and what you're doing")
b = button("Reset steps")
check(b is not None, "a Reset steps button")
if b is not None:
    tap(b)
    time.sleep(0.3)  # the screen reads the count on a timer of the real clock
    settle(400)
    check(accel.steps == 0 and "0" in texts(), "Reset steps starts the count again: %r" % (texts(),))

# -- Battery -------------------------------------------------------------------

open_app("battery")
joined = "\n".join(texts())
check("64%" in joined, "Battery shows the charge: %r" % (joined,))
check("3.91 V" in joined, "and the voltage")
sw = walk(lv.screen_active(), lv.switch_class)
check(len(sw) == 1, "a charger switch")
if sw:
    check(sw[0].has_state(lv.STATE.CHECKED), "on, as the charger is")
    tap(sw[0])
    check(battery.on is False, "a tap switches the charger off")

# -- LoRa ----------------------------------------------------------------------

open_app("lora")
check(any("SX1262" in t for t in texts()), "LoRa names the radio: %r" % (texts(),))
b = button("Send")
if b is not None:
    tap(b)
check(len(radio.sent) == 1, "Send sends a packet: %r" % (radio.sent,))
b = button("Listen")
if b is not None:
    tap(b)
check(radio.listened == 1 and any("quiet" in t for t in texts()), "Listen says the channel is quiet")
open_app("watch")
check("lora" in released, "leaving LoRa switches the radio's power off: %r" % (released,))

# -- without the parts ------------------------------------------------------------

_Board.PERIPHERALS = frozenset()
_Peripherals.battery = staticmethod(lambda: None)
for name, words in (("steps", "accelerometer"), ("battery", "battery"), ("lora", "LoRa")):
    open_app(name, shot=False)
    check(any(words in t for t in texts()), "%s says the board has no %s: %r" % (name, words, texts()))

if la.scope is not None:
    la.scope.stop_timers()
print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
