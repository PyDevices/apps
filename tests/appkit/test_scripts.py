# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""scan(), script entries and the generated index.

``scripts_contract.py`` holds the in-process checks; this file runs them on
CPython and unix MicroPython, with each planted fault. Then the whole round
trip through real restarts, on the sample app set in ``sample_set/``: the
home screen comes up, the autopilot taps "Blocks" (a plain script), the
program restarts into it, the script plays on its timer and quits, and the
program restarts to the home screen again. On MicroPython that runs under
``python -m appkit.launcher``; on CPython the restarts are ``os.execv``. The
frozen-style run does the same from a folder with no ``apps/`` in it, with
the apps and their generated index on the module path as a frozen build
has them. Last, the index generator itself, and appkit's manifest through
MicroPython's own manifest reader when a MicroPython checkout is found.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _harness import ICONS_LIB, LIB, OMNIPYTHON_LIB, TESTS, ContractCase, need_micropython, run

sys.path.insert(0, str(LIB))
if OMNIPYTHON_LIB is not None:
    sys.path.insert(1, str(OMNIPYTHON_LIB))
if ICONS_LIB is not None:
    sys.path.insert(1, str(ICONS_LIB))
from appkit import index  # noqa: E402  (runs without the rest of appkit)

CONTRACT = "scripts_contract.py"
SET = TESTS / "sample_set"
SUPERVISE = [sys.executable, "-m", "appkit.launcher", "--"]

PLANTS = (
    "script-early",
    "index-ignored",
    "script-as-app",
    "pending-taken",
    "no-close",
    "boot-runs-script",
    "bare-import",
    "parent-kept",
    "init-unmade",
    "init-silent",
)

#: What a good round trip logs, in order.
ROUND_TRIP = [
    "HOME 1 current=home names=blocks,hello,home",
    "LOOP True",
    "TAP Blocks",
    "SCRIPT start",
    "SCRIPT body done",
    "SCRIPT quit after 15 ticks",
    "HOME 2 current=home names=blocks,hello,home",
    "LOOP True",
    "DONE",
]


def _libs():
    """The omnipython and icons source folders, as strings, for a path."""
    return [str(p) for p in (OMNIPYTHON_LIB, ICONS_LIB) if p is not None]


def _board_configs():
    if OMNIPYTHON_LIB is None:
        return None
    path = OMNIPYTHON_LIB.parent / "board_configs" / "desktop"
    return path if path.is_dir() else None


class ScriptsContract(ContractCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        index.write(str(SET / "apps"), self.tmp.name)
        self.env = {"APPKIT_TEST_INDEX": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_cpython(self):
        self.assertPasses(run([sys.executable, CONTRACT], extra_env=self.env))

    def test_micropython(self):
        mp = need_micropython(self)
        self.assertPasses(run([mp, CONTRACT], extra_env=self.env))

    def _plants(self, cmd):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                result = run(cmd + ["--plant=" + plant], extra_env=self.env)
                self.assertIn("PLANTED " + plant, result.stdout, result.stdout + result.stderr)
                self.assertFailsWith(result, "FAIL ")
                self.assertIn(" 1 failed", result.stdout, result.stdout)

    def test_planted_cpython(self):
        self._plants([sys.executable, CONTRACT])

    def test_planted_micropython(self):
        self._plants([need_micropython(self), CONTRACT])


class RoundTrip(ContractCase):
    """Home, a script, the script quits, home again: real restarts."""

    def setUp(self):
        if _board_configs() is None:
            self.skipTest("no omnipython board_configs/desktop: the round trip needs a display")
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, cmd, cwd=SET, extra=None, plant=None):
        env = {"APPKIT_DATA": os.path.join(self.tmp.name, "data")}
        env.update(extra or {})
        if plant:
            env["APPKIT_PLANT"] = plant
        # board_config for the desktop, and the desktop helpers it imports
        # (usdl2 and the rest, in utils/), after omnipython's lib.
        configs = os.pathsep.join((str(OMNIPYTHON_LIB.parent / "utils"), str(_board_configs())))
        # MicroPython takes icons frozen, with its font in flash: not from source.
        omni = str(OMNIPYTHON_LIB) if OMNIPYTHON_LIB is not None else None
        mp_path = os.pathsep.join(p for p in (env.pop("FROZEN", None), str(LIB), omni, configs) if p)
        env["MICROPYPATH"] = mp_path.replace(os.pathsep, ":") + ":.frozen"
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (env.pop("FROZEN_PY", None), str(LIB), *_libs(), configs) if p
        )
        try:
            result = run(cmd, state_dir=self.tmp.name, extra_env=env, cwd=cwd, timeout=90)
        except subprocess.TimeoutExpired as exc:
            result = None
            self.timed_out = exc
        log = os.path.join(self.tmp.name, "log.txt")
        lines = []
        if os.path.exists(log):
            with open(log) as f:
                lines = f.read().splitlines()
            os.remove(log)
        return result, lines

    def assertRoundTrip(self, result, lines):
        self.assertIsNotNone(result, "timed out; the log: %r" % (lines,))
        out = result.stdout + result.stderr
        self.assertEqual(lines, ROUND_TRIP, out)
        self.assertEqual(result.returncode, 0, out)

    def test_micropython_supervised(self):
        mp = need_micropython(self)
        self.assertRoundTrip(*self._run(SUPERVISE + [mp, "main.py"]))

    def test_micropython_supervised_without_the_loop(self):
        # A program that doesn't end in appkit.serve(): the restarts go
        # through the interpreter's exit hook, and the restart file.
        mp = need_micropython(self)
        result, lines = self._run(SUPERVISE + [mp, "main.py"], extra={"APPKIT_NO_LOOP": "1"})
        self.assertEqual(lines.count("NO LOOP"), 3, lines)
        self.assertEqual(lines.count("LOOP False"), 2, lines)
        lines = [line.replace("LOOP False", "LOOP True") for line in lines if line != "NO LOOP"]
        self.assertRoundTrip(result, lines)

    def test_cpython_execv(self):
        self.assertRoundTrip(*self._run([sys.executable, "main.py"]))

    def test_planted_micropython(self):
        mp = need_micropython(self)
        for plant in ("no-pending-check", "script-early", "no-restart-file"):
            with self.subTest(plant=plant):
                result, lines = self._run(SUPERVISE + [mp, "main.py"], plant=plant)
                self.assertIn("PLANTED " + plant, lines[:1], lines)
                trip = [line for line in lines if not line.startswith("PLANTED")]
                self.assertNotEqual(trip, ROUND_TRIP, "a planted fault went unnoticed")
                if plant == "script-early":
                    self.assertNotIn("SCRIPT quit after 15 ticks", lines)

    def _frozen(self, mp):
        """A folder with no apps/, and the apps and index where a frozen build has them."""
        work = os.path.join(self.tmp.name, "board")
        frozen = os.path.join(self.tmp.name, "frozen")
        os.makedirs(work)
        os.makedirs(frozen)
        for name in ("main.py", "autopilot.py"):
            shutil.copy(str(SET / name), work)

        def module(path, base_path="."):
            os.makedirs(os.path.dirname(os.path.join(frozen, path)), exist_ok=True)
            shutil.copy(os.path.join(base_path, path), os.path.join(frozen, path))

        def package(path, base_path="."):
            shutil.copytree(os.path.join(base_path, path), os.path.join(frozen, path))

        index.freeze_apps(str(SET / "apps"), module, package, os.path.join(self.tmp.name, "index"))
        self.assertEqual(sorted(os.listdir(frozen)), ["_appkit_apps.py", "blocks.py", "frozen_apps"])
        self.assertEqual(sorted(os.listdir(os.path.join(frozen, "frozen_apps"))), ["__init__.py", "hello"])
        return work, frozen

    def test_micropython_frozen(self):
        mp = need_micropython(self)
        work, frozen = self._frozen(mp)
        self.assertRoundTrip(*self._run(SUPERVISE + [mp, "main.py"], cwd=work, extra={"FROZEN": frozen}))
        result, lines = self._run(
            SUPERVISE + [mp, "main.py"], cwd=work, extra={"FROZEN": frozen}, plant="index-ignored"
        )
        self.assertIsNotNone(result, "the planted run hung; the log: %r" % (lines,))
        self.assertIn("CRASH OSError: no apps: there is no folder 'apps' and no _appkit_apps module", lines, lines)
        self.assertNotIn("HOME 1 current=home names=blocks,hello,home", lines, "a planted fault went unnoticed")

    def test_cpython_frozen(self):
        work, frozen = self._frozen(None)
        self.assertRoundTrip(*self._run([sys.executable, "main.py"], cwd=work, extra={"FROZEN_PY": frozen}))


class Index(unittest.TestCase):
    def test_collect_and_render(self):
        apps = index.collect(str(SET / "apps"))
        self.assertEqual([entry for entry, info in apps], ["blocks", "hello"])
        ns = {}
        exec(index.render(apps), ns)
        self.assertEqual(ns["APPS"], (("blocks", apps[0][1]), ("hello", apps[1][1])))
        self.assertEqual(ns["APPS"][0][1]["script"], "blocks")

    def test_every_app_here_passes_homes_check(self):
        # Home runs this check at boot and stops on the first app that fails
        # it, so one bad app.json leaves a board with no Home.
        self.assertTrue(index.collect(str(LIB.parent / "apps")))

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "x.py")
            result = subprocess.run(
                [sys.executable, str(LIB / "appkit" / "index.py"), str(SET / "apps"), "-o", out],
                capture_output=True,
                text=True,
                env=dict(os.environ, PYTHONPATH=os.pathsep.join(_libs() + [os.environ.get("PYTHONPATH", "")])),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(out) as f:
                self.assertIn("('hello', {'name': 'hello', 'title': 'Hello', 'icon': 'language'})", f.read())
            result = subprocess.run([sys.executable, str(LIB / "appkit" / "index.py")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("usage", result.stdout)

    def test_missing_icons_says_how_to_get_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            # -S as well: no site-packages, where omnipython-desktop may have put icons.
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(LIB / "appkit" / "index.py"), str(SET / "apps"), "-o", os.path.join(tmp, "x.py")],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pip install omnipython-desktop", result.stderr)
            self.assertIn("packages/icons", result.stderr)

    def test_bad_app_json_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "bad"))
            with open(os.path.join(tmp, "bad", "app.json"), "w") as f:
                f.write("{not json")
            with self.assertRaises(ValueError) as cm:
                index.collect(tmp)
            self.assertIn("bad", str(cm.exception))

    def _one_app(self, tmp, info):
        os.makedirs(os.path.join(tmp, "thing"))
        with open(os.path.join(tmp, "thing", "app.json"), "w") as f:
            json.dump(info, f)

    def test_tile_app_without_an_icon_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one_app(tmp, {"name": "thing", "title": "Thing"})
            with self.assertRaises(ValueError) as cm:
                index.collect(tmp)
            self.assertIn("'thing'", str(cm.exception))
            self.assertIn('no "icon"', str(cm.exception))
            self.assertIn('"tile": false', str(cm.exception))

    def test_unknown_icon_is_refused_and_says_where_the_names_are(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one_app(tmp, {"name": "thing", "title": "Thing", "icon": "no_such_icon"})
            with self.assertRaises(ValueError) as cm:
                index.collect(tmp)
            msg = str(cm.exception)
            self.assertIn("'thing'", msg)
            self.assertIn("'no_such_icon'", msg)
            self.assertIn("icons.names()", msg)

    def test_every_icon_name_is_a_tile_icon(self):
        # icons draws every name at any size, so the 24 px "home" makes a tile too.
        with tempfile.TemporaryDirectory() as tmp:
            self._one_app(tmp, {"name": "thing", "icon": "home"})
            self.assertEqual(index.collect(tmp), [("thing", {"name": "thing", "icon": "home"})])

    def test_app_without_a_tile_needs_no_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one_app(tmp, {"name": "thing", "tile": False})
            self.assertEqual(index.collect(tmp), [("thing", {"name": "thing", "tile": False})])

    def _two_apps(self, tmp):
        """An apps folder: ``stage`` with a song beside it, and ``show``, which draws with stage's code."""
        for name in ("stage", "show", "other"):
            os.makedirs(os.path.join(tmp, name, "tests"))
            with open(os.path.join(tmp, name, "app.json"), "w") as f:
                json.dump({"name": name, "tile": False}, f)
            with open(os.path.join(tmp, name, "__init__.py"), "w") as f:
                f.write("from ..stage import song\n" if name == "show" else "")
            with open(os.path.join(tmp, name, "tests", "test_it.py"), "w") as f:
                f.write("")
        with open(os.path.join(tmp, "stage", "song.py"), "w") as f:
            f.write("")
        with open(os.path.join(tmp, "stage", "main.py"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(tmp, "stage", "songs"))
        with open(os.path.join(tmp, "stage", "songs", "rock.json"), "w") as f:
            f.write('{"name": "Rock"}')
        with open(os.path.join(tmp, "stage", "README.md"), "w") as f:
            f.write("")

    def _freeze_into(self, folder, out, names=None):
        frozen = []

        def module(path, base_path="."):
            frozen.append(path)

        def package(path, base_path="."):
            raise AssertionError("freeze_apps freezes files one by one, not %s" % path)

        index.freeze_apps(folder, module, package, out, names)
        return frozen

    def test_freeze_chosen_apps_brings_the_apps_they_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            apps = os.path.join(tmp, "apps")
            self._two_apps(apps)
            frozen = self._freeze_into(apps, os.path.join(tmp, "out"), "show")
            self.assertEqual(
                sorted(frozen),
                [
                    "_appkit_apps.py",
                    "_appkit_files.py",
                    "frozen_apps/__init__.py",
                    "frozen_apps/show/__init__.py",
                    "frozen_apps/stage/__init__.py",
                    "frozen_apps/stage/song.py",
                ],
            )
            ns = {}
            with open(os.path.join(tmp, "out", "_appkit_apps.py")) as f:
                exec(f.read(), ns)
            self.assertEqual(ns["PACKAGE"], "frozen_apps")
            self.assertEqual([entry for entry, _ in ns["APPS"]], ["show", "stage"])
            with self.assertRaises(ValueError) as cm:
                index.choose(apps, ["nothing"])
            self.assertIn("'nothing'", str(cm.exception))

    def test_script_app_freezes_the_modules_beside_it(self):
        # A script imports its folder's modules by their own names (Bit World's
        # bit_palette), so a freeze puts them at the top level with it, with
        # native taken out where asked; its tests stay out.
        with tempfile.TemporaryDirectory() as tmp:
            apps = os.path.join(tmp, "apps")
            where = os.path.join(apps, "game")
            os.makedirs(os.path.join(where, "tests"))
            with open(os.path.join(where, "app.json"), "w") as f:
                json.dump({"name": "game", "tile": False, "script": "game"}, f)
            with open(os.path.join(where, "game.py"), "w") as f:
                f.write("from game_palette import RED\n")
            with open(os.path.join(where, "game_palette.py"), "w") as f:
                f.write("@micropython.native\ndef red():\n    return 1\nRED = 1\n")
            with open(os.path.join(where, "tests", "test_game.py"), "w") as f:
                f.write("")
            out = os.path.join(tmp, "out")
            frozen = []

            def module(path, base_path="."):
                frozen.append(path)
                with open(os.path.join(base_path, path)) as f:
                    texts[path] = f.read()

            texts = {}
            index.freeze_apps(apps, module, None, out, native=False)
            self.assertIn("game.py", frozen)
            self.assertIn("game_palette.py", frozen)
            self.assertNotIn("test_game.py", [os.path.basename(p) for p in frozen])
            self.assertNotIn("@micropython.native", texts["game_palette.py"])

    def test_frozen_files_read_through_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            apps = os.path.join(tmp, "apps")
            self._two_apps(apps)
            out = os.path.join(tmp, "out")
            self._freeze_into(apps, out)
            ns = {}
            with open(os.path.join(out, "_appkit_files.py")) as f:
                exec(f.read(), ns)
            self.assertEqual(ns["FILES"], {"frozen_apps/stage/songs/rock.json": b'{"name": "Rock"}'})
            from appkit import assets

            saved = assets._files
            assets._files = ns["FILES"]
            try:
                # As a frozen module's __file__ has it, with no such file on disk.
                folder = "frozen_apps/stage/songs"
                self.assertEqual(assets.listdir(folder), ["rock.json"])
                self.assertEqual(assets.listdir("frozen_apps/stage"), ["songs"])
                self.assertEqual(assets.read(folder + "/rock.json"), '{"name": "Rock"}')
                self.assertEqual(assets.read(".frozen/" + folder + "/rock.json", binary=True), b'{"name": "Rock"}')
                with self.assertRaises(OSError):
                    assets.read(folder + "/jazz.json")
                with self.assertRaises(OSError):
                    assets.listdir("not_frozen_apps/stage")
                # On disk, the file on disk.
                self.assertEqual(assets.listdir(os.path.join(apps, "stage", "songs")), ["rock.json"])
            finally:
                assets._files = saved

    def test_manifest_through_micropythons_reader(self):
        # appkit's manifest.py as a firmware build reads it.
        found = None
        for parent in TESTS.parents:
            candidate = parent / "micropython" / "tools" / "manifestfile.py"
            if candidate.is_file():
                found = candidate
                break
        found = os.environ.get("MICROPYTHON_MANIFESTFILE", found)
        if not found:
            self.skipTest("no MicroPython checkout with tools/manifestfile.py")
        with tempfile.TemporaryDirectory() as tmp:
            # An omnipython-lib tree with icons in it, from wherever this process imports icons.
            spec = importlib.util.find_spec("icons")
            if spec is None:
                self.skipTest("no icons package: put omnipython's packages/icons in ICONS_LIB")
            library = os.path.join(tmp, "library")
            os.makedirs(library)
            os.symlink(os.path.dirname(list(spec.submodule_search_locations)[0]), os.path.join(library, "icons"))
            result = self._freeze(found, tmp, library=library)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            listed = result.stdout
            for frozen_as in (
                "_appkit_apps.py",
                "blocks.py",
                "frozen_apps/__init__.py",
                "frozen_apps/hello/__init__.py",
                "appkit/launcher.py",
            ):
                self.assertIn(frozen_as, listed, listed)
            # The firmware brings icons; appkit's manifest doesn't freeze it.
            self.assertNotIn("icons/__init__.py", listed, listed)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "index", "_appkit_apps.py")))

    def _freeze(self, manifestfile, tmp, library=None):
        """appkit's manifest, with *apps* from the sample set, read by MicroPython's own reader in a
        process that has icons on no import path, not even site-packages; *library* is
        ``$OMNIPYTHON_LIBRARY``, an omnipython-lib tree."""
        board = os.path.join(tmp, "manifest.py")
        with open(board, "w") as f:
            f.write(
                "include(%r, apps=%r, index_dir=%r)\n"
                % (str(TESTS.parents[1] / "lib" / "appkit"), str(SET / "apps"), os.path.join(tmp, "index"))
            )
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "OMNIPYTHON_LIBRARY")}
        if library:
            env["OMNIPYTHON_LIBRARY"] = str(library)
        return subprocess.run(
            [sys.executable, "-I", "-S", str(manifestfile), "--freeze", board], capture_output=True, text=True, cwd=tmp, env=env
        )

    def test_manifest_without_icons_says_how_to_fix_it(self):
        found = os.environ.get("MICROPYTHON_MANIFESTFILE")
        for parent in TESTS.parents:
            candidate = parent / "micropython" / "tools" / "manifestfile.py"
            if not found and candidate.is_file():
                found = candidate
        if not found:
            self.skipTest("no MicroPython checkout with tools/manifestfile.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = self._freeze(found, tmp)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("needs the icons package", result.stdout + result.stderr)
            # A library tree whose icons isn't omnipython's.
            fake = os.path.join(tmp, "library", "icons", "icons")
            os.makedirs(fake)
            open(os.path.join(fake, "__init__.py"), "w").close()
            result = self._freeze(found, tmp, library=os.path.join(tmp, "library"))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("isn't omnipython's", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
