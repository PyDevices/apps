# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The MIDI Controller app: the bytes each control sends, mapping edits, the
saved settings, what comes back, the ways out, and every view on the screen
at 800 x 480 and at 480 x 320 with no text cut off or drawn over.

    python -m unittest tests.test_midicontroller

The screen checks run `midicontroller_contract.py` in a fresh interpreter,
against pydevices' ``midiports`` from ``$PYDEVICES_DIR`` (or a ``pydevices``
checkout beside this one) and LVGL for CPython. Without them they skip,
unless ``MIDICONTROLLER_REQUIRE=1`` says they must run.
"""

import importlib.util
import json
import os
import subprocess
import sys
import types
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)


def _load(name):
    # The app's logic modules on their own: the package's __init__ needs LVGL.
    path = os.path.join(ROOT, "apps", "midicontroller", name + ".py")
    spec = importlib.util.spec_from_file_location("midicontroller_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


surface = _load("surface")
links = _load("links")
Surface = surface.Surface


class Out:
    def __init__(self):
        self.sent = []

    def write(self, buf, nbytes):
        self.sent.append(bytes(buf[:nbytes]))
        return nbytes


def _since(a, b):
    return a - b


class SendTest(unittest.TestCase):
    def setUp(self):
        self.out = Out()
        self.s = Surface(out=self.out)

    def test_each_kind_of_control_sends_its_message(self):
        s = self.s
        s.press("pad0", 1.0)
        s.release("pad0")
        s.move("knob4", 100)
        s.move("fader15", 5)
        s.move("x", 127)
        s.press("tr3")
        s.release("tr3")
        s.move("mod", 64)
        self.assertEqual(self.out.sent, [
            bytes([0x90, 36, 127]), bytes([0x80, 36, 0]),
            bytes([0xB0, 74, 100]), bytes([0xB0, 117, 5]), bytes([0xB0, 16, 127]),
            bytes([0xB0, 23, 127]), bytes([0xB0, 23, 0]), bytes([0xB0, 1, 64]),
        ])

    def test_the_channel_setting_moves_everything(self):
        self.s.set("channel", 10)
        self.s.press("pad3")
        self.s.move("knob0", 1)
        self.assertEqual([m[0] for m in self.out.sent], [0x99, 0xB9])

    def test_mixer_strips_play_on_their_own_channels(self):
        self.s.set("channel", 3)
        self.s.move("mix0", 90)
        self.s.move("mix7", 91)
        self.s.press("mute1")
        self.s.press("solo7")
        self.assertEqual(self.out.sent, [bytes([0xB2, 7, 90]), bytes([0xB9, 7, 91]), bytes([0xB3, 14, 127]),
                                         bytes([0xB9, 15, 127])])

    def test_the_strips_wrap_past_channel_16(self):
        self.s.set("channel", 16)
        self.s.move("mix1", 1)
        self.assertEqual(self.out.sent, [bytes([0xB0, 7, 1])])

    def test_a_toggle_flips_and_its_release_sends_nothing(self):
        s = self.s
        s.press("mute2")
        self.assertIsNone(s.release("mute2"))
        s.press("mute2")
        self.assertEqual(self.out.sent, [bytes([0xB2, 14, 127]), bytes([0xB2, 14, 0])])

    def test_velocity_comes_from_the_touch_unless_fixed(self):
        s = self.s
        s.press("pad0", 0.0)
        s.press("pad0", 1.0)
        s.set("velocity", 100)
        s.press("pad0", 0.0)
        self.assertEqual([m[2] for m in self.out.sent], [32, 127, 100])

    def test_banks_move_the_pads_sixteen_notes_at_a_time(self):
        s = self.s
        s.set("bank", 2)
        s.press("pad0")
        self.assertEqual(self.out.sent[-1][1], 68)
        self.assertEqual(s.describe("pad15"), "B5")
        s.remap("pad15", number=120)
        self.assertEqual(s.describe("pad15"), "-")
        self.assertIsNone(s.press("pad15"), "a pad pushed past 127 plays nothing")

    def test_the_keys_follow_the_octave(self):
        s = self.s
        s.key(0, True, 1.0)
        s.set("octave", 2)
        s.key(13, True, 1.0)
        s.key(13, False)
        self.assertEqual(self.out.sent, [bytes([0x90, 60, 127]), bytes([0x90, 49, 127]), bytes([0x80, 49, 0])])

    def test_all_notes_off_on_every_channel_in_use(self):
        self.s.panic()
        self.assertEqual(self.out.sent, [bytes([0xB0 | ch, 123, 0]) for ch in range(8)])

    def test_a_port_that_fails_says_so_and_keeps_going(self):
        class Gone:
            def write(self, buf, n):
                raise OSError("unplugged")

        s = Surface(out=Gone())
        s.press("pad0")
        self.assertEqual(s.error, "unplugged")
        self.assertEqual(s.sent, 0)
        self.assertEqual(s.last, bytes([0x90, 36, 103]))


class MappingTest(unittest.TestCase):
    def test_a_pad_can_become_a_cc_and_a_knob_cannot_become_a_note(self):
        s = Surface(out=Out())
        s.remap("pad0", kind=surface.CC, number=64)
        s.remap("knob0", kind=surface.NOTE, number=200)
        self.assertEqual(s.map["pad0"], ("cc", 64))
        self.assertEqual(s.map["knob0"], ("cc", 127))
        s.press("pad0")
        s.release("pad0")
        self.assertEqual(s.out.sent, [bytes([0xB0, 64, 103]), bytes([0xB0, 64, 0])])

    def test_reset_puts_one_or_all_back(self):
        s = Surface()
        s.remap("pad0", number=1)
        s.remap("pad1", number=2)
        s.reset("pad0")
        self.assertEqual(s.map["pad0"], ("note", 36))
        self.assertEqual(s.map["pad1"], ("note", 2))
        s.reset()
        self.assertEqual(s.map, surface.DEFAULT_MAP)

    def test_the_saved_file_holds_only_what_differs_and_reads_back(self):
        s = Surface()
        self.assertEqual(s.config(), {})
        s.set("channel", 5)
        s.set("output", "pc:Loop")
        s.remap("fader3", number=11)
        saved = json.loads(json.dumps(s.config()))
        self.assertEqual(saved, {"channel": 5, "output": "pc:Loop", "map": {"fader3": ["cc", 11]}})
        again = Surface(saved)
        self.assertEqual(again.settings, s.settings)
        self.assertEqual(again.map, s.map)

    def test_a_bad_file_keeps_the_defaults(self):
        s = Surface({"channel": 99, "velocity": -4, "map": {"pad0": ["sysex", 1], "nope": ["cc", 1],
                                                              "knob1": ["cc", 300], "knob2": "x"}})
        self.assertEqual(s.settings["channel"], 16)
        self.assertEqual(s.settings["velocity"], 0)
        self.assertEqual(s.map, surface.DEFAULT_MAP)


class FeedTest(unittest.TestCase):
    def test_what_comes_in_moves_the_controls_it_matches(self):
        s = Surface()
        moved = s.feed(bytes([0xB0, 74, 99, 0x90, 37, 80, 0x80, 37, 0, 0xB3, 7, 5, 0xB0, 9, 9]))
        self.assertEqual(moved, [("knob4", 99), ("pad1", 80), ("pad1", 0), ("mix3", 5)])
        self.assertEqual(s.values["knob4"], 99)

    def test_a_control_just_moved_by_hand_ignores_its_echo(self):
        s = Surface()
        s.move("knob0", 50, now=1000)
        self.assertEqual(s.feed(bytes([0xB0, 70, 10]), 1000 + surface.HOLD_MS - 1, _since), [])
        self.assertEqual(s.values["knob0"], 50)
        self.assertEqual(s.feed(bytes([0xB0, 70, 10]), 1000 + surface.HOLD_MS, _since), [("knob0", 10)])

    def test_a_remap_is_heard_at_once(self):
        s = Surface()
        s.feed(b"")
        s.remap("knob0", number=20)
        self.assertEqual(s.feed(bytes([0xB0, 20, 1])), [("knob0", 1), ("tr0", 1)])

    def test_running_bytes_and_short_messages_are_stepped_over(self):
        s = Surface()
        self.assertEqual(s.feed(bytes([5, 0xF8, 0xC0, 3, 0xD0, 9, 0xB0, 70, 4, 0xB0, 71])), [("knob0", 4)])


class _Port:
    def __init__(self, info):
        self.info = info
        self.closed = False

    def write(self, buf, nbytes):
        return nbytes

    def readinto(self, buf, nbytes=None):
        return None

    def close(self):
        self.closed = True


class _Desk:
    busy = False

    def available(self):
        P = types.SimpleNamespace
        return [P(name="Synth", direction="out"), P(name="Loop", direction="in"), P(name="Loop", direction="out")]

    def open_port(self, info):
        if self.busy and info.direction == "in":
            raise OSError("in use")
        return _Port(info)


class LinksTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in ("machine", "_usbhost", "bledev", "midiports",
                                                       "midiports.linux", "midiports.windows")}
        self.desk = _Desk()
        midiports = types.ModuleType("midiports")
        midiports.__path__ = []
        midiports.linux = midiports.windows = self.desk
        sys.modules.update({"machine": None, "_usbhost": None, "bledev": None, "midiports": midiports,
                            "midiports.linux": self.desk, "midiports.windows": self.desk})
        self.platform = links.sys.platform
        links.sys = types.SimpleNamespace(platform="linux")

    def tearDown(self):
        links.sys = sys
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_a_computer_offers_its_outputs(self):
        self.assertEqual(links.choices(), [("pc:Synth", "Synth"), ("pc:Loop", "Loop")])

    def test_an_output_opens_with_its_input_for_feedback(self):
        link = links.open_link("pc:Loop")
        self.assertEqual((link.out.info.direction, link.inp.info.direction), ("out", "in"))
        self.assertEqual(link.status(), "Loop")
        link.close()
        self.assertTrue(link.out.closed and link.inp.closed)

    def test_an_input_another_program_holds_still_sends(self):
        self.desk.busy = True
        link = links.open_link("pc:Loop")
        self.assertIsNone(link.inp)
        self.assertEqual(link.read_into(bytearray(8)), 0)

    def test_an_output_that_went_away_says_so(self):
        with self.assertRaises(OSError):
            links.open_link("pc:Gone")
        with self.assertRaises(ValueError):
            links.open_link("serial")

    def test_a_board_with_nothing_offers_nothing(self):
        links.sys = types.SimpleNamespace(platform="rp2")
        self.assertEqual(links.choices(), [])
        self.assertIn("midiports", links.missing())


class BleLinkTest(unittest.TestCase):
    def test_it_advertises_connects_and_advertises_again(self):
        import asyncio

        class Conn:
            up = True

            def is_connected(self):
                return Conn.up

        class Port:
            connection = Conn()
            sent = []

            def write(self, buf, n):
                Port.sent.append(bytes(buf[:n]))

            def readinto(self, buf, n=None):
                return None

            async def close(self):
                pass

        serves = []

        async def serve(ble, name):
            # Advertises until a central connects.
            serves.append(name)
            while not Conn.up:
                await asyncio.sleep(0)
            return Port()

        class Loop:
            """asyncio's sleep_ms and run on CPython, where sleep takes seconds."""

            def __init__(self):
                self.loop = asyncio.new_event_loop()

            def create_task(self, coro):
                return self.loop.create_task(coro)

            async def sleep_ms(self, ms):
                await asyncio.sleep(0)

            def run(self, coro):
                return self.loop.run_until_complete(coro)

        loop = Loop()
        links_yield = links._yield

        async def _yield():
            await asyncio.sleep(0)

        links._yield = _yield
        try:
            link = links.BleLink(types.SimpleNamespace(serve=serve), object(), loop)
            self.assertIn("advertising", link.status())
            link.poll()
            link.poll()
            self.assertEqual(link.status(), "BLE: connected")
            link.write(bytes([0x90, 36, 100]))
            self.assertEqual(Port.sent, [bytes([0x90, 36, 100])])
            Conn.up = False
            for _ in range(4):
                link.poll()
            self.assertIn("disconnected", link.status())
            with self.assertRaises(OSError):
                link.write(bytes([0x90, 36, 100]))
            Conn.up = True
            for _ in range(4):
                link.poll()
            self.assertEqual(len(serves), 2, "it advertised again")
            link.close()
            self.assertTrue(link._task.done())
        finally:
            links._yield = links_yield
            loop.loop.close()


def _pydevices():
    return os.getenv("PYDEVICES_DIR") or os.path.join(ROOT, "..", "pydevices")


class ScreenTest(unittest.TestCase):
    def test_every_view_on_the_screen(self):
        required = os.getenv("MIDICONTROLLER_REQUIRE") == "1"
        try:
            import lvgl  # noqa: F401
        except ImportError:
            if required:
                raise
            self.skipTest("LVGL for CPython isn't installed")
        # The bench's 800 x 480 panels, and the smallest screen the app is for.
        for screen in ("800x480", "480x320"):
            with self.subTest(screen=screen):
                env = dict(os.environ, PYDEVICES_DIR=_pydevices(), MIDICONTROLLER_SCREEN=screen)
                r = subprocess.run(
                    [sys.executable, os.path.join(TESTS, "midicontroller_contract.py")],
                    capture_output=True, text=True, timeout=180, env=env,
                )
                if r.returncode == 2 and not required:
                    self.skipTest(r.stdout.strip())
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
