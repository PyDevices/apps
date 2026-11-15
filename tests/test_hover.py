# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hover styles in the shared theme, drawn by real LVGL on a headless display.

A control under a released pointer must differ in the frame buffer from the
same control with the pointer elsewhere, for each kind of control the theme
styles; a control the theme doesn't style must not change.
"""

import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "lib"))

try:
    import lvgl as lv

    import _headless
except ImportError:  # pragma: no cover
    lv = None

W, H = 320, 240


@unittest.skipIf(lv is None, "lvgl is not installed")
class HoverStylesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = _headless.display(W, H)
        # By path: appkit's package pulls in pydevices, which this test doesn't need.
        spec = importlib.util.spec_from_file_location(
            "hover", os.path.join(ROOT, "lib", "appkit", "hover.py")
        )
        hover = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hover)
        hover._applied[:] = []
        hover.apply()
        cls.hover = hover

    def setUp(self):
        self.screen = lv.screen_active()
        self.screen.clean()

    def shot(self):
        _headless.advance(60)
        _headless.refresh()
        return bytes(self.frame)

    def differs_when_hovered(self, widget):
        widget.center()
        before = self.shot()
        widget.add_state(lv.STATE.HOVERED)
        hovered = self.shot()
        widget.remove_state(lv.STATE.HOVERED)
        after = self.shot()
        self.assertEqual(before, after)
        return before != hovered

    def test_a_button_shows_hover(self):
        b = lv.button(self.screen)
        b.set_size(120, 50)
        self.assertTrue(self.differs_when_hovered(b))

    def test_a_list_row_shows_hover(self):
        row = lv.list(self.screen)
        row.set_size(200, 120)
        btn = row.add_button(None, "one")
        btn.add_state(lv.STATE.HOVERED)
        hovered = self.shot()
        btn.remove_state(lv.STATE.HOVERED)
        self.assertTrue(hovered != self.shot())

    def test_a_tab_shows_hover(self):
        tv = lv.tabview(self.screen)
        tv.add_tab("A")
        tv.add_tab("B")
        tab = tv.get_tab_bar().get_child(1)
        before = self.shot()
        tab.add_state(lv.STATE.HOVERED)
        self.assertTrue(before != self.shot())

    def test_a_slider_knob_shows_hover(self):
        s = lv.slider(self.screen)
        s.set_width(200)
        self.assertTrue(self.differs_when_hovered(s))

    def test_a_switch_shows_hover(self):
        self.assertTrue(self.differs_when_hovered(lv.switch(self.screen)))

    def test_a_label_does_not_change(self):
        label = lv.label(self.screen)
        label.set_text("plain")
        self.assertFalse(self.differs_when_hovered(label))

    def test_applying_twice_adds_one_layer(self):
        theme = lv.display_get_default().get_theme()
        self.hover.apply()
        self.assertEqual(lv.display_get_default().get_theme().apply_cb is None, theme.apply_cb is None)
        self.assertEqual(len(self.hover._applied), 1)


if __name__ == "__main__":
    unittest.main()
