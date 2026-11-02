# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Synth Station's tests: the MIDI parser here, the whole app in station_check.py.

station_check.py runs on CPython and on unix MicroPython (from
``PYDEVICES_MICROPYTHON``, ``micropython`` on PATH, or a ``bin/micropython``
in a folder above this one, with LVGL and audiodsp). Both need
audioinstruments with its ``panel_view`` module, and controlkit, on the path:
``SYNTHSTATION_PATH`` adds folders in front (``:``-separated), for a
checkout of either. With no MicroPython its half is skipped loudly;
``PYDEVICES_REQUIRE_MICROPYTHON=1`` makes that a failure.
"""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest

TESTS = Path(__file__).resolve().parent
LIB = TESTS.parents[1]  # the apps folder, which holds the synthstation package
#: A pydevices checkout: its lib/ (audiodev) and packages/midiports. From the anchor, next to this repo.
PYDEVICES = Path(os.environ.get("PYDEVICES_DIR", TESTS.parents[2].parent / "pydevices"))
CHECK = TESTS / "station_check.py"
EXTRA = [p for p in os.environ.get("SYNTHSTATION_PATH", "").split(":") if p]
PATH = EXTRA + [str(LIB), str(PYDEVICES / "packages" / "midiports")]
#: pydevices' own lib (audiodev): after the frozen copy on MicroPython.
REPO_LIB = str(PYDEVICES / "lib")

sys.path[:0] = [str(LIB)]

from synthstation.midi import Parser  # noqa: E402


def _micropython():
    explicit = os.environ.get("PYDEVICES_MICROPYTHON")
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

    def bend(self, value):
        self.got.append(("bend", value))

    def program(self, number):
        self.got.append(("program", number))


def parse(*chunks):
    sink = Sink()
    parser = Parser(sink)
    for chunk in chunks:
        data = bytearray(chunk)
        parser.feed(data, len(data))
    return sink.got


class MidiParser(unittest.TestCase):
    def test_messages_on_any_channel(self):
        got = parse([0x90, 60, 100, 0x83, 60, 0, 0xB9, 74, 12, 0xE0, 0, 64, 0xC5, 7])
        self.assertEqual(got, [("on", 60, 100, 0), ("off", 60, 3), ("cc", 74, 12, 9), ("bend", 8192), ("program", 7)])

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


class _Station:
    interpreter = None

    def setUp(self):
        if self.interpreter is None:
            message = "no micropython binary: the Synth Station checks did NOT run on MicroPython"
            if os.environ.get("PYDEVICES_REQUIRE_MICROPYTHON") == "1":
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
