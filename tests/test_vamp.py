# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Vamp's engine check (``vamp_check.py``), its link contract
(``vamp_link_contract.py``) and its front panel's contract
(``vamp_panel_contract.py``) on CPython and unix MicroPython, then once per
planted fault, on a bank ``vamp_bank.py`` writes.

    python -m unittest discover -s tests

The interpreters and the audio libraries are found as ``test_engine.py`` finds
them. hmilink comes from ``$HMILINK_PATH`` (the folder holding the
``hmilink`` package), else an omnipython checkout beside this one
(``omnipython/packages/hmilink``), else Ostinato's ``vendor/lib``. Whatever is missing
is skipped, loudly; with ``VAMP_REQUIRE=1`` set, as CI sets it, a missing
piece fails instead.

The front panel's screen needs LVGL. CPython must have it (omnipython-lvgl); a
MicroPython without it runs the panel's checks with no screen and says so.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
LIB = str(ROOT / "lib")
APPS = str(ROOT / "programs")  # programs/vamp is the package itself
sys.path.insert(0, str(TESTS))

from test_engine import _find, audio_libs  # noqa: E402

ENGINE_PLANTS = ("nodelay", "nocancel", "nomute", "norack", "nolive", "nochoke", "norecord")
LINK_PLANTS = ("nomute", "norecord")
PANEL_PLANTS = ("nohead", "noedit", "noecho")


def _hmilink():
    explicit = os.environ.get("HMILINK_PATH")
    candidates = [Path(explicit)] if explicit else []
    for parent in TESTS.parents:
        candidates.append(parent / "omnipython" / "packages" / "hmilink")
        candidates.append(parent / "omnipython" / "hmilink")
    candidates.append(ROOT / "programs" / "ostinato" / "vendor" / "lib")
    for c in candidates:
        if (c / "hmilink" / "__init__.py").is_file():
            return str(c)
    return None


def _with_audio_path(env):
    env["PYTHONPATH"] = os.pathsep.join(audio_libs() + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def _cpython_has_audio():
    r = subprocess.run([sys.executable, "-c", "import audioinstruments, audioeffects, audiomixer"],
                       capture_output=True, env=_with_audio_path(dict(os.environ)))
    return r.returncode == 0


def _skip(test, message):
    if os.environ.get("VAMP_REQUIRE"):
        test.fail(message)
    sys.stderr.write("\n*** " + message + " ***\n")
    test.skipTest(message)


class Vamp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bank = None
        cls.why = None
        if not _cpython_has_audio():
            cls.why = "this Python has no audioinstruments: Vamp's checks did NOT run"
            return
        r = subprocess.run([sys.executable, str(TESTS / "vamp_bank.py"), os.path.join(cls.tmp.name, "vamp.sf2")],
                           capture_output=True, text=True, timeout=120, env=_with_audio_path(dict(os.environ)))
        if r.returncode:
            cls.why = "no check bank: " + (r.stdout + r.stderr).strip().splitlines()[-1]
            return
        cls.bank = r.stdout.strip()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _cmd(self, kind, script):
        if self.bank is None:
            _skip(self, self.why)
        hm = _hmilink()
        if hm is None and ("link" in script or "panel" in script):
            _skip(self, "no hmilink: %s did NOT run" % script)
        path = [LIB, APPS, str(TESTS)] + ([hm] if hm else [])
        env = dict(os.environ)
        if kind == "cpython":
            env["PYTHONPATH"] = os.pathsep.join(path + audio_libs() + [env.get("PYTHONPATH", "")])
            return [sys.executable, str(TESTS / script), self.bank], env
        exe = _find("OMNIPYTHON_MICROPYTHON", "micropython")
        if exe is None:
            _skip(self, "no micropython: Vamp's %s did NOT run on it" % script)
        env["MICROPYPATH"] = ":".join(path + audio_libs() + [".frozen"])
        return [exe, "-X", "heapsize=64M", str(TESTS / script), self.bank], env

    def _run(self, kind, script, plant=None):
        cmd, env = self._cmd(kind, script)
        if kind == "cpython" and "panel" in script:
            cmd.append("--need-screen")
        if plant:
            cmd += ["--plant", plant]
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)

    def _passes(self, kind, script):
        r = self._run(kind, script)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all passed", r.stdout)
        self.assertNotIn("FAIL ", r.stdout)

    def _plants(self, kind, script, plants):
        for plant in plants:
            with self.subTest(plant=plant):
                r = self._run(kind, script, plant)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("FAIL ", r.stdout, r.stdout + r.stderr)
                self.assertIn("(plant: %s)" % plant, r.stdout, r.stdout + r.stderr)

    def test_engine_cpython(self):
        self._passes("cpython", "vamp_check.py")

    def test_engine_micropython(self):
        self._passes("micropython", "vamp_check.py")

    def test_engine_plants_cpython(self):
        self._plants("cpython", "vamp_check.py", ENGINE_PLANTS)

    def test_engine_plants_micropython(self):
        self._plants("micropython", "vamp_check.py", ENGINE_PLANTS)

    def test_link_cpython(self):
        self._passes("cpython", "vamp_link_contract.py")

    def test_link_micropython(self):
        self._passes("micropython", "vamp_link_contract.py")

    def test_link_plants_cpython(self):
        self._plants("cpython", "vamp_link_contract.py", LINK_PLANTS)

    def test_link_plants_micropython(self):
        self._plants("micropython", "vamp_link_contract.py", LINK_PLANTS)

    def test_panel_cpython(self):
        self._passes("cpython", "vamp_panel_contract.py")

    def test_panel_micropython(self):
        self._passes("micropython", "vamp_panel_contract.py")

    def test_panel_plants_cpython(self):
        self._plants("cpython", "vamp_panel_contract.py", PANEL_PLANTS)

    def test_panel_plants_micropython(self):
        self._plants("micropython", "vamp_panel_contract.py", PANEL_PLANTS)


class SongSegments(unittest.TestCase):
    """songmodel.model.segments, which Ostinato's engine and Vamp's both play
    from: pattern mode, a pending switch, and song mode looping its scenes."""

    def setUp(self):
        sys.path.insert(0, APPS)
        sys.path.insert(0, LIB)
        from songmodel import model

        self.m = model

    def test_pattern_mode_splits_at_a_switch(self):
        m = self.m
        p = m.new_project()
        t = p["tracks"][0]
        t["patterns"].append(m.pattern(1))
        t["next"] = {"at": m.BAR * 2, "pattern": 1}
        segs = m.segments(p, 0, m.BAR * 4)
        self.assertEqual([(a, b) for a, b, _base, _pats in segs], [(0, m.BAR * 2), (m.BAR * 2, m.BAR * 4)])

    def test_song_mode_walks_and_loops(self):
        m = self.m
        p = m.new_project()
        tid = str(p["tracks"][0]["id"])
        p["song_mode"] = True
        p["song"] = [{"patterns": {tid: 0}, "repeat": 1}, {"patterns": {tid: -1}, "repeat": 2}]
        segs = m.segments(p, 0, m.BAR * 6)
        self.assertEqual([(a, b, base) for a, b, base, _p in segs],
                         [(0, m.BAR, 0), (m.BAR, m.BAR * 3, m.BAR), (m.BAR * 3, m.BAR * 4, m.BAR * 3),
                          (m.BAR * 4, m.BAR * 6, m.BAR * 4)])
        p["loop_scene"] = 1
        self.assertEqual(m.segments(p, 0, m.BAR)[0][3][int(tid)], -1)


class PanelPlayhead(unittest.TestCase):
    """vamp.panel.playing_at: which pattern a track is in at the box's tick,
    and how far into it, so a panel can light the right step."""

    @classmethod
    def setUpClass(cls):
        hm = _hmilink()
        if hm is None:
            raise unittest.SkipTest("no hmilink: the panel's playhead checks did NOT run")
        for p in (hm, APPS, LIB):
            if p not in sys.path:
                sys.path.insert(0, p)
        from songmodel import model
        from vamp import panel

        cls.m = model
        cls.panel = panel

    def test_pattern_mode_wraps_and_switches(self):
        m, at = self.m, self.panel.playing_at
        p = m.new_project()
        t = p["tracks"][0]
        t["patterns"] = [m.pattern(2), m.pattern(1)]
        self.assertEqual(at(p, t, m.BAR * 2 + m.STEP * 3), (0, m.STEP * 3))
        self.assertEqual(at(p, t, m.BAR * 3 + m.STEP), (0, m.BAR + m.STEP))
        t["next"] = {"at": m.BAR * 4, "pattern": 1}
        self.assertEqual(at(p, t, m.BAR * 3), (0, m.BAR))
        self.assertEqual(at(p, t, m.BAR * 5 + m.STEP), (1, m.STEP))

    def test_song_mode_counts_from_the_scene(self):
        m, at = self.m, self.panel.playing_at
        p = m.new_project()
        t = p["tracks"][0]
        t["patterns"] = [m.pattern(1), m.pattern(2)]
        tid = str(t["id"])
        p["song_mode"] = True
        p["song"] = [{"patterns": {tid: 0}, "repeat": 1}, {"patterns": {tid: 1}, "repeat": 1},
                     {"patterns": {tid: -1}, "repeat": 1}]
        self.assertEqual(at(p, t, m.STEP * 5), (0, m.STEP * 5))
        self.assertEqual(at(p, t, m.BAR + m.BAR + m.STEP), (1, m.BAR + m.STEP))
        self.assertEqual(at(p, t, m.BAR * 3 + m.STEP), (-1, 0))
        self.assertEqual(at(p, t, m.BAR * 4 + m.STEP * 2), (0, m.STEP * 2))

    def test_cells_mark_starts_and_held_steps(self):
        m, panel = self.m, self.panel

        class Joined:
            closed = False
            doc = m.new_project()

        front = panel.Front(None)
        front.panel = Joined()
        front.selected = 1
        notes = front.doc["tracks"][1]["patterns"][0]["notes"]
        notes.append([m.STEP * 2, m.STEP * 3, 50, 100])
        notes.append([m.STEP * 3, m.STEP, 50, 100])
        notes.append([0, m.STEP, 72, 100])
        row = (front.low + panel.OCTAVE - 1 - 50) * panel.STEPS
        self.assertEqual(list(front.cells()[row:row + 6]), [0, 0, panel.START, panel.START, panel.HELD, 0])
        self.assertEqual(sum(front.cells()), 2 * panel.START + panel.HELD)


if __name__ == "__main__":
    unittest.main()
