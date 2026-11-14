# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bit World's tests: the partial repaint matches a full redraw, and the exit button quits cleanly.

Run them from the app's folder, on a CPython with pygraphics, audiodsp and
pydevices' ``lib`` importable (``PYDEVICES_LIB`` names a checkout's)::

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(TESTS)
sys.path[:0] = [TESTS]

import repaint_check  # noqa: E402

#: Runs the app the way a launcher does, presses the exit button after a second,
#: and prints what it saw once ``App.run`` returns.
DRIVER = """
import sys
sys.path.insert(0, %r)
import bit_world as bw, multimer
frames = [0]
step = bw.director.step
def counted(t=None):
    frames[0] += 1
    step(t)
bw.frame_timer.deinit()
multimer.every(bw.FRAME_MS, counted)
closed = []
close = bw.director.sound.close
bw.director.sound.close = lambda: (closed.append(1), close())
ex, ey, ew, eh = bw.director.rect_exit
multimer.after(1000, lambda t=None: bw.director.on_pointer_down(ex + ew // 2, ey + eh // 2))
bw.app.run()
print("RESULT", frames[0], bw.app.quit_requested, len(closed))
"""


class RepaintTest(unittest.TestCase):
    def test_small_panel(self):
        self.assertEqual(repaint_check.check(480, 320, 120, report=lambda line: None), 0)

    def test_800x480(self):
        self.assertEqual(repaint_check.check(800, 480, 60, report=lambda line: None), 0)


class ExitTest(unittest.TestCase):
    def test_exit_button_quits_and_closes_the_audio(self):
        env = dict(os.environ)
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("SDL_AUDIODRIVER", "dummy")
        env.update(PYDEVICES_WIDTH="800", PYDEVICES_HEIGHT="480", PYDEVICES_SCALE="1")
        lib = os.environ.get("PYDEVICES_LIB")
        if lib:
            env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
        out = subprocess.run([sys.executable, "-c", DRIVER % APP], env=env, capture_output=True, text=True, timeout=120)
        lines = [line for line in out.stdout.splitlines() if line.startswith("RESULT")]
        self.assertTrue(lines, out.stdout + out.stderr)
        _, frames, quit_requested, closed = lines[-1].split()
        self.assertGreater(int(frames), 5, "it drew frames before the exit")
        self.assertEqual(quit_requested, "True", "the exit button quit the App")
        self.assertEqual(closed, "1", "quitting closed the audio once")
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
