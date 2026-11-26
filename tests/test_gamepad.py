# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The Gamepad app: the report the pad sends, the tester's reading, and both
on the screen, at 800 x 480 and at 480 x 320, with no text cut off or drawn
over.

    python -m unittest tests.test_gamepad

The screen checks run `gamepad_contract.py` in a fresh interpreter, against
omnipython's ``usb-hid`` and ``usb-host-hid`` from ``$OMNIPYTHON_DIR`` (or a
``omnipython`` checkout beside this one) and LVGL for CPython. Without them
they skip, unless ``GAMEPAD_REQUIRE=1`` says they must run.
"""

import importlib.util
import os
import struct
import subprocess
import sys
import types
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)


def _load(name):
    # The app's two logic modules on their own: the package's __init__ needs LVGL.
    path = os.path.join(ROOT, "apps", "gamepad", name + ".py")
    spec = importlib.util.spec_from_file_location("gamepad_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


padmod = _load("pad")
Pad, Sender, hat_at, stick_at = padmod.Pad, padmod.Sender, padmod.hat_at, padmod.stick_at
_watch = _load("watch")
LOOK_MS, Watch = _watch.LOOK_MS, _watch.Watch


class HatTest(unittest.TestCase):
    def test_each_eighth_of_the_d_pad_is_its_direction(self):
        # Clockwise from north, as the HID hat counts.
        points = [(0, -50), (40, -40), (50, 0), (40, 40), (0, 50), (-40, 40), (-50, 0), (-40, -40)]
        self.assertEqual([hat_at(x, y, 100) for x, y in points], list(range(8)))

    def test_the_middle_is_no_direction(self):
        self.assertIsNone(hat_at(0, 0, 100))
        self.assertIsNone(hat_at(20, -20, 100))
        self.assertEqual(hat_at(0, -31, 100), 0)

    def test_a_touch_just_either_side_of_a_boundary(self):
        # North and north-east meet at 22.5 degrees.
        self.assertEqual(hat_at(37, -100, 100), 0)
        self.assertEqual(hat_at(45, -100, 100), 1)


class StickTest(unittest.TestCase):
    def test_the_rim_is_full_scale(self):
        self.assertEqual(stick_at(100, 0, 100), (127, 0))
        self.assertEqual(stick_at(0, -100, 100), (0, -127))
        self.assertEqual(stick_at(0, 0, 100), (0, 0))

    def test_past_the_rim_stays_on_it(self):
        x, y = stick_at(300, 300, 100)
        self.assertEqual((x, y), (90, 90))
        self.assertEqual(stick_at(-500, 0, 100), (-127, 0))


class PadTest(unittest.TestCase):
    def test_the_report_is_usb_hids_gamepad_report(self):
        p = Pad()
        self.assertEqual(p.report(), bytes(7))
        p.press(padmod.A)
        p.press(16)
        p.hat = 0
        p.x, p.y = -127, 64
        self.assertEqual(p.report(), struct.pack("<HBbbbb", 0x8001, 1, -127, 64, 0, 0))
        p.hat = 7
        self.assertEqual(p.report()[2], 8)
        p.release(padmod.A)
        self.assertEqual(p.report()[:2], b"\x00\x80")

    def test_the_named_buttons_are_distinct_and_in_range(self):
        names = (padmod.A, padmod.B, padmod.X, padmod.Y, padmod.L, padmod.R, padmod.SELECT, padmod.START)
        self.assertEqual(len(set(names)), 8)
        self.assertTrue(all(1 <= n <= 16 for n in names))


class _Device:
    def __init__(self):
        self.connected = False
        self.reports = []

    def send_report(self, report):
        if not self.connected:
            raise OSError("USB HID is not connected to a host")
        self.reports.append(bytes(report))


class SenderTest(unittest.TestCase):
    def test_only_a_change_is_sent(self):
        dev = _Device()
        dev.connected = True
        p = Pad()
        s = Sender(p, dev)
        self.assertTrue(s.send())
        self.assertFalse(s.send())
        p.press(1)
        self.assertTrue(s.send())
        self.assertEqual(len(dev.reports), 2)
        self.assertEqual(s.count, 2)

    def test_a_report_without_a_host_goes_once_one_arrives(self):
        dev = _Device()
        p = Pad()
        s = Sender(p, dev)
        p.press(3)
        self.assertFalse(s.send())
        self.assertIn("not connected", s.error)
        dev.connected = True
        self.assertTrue(s.send())
        self.assertIsNone(s.error)
        self.assertEqual(dev.reports, [p.report()])


# A stand-in for usb.host.hid_generic: a pad that plays back events.
class _USBError(OSError):
    pass


class _HidPad:
    def __init__(self, dev):
        self.dev = dev
        self.fields = [[0, 0, 0, 1, 0, 1, n, 0] for n in (1, 2, 3)]
        self.fields += [[1, 0, 8, 8, -127, 127, 0x010030, None], [1, 0, 16, 8, -127, 127, 0x010031, None]]
        self.fields.append([2, 0, 24, 4, 1, 8, 0x010039, None, 0])
        self.axes = {}
        self.closed = False

    @staticmethod
    def match(dev):
        return True

    def read(self, timeout=1):
        if self.dev.gone:
            raise _USBError(19, "gone")
        if not self.dev.events:
            return None
        ev = self.dev.events.pop(0)
        if ev[0] == 8:
            self.axes[ev[1]] = ev[2]
        return ev

    def scaled(self, usage):
        return self.axes[usage] / 127

    def close(self):
        self.closed = True


_hid = types.SimpleNamespace(Gamepad=_HidPad, BUTTON_DOWN=6, BUTTON_UP=7, AXIS=8, HAT=9)


class _Dev:
    idVendor, idProduct = 0x046D, 0xC216
    manufacturer, product = "Logitech", "Dual Action"

    def __init__(self):
        self.events = []
        self.gone = False


class _Core:
    USBError = _USBError

    def __init__(self):
        self.dev = None
        self.finds = 0

    def find(self, custom_match=None):
        self.finds += 1
        return self.dev


def _since(now, then):
    return now - then


class WatchTest(unittest.TestCase):
    def test_it_looks_once_a_second_until_a_pad_is_there(self):
        core = _Core()
        w = Watch(core, _hid)
        self.assertFalse(w.poll(0, _since))
        self.assertFalse(w.poll(LOOK_MS - 1, _since))
        self.assertEqual(core.finds, 1)
        core.dev = _Dev()
        self.assertTrue(w.poll(LOOK_MS, _since))
        self.assertEqual(w.name, "Logitech Dual Action")
        self.assertEqual(w.layout, ((1, 2, 3), (0x010030, 0x010031), 1, ()))

    def test_events_become_what_is_held(self):
        core = _Core()
        core.dev = _Dev()
        w = Watch(core, _hid)
        w.poll(0, _since)
        core.dev.events = [(6, 1, 0), (6, 3, 0), (8, 0x010030, 127), (9, 0, 2), (7, 1, 0)]
        self.assertTrue(w.poll(10, _since))
        self.assertEqual(w.buttons, {3})
        self.assertEqual(w.axes, {0x010030: 1.0})
        self.assertEqual(w.hats, {0: 2})
        self.assertEqual(w.events, 5)
        self.assertFalse(w.poll(20, _since))

    def test_unplugging_drops_the_pad_and_looks_again(self):
        core = _Core()
        core.dev = _Dev()
        w = Watch(core, _hid)
        w.poll(0, _since)
        pad = w.pad
        core.dev.events = [(6, 2, 0)]
        w.poll(10, _since)
        core.dev.gone = True
        self.assertTrue(w.poll(20, _since))
        self.assertTrue(pad.closed)
        self.assertIsNone(w.pad)
        self.assertIsNone(w.layout)
        self.assertEqual(w.buttons, set())
        self.assertIn("went", w.status)
        core.dev = _Dev()
        self.assertFalse(w.poll(20 + LOOK_MS - 1, _since))
        self.assertTrue(w.poll(20 + LOOK_MS, _since))


class _ExtrasPad(_HidPad):
    """A pad whose reports also carry vendor values, as a PS3-layout pad's do."""

    def __init__(self, dev):
        super().__init__(dev)
        self.extra_info = [(0xFF00002A, 0, 255), (0xFF00002C, 0, 1023)]
        self.extras = [None, None]
        self.reports = 0

    def read(self, timeout=1):
        # Each queued entry is a report: its events, then its extras.
        if not self.dev.events:
            return None
        if self.queue:
            return self.queue.pop(0)
        events, extras = self.dev.events.pop(0)
        self.reports += 1
        self.extras = list(extras)
        self.queue = list(events)
        return self.queue.pop(0) if self.queue else None

    queue = []


class ExtrasTest(unittest.TestCase):
    def setUp(self):
        self.core = _Core()
        self.core.dev = _Dev()
        self.hid = types.SimpleNamespace(Gamepad=_ExtrasPad, BUTTON_DOWN=6, BUTTON_UP=7, AXIS=8, HAT=9)

    def test_the_layout_names_each_extra_and_its_range(self):
        w = Watch(self.core, self.hid)
        w.poll(0, _since)
        self.assertEqual(w.layout[3], ((0xFF00002A, 0, 255), (0xFF00002C, 0, 1023)))

    def test_a_report_that_only_moves_extras_is_a_change(self):
        w = Watch(self.core, self.hid)
        w.poll(0, _since)
        self.core.dev.events = [([], [0, 514]), ([], [0, 520])]
        self.assertTrue(w.poll(10, _since))
        self.assertEqual(w.extras, [0, 520])
        self.assertEqual(w.events, 0)
        self.assertFalse(w.poll(20, _since))

    def test_events_and_extras_come_together(self):
        w = Watch(self.core, self.hid)
        w.poll(0, _since)
        self.core.dev.events = [([(6, 8, 0)], [200, 514])]
        self.assertTrue(w.poll(10, _since))
        self.assertEqual(w.buttons, {8})
        self.assertEqual(w.extras, [200, 514])


PageWatch = _watch.PageWatch


def _standard(buttons=(), axes=(0.0, 0.0, 0.0, 0.0)):
    """A standard-layout pad's 17 buttons, *buttons* (counted from 1) held."""
    return [1.0 if n in buttons else 0.0 for n in range(1, 18)], list(axes)


class PageWatchTest(unittest.TestCase):
    def _watch(self, pads, chosen=()):
        return PageWatch(pads=lambda: pads, chosen=lambda: list(chosen))

    def test_the_first_pad_until_one_is_chosen(self):
        buttons, axes = _standard((1, 6), (0.5, -1.0, 0.0, 0.25))
        pads = [(0, "Xbox Controller", "standard", buttons, axes), (1, "8BitDo", "standard", *_standard())]
        w = self._watch(pads)
        self.assertTrue(w.poll())
        self.assertEqual(w.name, "Xbox Controller")
        self.assertEqual(w.buttons, {1, 6})
        self.assertEqual(w.axes[0x010030], 0.5)
        self.assertEqual(w.axes[0x010035], 0.25)
        self.assertEqual(w.pad.axes[0x010031], -32767)
        numbers, codes, hats, extras = w.layout
        self.assertEqual((len(numbers), codes, hats), (13, (0x010030, 0x010031, 0x010032, 0x010035), 1))
        self.assertFalse(w.poll(), "nothing moved")

    def test_the_pad_chosen_in_connections(self):
        pads = [(0, "Pad", "standard", *_standard()), (1, "Pad", "standard", *_standard((2,)))]
        w = self._watch(pads, chosen=["Pad #2"])
        w.poll()
        self.assertEqual(w.buttons, {2})

    def test_the_d_pad_is_a_hat(self):
        pads = [(0, "Pad", "standard", *_standard((13, 16)))]
        w = self._watch(pads)
        w.poll()
        self.assertEqual((w.hats[0], w.buttons), (1, set()))

    def test_a_pad_that_goes_is_looked_for_again(self):
        pads = [(0, "Pad", "standard", *_standard())]
        w = self._watch(pads)
        w.poll()
        del pads[:]
        self.assertTrue(w.poll())
        self.assertIsNone(w.layout)
        self.assertIn("went", w.status)

    def test_a_chosen_pad_not_shown_isnt_another(self):
        pads = [(0, "8BitDo", "standard", *_standard())]
        w = self._watch(pads, chosen=["Xbox Controller"])
        self.assertFalse(w.poll())
        self.assertIsNone(w.pad)

    def test_a_browser_without_the_api_says_so(self):
        w = PageWatch(pads=lambda: None, chosen=lambda: [])
        self.assertTrue(w.poll())
        self.assertEqual(w.status, _watch.NO_GAMEPAD_API)

    def test_the_browser_list_is_read(self):
        text = "0\tXbox Controller\tstandard\t1.00,0.00\t0.500,-1.000"
        self.assertEqual(_watch.page_pads(lambda: text), [(0, "Xbox Controller", "standard", [1.0, 0.0], [0.5, -1.0])])
        self.assertEqual(_watch.page_pads(lambda: ""), [])
        self.assertIsNone(_watch.page_pads(lambda: None))


def _omnipython():
    return os.getenv("OMNIPYTHON_DIR") or os.path.join(ROOT, "..", "omnipython")


class ScreenTest(unittest.TestCase):
    def test_both_sides_on_the_screen(self):
        required = os.getenv("GAMEPAD_REQUIRE") == "1"
        try:
            import lvgl  # noqa: F401
        except ImportError:
            if required:
                raise
            self.skipTest("LVGL for CPython isn't installed")
        # The bench's 800 x 480 panels, and the smallest screen the app is for.
        for screen in ("800x480", "480x320"):
            with self.subTest(screen=screen):
                env = dict(os.environ, OMNIPYTHON_DIR=_omnipython(), GAMEPAD_SCREEN=screen)
                r = subprocess.run(
                    [sys.executable, os.path.join(TESTS, "gamepad_contract.py")],
                    capture_output=True, text=True, timeout=120, env=env,
                )
                if r.returncode == 2 and not required:
                    self.skipTest(r.stdout.strip())
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
