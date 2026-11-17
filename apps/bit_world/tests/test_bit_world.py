# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bit World's tests: the partial repaint matches a full redraw, and the exit button quits cleanly.

Run them from the app's folder, on a CPython with pygraphics, audiodsp and
omnipython's ``lib`` importable (``OMNIPYTHON_LIB`` names a checkout's)::

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
%s
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
print("RESULT", frames[0], bw.app.quit_requested, len(closed), bw.WIDTH, bw.HEIGHT)
"""

#: A display that can only swap its width and height, as a panel's framebuffer does.
CANT_ROTATE = "import board_config\ntype(board_config.display_drv).can_rotate = False"


class RepaintTest(unittest.TestCase):
    def test_small_panel(self):
        self.assertEqual(repaint_check.check(480, 320, 120, report=lambda line: None), 0)

    def test_800x480(self):
        self.assertEqual(repaint_check.check(800, 480, 60, report=lambda line: None), 0)


class ColorTest(unittest.TestCase):
    """The colors come from the palettes library and match what the art was drawn with."""

    #: Every named color as RGB565, as the art code first drew them.
    COLORS = {
        "ABYSS": 0x0884,
        "AMBER": 0xe445,
        "AQUA_GLOW": 0x5f7f,
        "BRONZE": 0x61e4,
        "COPPER": 0x9ac5,
        "CORAL": 0xfb0a,
        "CREAM": 0xff9c,
        "CRIMSON": 0xc148,
        "CYAN": 0x25da,
        "DARK_MOSS": 0x0984,
        "DARK_WOOD": 0x20a2,
        "DEEP_SLATE": 0x1949,
        "DEEP_TEAL": 0x09a8,
        "EMERALD": 0x566d,
        "FOREST": 0x1ac7,
        "GOLD": 0xfe08,
        "ICE_CYAN": 0xbfff,
        "LIME_GLOW": 0x9fb0,
        "MAGENTA": 0xba16,
        "MIST": 0x8519,
        "MOSS": 0x3469,
        "NEON_PINK": 0xfb78,
        "NIGHT": 0x10c6,
        "OAK": 0x3923,
        "ORANGE": 0xfc67,
        "PLUM": 0x30a8,
        "SILVER": 0xc6bd,
        "SLATE": 0x2a0d,
        "STEEL": 0x4b32,
        "SUN_YELLOW": 0xff4f,
        "TEAL": 0x1370,
        "VIOLET": 0x6992,
        "VOID": 0x0042,
        "WHITE": 0xffff,
    }

    def test_each_color_keeps_its_value(self):
        import bit_palette

        for name, value in self.COLORS.items():
            self.assertEqual(getattr(bit_palette, name), value, name)

    def test_the_transparent_key_is_never_drawn(self):
        import bit_palette

        # (0, 4, 0) is 0x0020 in RGB565, the key; the next value up stands in for it.
        self.assertEqual(bit_palette.rgb565(0, 4, 0), bit_palette.KEY + 1)
        self.assertNotIn(bit_palette.KEY, [getattr(bit_palette, name) for name in self.COLORS])

    def test_lerp_ends_are_the_colors(self):
        import bit_palette

        self.assertEqual(bit_palette.lerp565(bit_palette.VOID_RGB, bit_palette.SILVER_RGB, 0.0), bit_palette.VOID)
        self.assertEqual(bit_palette.lerp565(bit_palette.VOID_RGB, bit_palette.SILVER_RGB, 1.0), bit_palette.SILVER)


class ExitTest(unittest.TestCase):
    def run_app(self, width, height, prelude=""):
        """Run the app on a desktop display of this size; return frames, quit, closes and its size."""
        env = dict(os.environ)
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("SDL_AUDIODRIVER", "dummy")
        env.update(OMNIPYTHON_WIDTH=str(width), OMNIPYTHON_HEIGHT=str(height), OMNIPYTHON_SCALE="1")
        lib = os.environ.get("OMNIPYTHON_LIB")
        if lib:
            env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
        out = subprocess.run(
            [sys.executable, "-c", DRIVER % (APP, prelude)], env=env, capture_output=True, text=True, timeout=120
        )
        lines = [line for line in out.stdout.splitlines() if line.startswith("RESULT")]
        self.assertTrue(lines, out.stdout + out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        _, frames, quit_requested, closed, w, h = lines[-1].split()
        self.assertGreater(int(frames), 5, "it drew frames before the exit")
        self.assertEqual(quit_requested, "True", "the exit button quit the App")
        self.assertEqual(closed, "1", "quitting closed the audio once")
        return int(w), int(h)

    def test_exit_button_quits_and_closes_the_audio(self):
        self.assertEqual(self.run_app(800, 480), (800, 480))

    def test_a_portrait_display_turns_to_landscape(self):
        self.assertEqual(self.run_app(480, 800), (800, 480))

    def test_a_display_that_cant_rotate_stays_portrait(self):
        self.assertEqual(self.run_app(480, 800, CANT_ROTATE), (480, 800))


if __name__ == "__main__":
    unittest.main()
