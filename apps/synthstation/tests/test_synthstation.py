# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Synth Station's tests: the MIDI parser here, the whole app in station_check.py.

station_check.py runs on CPython and on unix MicroPython (from
``OMNIPYTHON_MICROPYTHON``, ``micropython`` on PATH, or a ``bin/micropython``
in a folder above this one, with LVGL and audiodsp). Both need
audioinstruments with its ``panel_view`` module, and controlkit, on the path:
``SYNTHSTATION_PATH`` adds folders in front (``:``-separated), for a
checkout of either. With no MicroPython its half is skipped loudly;
``OMNIPYTHON_REQUIRE_MICROPYTHON=1`` makes that a failure.
"""

from pathlib import Path
import os
import shutil
import subprocess
import types
import sys
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
LIB = TESTS.parents[1]  # the apps folder, which holds the synthstation package
#: An omnipython checkout: its lib/ (audiodev) and packages/midiports. From the anchor, next to this repo.
PYDEVICES = Path(os.environ.get("OMNIPYTHON_DIR", TESTS.parents[2].parent / "omnipython"))
CHECK = TESTS / "station_check.py"
EXTRA = [p for p in os.environ.get("SYNTHSTATION_PATH", "").split(":") if p]
PATH = EXTRA + [str(LIB), str(PYDEVICES / "packages" / "midiports")]
#: omnipython's own lib (audiodev): after the frozen copy on MicroPython.
REPO_LIB = str(PYDEVICES / "lib")

sys.path[:0] = [str(LIB)]

from synthstation import midi  # noqa: E402
from synthstation.midi import Parser  # noqa: E402


def _micropython():
    explicit = os.environ.get("OMNIPYTHON_MICROPYTHON")
    if explicit:
        return explicit
    found = shutil.which("micropython")
    if found:
        return found
    for parent in TESTS.parents:
        candidate = parent / "bin" / "micropython"
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


class Sink:
    def __init__(self):
        self.got = []

    def note_on(self, note, velocity, channel):
        self.got.append(("on", note, velocity, channel))

    def note_off(self, note, channel):
        self.got.append(("off", note, channel))

    def control(self, controller, value, channel):
        self.got.append(("cc", controller, value, channel))

    def bend(self, value, channel):
        self.got.append(("bend", value, channel))

    def program(self, number, channel):
        self.got.append(("program", number, channel))


def parse(*chunks):
    sink = Sink()
    parser = Parser(sink)
    for chunk in chunks:
        data = bytearray(chunk)
        parser.feed(data, len(data))
    return sink.got


class MidiParser(unittest.TestCase):
    def test_messages_on_any_channel(self):
        got = parse([0x90, 60, 100, 0x83, 60, 0, 0xB9, 74, 12, 0xE2, 0, 64, 0xC5, 7])
        self.assertEqual(
            got, [("on", 60, 100, 0), ("off", 60, 3), ("cc", 74, 12, 9), ("bend", 8192, 2), ("program", 7, 5)])

    def test_running_status_and_velocity_zero(self):
        got = parse([0x90, 60, 100, 62, 90, 60, 0])
        self.assertEqual(got, [("on", 60, 100, 0), ("on", 62, 90, 0), ("off", 60, 0)])

    def test_a_pad_message_carries_its_channel(self):
        self.assertEqual(parse([0x99, 36, 100, 0x89, 36, 0]), [("on", 36, 100, 9), ("off", 36, 9)])

    def test_a_message_split_across_reads(self):
        self.assertEqual(parse([0x90, 60], [100]), [("on", 60, 100, 0)])

    def test_real_time_inside_a_message_and_sysex_are_skipped(self):
        got = parse([0x90, 60, 0xF8, 100, 0xF0, 1, 2, 3, 0xF7, 0xB0, 1, 5])
        self.assertEqual(got, [("on", 60, 100, 0), ("cc", 1, 5, 0)])

    def test_data_after_system_common_is_not_a_note(self):
        self.assertEqual(parse([0x90, 60, 100, 0xF3, 4, 61, 100]), [("on", 60, 100, 0)])


def _run(interpreter, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(TESTS)] + PATH + [REPO_LIB, env.get("PYTHONPATH", "")])
    env["MICROPYPATH"] = ":".join([str(TESTS)] + PATH + [".frozen", REPO_LIB])
    return subprocess.run(
        [interpreter, "-X", "heapsize=256M", str(CHECK)] + list(args) if "micropython" in interpreter
        else [interpreter, str(CHECK)] + list(args),
        cwd=str(TESTS), env=env, capture_output=True, text=True, timeout=1800)


class WebInputs(unittest.TestCase):
    """The browser's branch of Inputs, with webmidi stood in for."""

    def _open(self, names, why=None):
        port = types.SimpleNamespace(names=names, why=why, any=lambda: 3, closed=[])
        port.readinto = mock.Mock(side_effect=[3, None])
        port.close = lambda: port.closed.append(True)
        webmidi = types.SimpleNamespace(page_in=lambda: port)
        package = types.ModuleType("midiports")
        package.webmidi = webmidi
        with mock.patch.object(midi.sys, "platform", "webassembly"), \
                mock.patch.dict(sys.modules, {"midiports": package, "midiports.webmidi": webmidi}):
            return midi.Inputs().open(), port

    def test_a_browser_opens_web_midi_and_polls_it(self):
        inputs, port = self._open(["Keys"])
        self.assertEqual(inputs.kind, "web")
        self.assertIsNone(inputs.why)
        self.assertEqual(inputs.names(), ["Keys"])
        inputs.poll(mock.Mock())
        self.assertEqual(port.readinto.call_count, 2)  # until it's empty
        inputs.close()
        self.assertEqual(port.closed, [True])

    def test_names_stay_empty_until_the_browser_says_yes(self):
        inputs, _ = self._open([])
        self.assertEqual(inputs.kind, "web")
        self.assertEqual(inputs.names(), [])

    def test_no_midiports_is_said_rather_than_raised(self):
        with mock.patch.object(midi.sys, "platform", "webassembly"), \
                mock.patch.dict(sys.modules, {"midiports": None}):
            inputs = midi.Inputs().open()
        self.assertIsNone(inputs.kind)
        self.assertEqual(inputs.why, "midiports isn't installed")


class _FakeBle:
    """``midiports.ble``'s input as Inputs sees it: messages queued, a
    note-off for each held note on close, an error once the queue is read."""

    def __init__(self, name):
        self.name = name
        self.state = "advertising"
        self.queue = []
        self.error = None
        self.closed = False

    def readinto(self, buf):
        if self.queue:
            msg = self.queue.pop(0)
            buf[:len(msg)] = msg
            return len(msg)
        if self.error is not None:
            raise self.error
        return None

    def close(self):
        self.closed = True
        self.state = "closed"
        self.queue.append(b"\x80\x3c\x00")  # the note the test leaves held


class BleInputs(unittest.TestCase):
    """Bluetooth MIDI as one more input, with midiports.ble stood in for."""

    def setUp(self):
        self.opened = []

        def ports(name):
            port = _FakeBle(name)
            self.opened.append(port)
            return port, object()

        self.ble = types.SimpleNamespace(ports=ports)
        package = types.ModuleType("midiports")
        package.ble = self.ble
        patcher = mock.patch.dict(sys.modules, {"midiports": package, "midiports.ble": self.ble})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_off_until_turned_on_and_never_offered_off_a_board(self):
        inputs = midi.Inputs()
        self.assertIsNone(inputs.ble)
        self.assertIsNone(inputs.ble_text())
        self.assertEqual(self.opened, [])
        self.assertFalse(midi.ble_available())  # CPython: a computer's paired devices are its MIDI ports

    def test_on_it_advertises_and_its_notes_reach_the_parser(self):
        inputs = midi.Inputs()
        inputs.set_ble(True)
        port = self.opened[0]
        self.assertEqual(port.name, "Synth Station")
        self.assertEqual(inputs.ble_text(), "Bluetooth: waiting as Synth Station")
        self.assertEqual(inputs.names(), [])
        port.state = "connected"
        self.assertEqual(inputs.names(), ["Bluetooth"])
        port.queue += [b"\x90\x3c\x64", b"\x91\x40\x50"]
        sink = Sink()
        inputs.poll(Parser(sink))
        self.assertEqual(sink.got, [("on", 60, 100, 0), ("on", 64, 80, 1)])

    def test_off_lets_go_of_the_notes_it_left(self):
        inputs = midi.Inputs()
        inputs.set_ble(True)
        sink = Sink()
        inputs.set_ble(False, Parser(sink))
        self.assertTrue(self.opened[0].closed)
        self.assertIsNone(inputs.ble)
        self.assertEqual(sink.got, [("off", 60, 0)])

    def test_a_stopped_link_is_said_after_its_last_notes(self):
        inputs = midi.Inputs()
        inputs.set_ble(True)
        port = self.opened[0]
        port.queue.append(b"\x80\x40\x00")
        port.error = OSError("radio gone")
        sink = Sink()
        inputs.poll(Parser(sink))
        self.assertEqual(sink.got[0], ("off", 64, 0))
        self.assertIsNone(inputs.ble)
        self.assertEqual(inputs.ble_text(), "Bluetooth MIDI stopped: radio gone")

    def test_a_failure_to_start_is_raised_and_kept(self):
        def broken(name):
            raise OSError("no radio")

        self.ble.ports = broken
        inputs = midi.Inputs()
        with self.assertRaises(OSError):
            inputs.set_ble(True)
        self.assertIsNone(inputs.ble)
        self.assertEqual(inputs.ble_text(), "Bluetooth MIDI stopped: no radio")


class _FakePumpOwner:
    """audiodev's pump owner: a status block whose two byte totals swing by a
    block while nothing is missing, as they do on a board."""

    def __init__(self):
        self.words = [0] * 24
        self.words[0] = 1

    def status(self):
        import struct

        return struct.pack("<24Q", *self.words)


class AudioOutCounts(unittest.TestCase):
    """Through audio_out on a board, Synth Station's underruns are the I2S
    driver's count, not the swing between the pump's byte totals."""

    def setUp(self):
        self.starved = 0
        self.owner = _FakePumpOwner()
        bp = types.ModuleType("board_peripherals")
        pumpmod = types.ModuleType("audiopump")
        pumpmod.STATUS_WORDS = 24
        drv = types.ModuleType("_audioif")
        drv.i2s_starved_bytes = lambda: self.starved
        dev = types.ModuleType("audiodev")
        dev.pump = types.SimpleNamespace(owner=lambda: self.owner)
        self.mods = mock.patch.dict(sys.modules, {"board_peripherals": bp, "audiopump": pumpmod,
                                                   "_audioif": drv, "audiodev": dev})
        self.mods.start()
        from synthstation import audio

        self.out = audio.Output(None)
        self.out._out = types.SimpleNamespace(pumped=True)

    def tearDown(self):
        self.mods.stop()

    def step(self, swing):
        w = self.owner.words
        w[0] += 1
        w[1] += 1024
        w[12] += 1000
        w[15] += 1024  # the sink
        w[21] = w[15] + swing  # the DMA, ahead or behind by part of a block
        return self.out.load()

    def test_swing_is_not_an_underrun(self):
        for swing in (0, 176, 700, 1024, 1400, 300, 1700):
            self.step(swing)
        self.assertEqual(self.out.underruns, 0)
        self.assertEqual(self.out.starved_ms(), 0)

    def test_driver_count_is(self):
        self.step(500)
        self.starved = 1920  # 10 ms at 48 kHz stereo
        self.step(500)
        self.step(500)
        self.starved = 0  # the channel reopened and counts again from 0
        self.step(500)
        self.starved = 960
        self.step(500)
        self.assertEqual(self.out.underruns, 2)
        self.assertEqual(self.out.starved_ms(), 15)


class _Station:
    interpreter = None

    def setUp(self):
        if self.interpreter is None:
            message = "no micropython binary: the Synth Station checks did NOT run on MicroPython"
            if os.environ.get("OMNIPYTHON_REQUIRE_MICROPYTHON") == "1":
                self.fail(message)
            sys.stderr.write("\n*** " + message + " ***\n")
            self.skipTest(message)

    def test_every_instrument_opens_plays_and_follows_the_keyboard(self):
        result = _run(self.interpreter)
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("RESULT OK", out)


class CPythonStation(_Station, unittest.TestCase):
    interpreter = sys.executable


class MicroPythonStation(_Station, unittest.TestCase):
    interpreter = _micropython()


if __name__ == "__main__":
    unittest.main()
