# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The layout tables: which one a window gets, and that its regions tile the window."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "ui"))

import layout  # noqa: E402

REGIONS = ("top", "tracks", "editor", "inspector", "keys", "status")
SIZES = ((2560, 1440), (1920, 1080), (1680, 1050), (1600, 900), (1440, 900), (1366, 768), (1280, 800), (1280, 720))


def overlap(a, b):
    """The area two (x, y, w, h) rectangles share."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


class LayoutTest(unittest.TestCase):
    def test_the_design_size_keeps_its_table(self):
        self.assertEqual(
            layout.pick(1920, 1080),
            {
                "scale": 1.0,
                "top": (0, 0, 1920, 72),
                "tracks": (0, 72, 300, 828),
                "editor": (300, 72, 1220, 828),
                "inspector": (1520, 72, 400, 828),
                "keys": (0, 900, 1920, 150),
                "status": (0, 1050, 1920, 30),
            },
        )

    def test_1280x720_gets_the_compact_table(self):
        table = layout.pick(1280, 720)
        self.assertEqual(table, layout.compact(1280, 720))
        self.assertEqual(
            table,
            {
                "scale": 1280 / 1920,
                "top": (0, 0, 1280, 48),
                "tracks": (0, 48, 250, 652),
                "editor": (250, 48, 720, 552),
                "inspector": (970, 48, 310, 552),
                "keys": (250, 600, 1030, 100),
                "status": (0, 700, 1280, 20),
            },
        )

    def test_the_compact_table_gives_words_more_room_than_the_scale_would(self):
        compact, scaled = layout.compact(1280, 720), layout.desktop(1280, 720)
        self.assertGreater(compact["tracks"][2], scaled["tracks"][2])
        self.assertGreater(compact["inspector"][2], scaled["inspector"][2])
        self.assertGreater(compact["tracks"][3], scaled["tracks"][3])

    def test_which_table_a_window_gets(self):
        for w, h in SIZES:
            with self.subTest(size=(w, h)):
                small = min(w / 1920, h / 1080) < layout.COMPACT_BELOW
                self.assertEqual(layout.pick(w, h), (layout.compact if small else layout.desktop)(w, h))
        self.assertEqual(layout.pick(1600, 900), layout.compact(1600, 900))
        self.assertEqual(layout.pick(1680, 1050), layout.desktop(1680, 1050))

    def test_the_regions_tile_the_window(self):
        for w, h in SIZES:
            with self.subTest(size=(w, h)):
                table = layout.pick(w, h)
                rects = [table[name] for name in REGIONS]
                for x, y, rw, rh in rects:
                    self.assertTrue(rw > 0 and rh > 0 and x >= 0 and y >= 0 and x + rw <= w and y + rh <= h)
                for i, a in enumerate(rects):
                    for b in rects[i + 1:]:
                        self.assertEqual(overlap(a, b), 0, (a, b))
                self.assertEqual(sum(rw * rh for x, y, rw, rh in rects), w * h)


PHONES = ((844, 390, 1), (390, 844, 1), (2532, 1170, 3), (1170, 2532, 3), (1600, 720, 2), (720, 1600, 2))
PHONE_REGIONS = ("top", "tabs", "status")


class PhoneLayoutTest(unittest.TestCase):
    def test_a_phone_gets_the_phone_table(self):
        for w, h, dpr in PHONES:
            with self.subTest(size=(w, h, dpr)):
                self.assertEqual(layout.pick(w, h, dpr), layout.phone(w, h, dpr))

    def test_a_desktop_window_is_not_a_phone(self):
        for w, h, dpr in ((1280, 720, 1), (1920, 1080, 1.5), (2560, 1440, 2), (1366, 768, 1)):
            with self.subTest(size=(w, h, dpr)):
                self.assertNotIn("pages", layout.pick(w, h, dpr))

    def test_a_phone_is_drawn_at_one_design_pixel_per_css_pixel(self):
        for w, h, dpr in PHONES:
            with self.subTest(size=(w, h, dpr)):
                self.assertEqual(layout.phone(w, h, dpr)["scale"], dpr)

    def test_touch_targets_are_a_fingertip(self):
        for w, h, dpr in PHONES:
            with self.subTest(size=(w, h, dpr)):
                table = layout.phone(w, h, dpr)
                self.assertGreaterEqual(table["touch"], 44 * dpr)
                self.assertGreaterEqual(table["tabs"][3], 44 * dpr)

    def test_every_page_shares_one_rect(self):
        for w, h, dpr in PHONES:
            with self.subTest(size=(w, h, dpr)):
                table = layout.phone(w, h, dpr)
                self.assertEqual(set(table["pages"]), {"editor", "tracks", "inspector", "keys"})
                self.assertEqual({table[name] for name in table["pages"]}, {table["editor"]})

    def test_one_page_and_the_bars_tile_the_window(self):
        for w, h, dpr in PHONES:
            with self.subTest(size=(w, h, dpr)):
                table = layout.phone(w, h, dpr)
                rects = [table[name] for name in PHONE_REGIONS] + [table["editor"]]
                for x, y, rw, rh in rects:
                    self.assertTrue(rw > 0 and rh > 0 and x >= 0 and y >= 0 and x + rw <= w and y + rh <= h)
                for i, a in enumerate(rects):
                    for b in rects[i + 1:]:
                        self.assertEqual(overlap(a, b), 0, (a, b))
                self.assertEqual(sum(rw * rh for x, y, rw, rh in rects), w * h)


if __name__ == "__main__":
    unittest.main()
