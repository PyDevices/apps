# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Touch: tap five targets, and see what the touch mapping gets wrong.

The targets come one at a time, large enough to read at arm's length: the
four corners a tenth of the way in, then the middle. Each tap keeps the point
the board's ``touch_read`` gave and where the touch device's rotation table
put it. After the fifth the app says in plain words what's wrong, if anything,
and which rotation table entry and calibration would be right, and saves every
number to ``/data/touchcal/last.json``.

A tap anywhere counts, so a mapping that sends taps far from the target still
gets through all five. The targets cover the whole screen, Home button
included, until the fifth.
"""

import json
import sys

import lvgl as lv
from touchkit import ui

from .fit import analyse

#: Where the last run's numbers go, in the app's data folder.
FILE = "last.json"
COUNT = 5
_POLL_MS = 30
_INK = lv.color_hex(0xFFFFFF)
_MARK = lv.color_hex(0xFFD400)
_BLACK = lv.color_hex(0x000000)


def target_places(width, height):
    """The five targets on a ``width`` x ``height`` screen: the corners a tenth in, clockwise from the top left, then the middle."""
    mx, my = width // 10, height // 10
    return [(mx, my), (width - 1 - mx, my), (width - 1 - mx, height - 1 - my), (mx, height - 1 - my), (width // 2, height // 2)]


def _device():
    """The board's touch device, or None (a computer's mouse, or no touch)."""
    drv = getattr(sys.modules.get("board_config"), "display_drv", None)
    dev = getattr(drv, "touch_device", None)
    return dev if dev is not None and hasattr(dev, "_read") else None


def _table(dev):
    for name in ("_rotation_table", "_data2"):
        table = getattr(dev, name, None)
        if table is not None:
            return tuple(table)
    return None


def _median(values):
    values = sorted(values)
    return values[len(values) // 2]


class Taps:
    """Every press the touch device reads, from first contact to lift, as one tap.

    It stands in for the device's ``_read`` until `close`, so it sees the
    points before the rotation table does, whether or not LVGL finds anything
    under them.

    Args:
        dev: The touch device (``display_drv.touch_device``).
    """

    def __init__(self, dev):
        self.dev = dev
        self._orig = dev._read
        self._xs = []
        self._ys = []
        self.done = []
        dev._read = self._read

    def _read(self):
        points = self._orig()
        if points:
            p = points if isinstance(points[0], int) else points[0]
            self._xs.append(int(p[0]))
            self._ys.append(int(p[1]))
        elif self._xs:
            # A resistive panel's first and last reads wander: the median is the press.
            self.done.append((_median(self._xs), _median(self._ys)))
            self._xs = []
            self._ys = []
        return points

    def mapped(self, raw):
        """``raw`` through the device's rotation table, as LVGL gets it."""
        mapper = getattr(self.dev, "_map_point", None)
        return tuple(mapper(raw)[:2]) if mapper is not None else raw

    def close(self):
        self.dev._read = self._orig


def _cross(parent, n, x, y, width, height):
    """Target ``n`` at ``(x, y)``: a crosshair in a ring, and its number beside it, towards the middle."""
    arm = max(16, min(width, height) // 10)
    for w, h in ((2 * arm + 1, 3), (3, 2 * arm + 1)):
        bar = ui.plain(lv.obj(parent))
        bar.set_size(w, h)
        bar.set_style_bg_color(_INK, 0)
        bar.set_style_bg_opa(lv.OPA.COVER, 0)
        bar.set_pos(x - w // 2, y - h // 2)
    d = arm + arm // 2
    ring = ui.plain(lv.obj(parent))
    ring.set_size(d, d)
    ring.set_style_radius(d, 0)
    ring.set_style_border_width(3, 0)
    ring.set_style_border_color(_MARK, 0)
    ring.set_pos(x - d // 2, y - d // 2)
    num = ui.label(parent, str(n), ui.huge, _MARK)
    if n == COUNT:
        where = lv.ALIGN.OUT_TOP_MID
    elif x < width // 2:
        where = lv.ALIGN.OUT_BOTTOM_RIGHT if y < height // 2 else lv.ALIGN.OUT_TOP_RIGHT
    else:
        where = lv.ALIGN.OUT_BOTTOM_LEFT if y < height // 2 else lv.ALIGN.OUT_TOP_LEFT
    num.align_to(ring, where, 0, 0)
    say = ui.label(parent, "Tap the middle of the cross\n%d of %d" % (n, COUNT), ui.font, _INK)
    say.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    if n == COUNT:
        say.align(lv.ALIGN.BOTTOM_MID, 0, -height // 8)
    else:
        say.align(lv.ALIGN.CENTER, 0, 0)


def main(scope):
    disp = lv.display_get_default()
    width, height = disp.get_horizontal_resolution(), disp.get_vertical_resolution()
    targets = target_places(width, height)
    dev = _device()
    taps = []
    state = {"result": None}

    # The targets go over everything, bar and Home button included: a tap
    # that the mapping sends somewhere else mustn't press anything there.
    sheet = scope.adopt(ui.plain(lv.obj(lv.layer_sys())))
    sheet.set_size(width, height)
    sheet.set_pos(0, 0)
    sheet.set_style_bg_color(_BLACK, 0)
    sheet.set_style_bg_opa(lv.OPA.COVER, 0)
    sheet.add_flag(lv.obj.FLAG.CLICKABLE)

    root = scope.root
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    root.set_style_bg_color(ui.BG, 0)
    watch = scope.adopt(Taps(dev), lambda w: w.close()) if dev is not None else None

    def show():
        sheet.clean()
        x, y = targets[len(taps)]
        _cross(sheet, len(taps) + 1, x, y, width, height)

    def tapped(raw, mapped):
        if state["result"] is not None:
            return
        taps.append({"n": len(taps) + 1, "target": targets[len(taps)], "raw": raw, "mapped": mapped})
        if len(taps) < COUNT:
            show()
        else:
            finish()

    def poll(_timer=None):
        while watch.done:
            raw = watch.done.pop(0)
            tapped(raw, watch.mapped(raw))

    def clicked(_event):
        # No touch device to watch (a computer's mouse): LVGL's point is all there is.
        p = lv.point_t()
        lv.indev_active().get_point(p)
        tapped(None, (p.x, p.y))

    if watch is not None:
        scope.every(_POLL_MS, poll)
    else:
        sheet.add_event_cb(clicked, lv.EVENT.CLICKED, None)

    def finish():
        rotation = getattr(dev, "rotation", 0) if dev is not None else 0
        mask = getattr(dev, "_mask", None) if dev is not None else None
        table = _table(dev) if dev is not None else None
        result = analyse(taps, width, height, mask, rotation, table)
        state["result"] = result
        record = {
            "display": [width, height],
            "touch_device": type(dev).__name__ if dev is not None else None,
            "rotation": rotation,
            "mask": mask,
            "table": table,
            "taps": taps,
            "analysis": result,
        }
        path = None
        try:
            path = scope.data_dir + "/" + FILE
            with open(path, "w") as f:
                json.dump(record, f)
        except (OSError, ValueError) as e:
            path = "not saved: %s" % (e,)
        sheet.add_flag(lv.obj.FLAG.HIDDEN)
        _results(root, taps, result, path, width, height, again)

    def again():
        del taps[:]
        state["result"] = None
        if watch is not None:
            del watch.done[:]
        root.clean()
        sheet.remove_flag(lv.obj.FLAG.HIDDEN)
        show()

    show()


def _results(root, taps, result, path, width, height, again):
    """Where each tap landed against its target, and what's wrong in words."""
    root.clean()
    for tap in taps:
        tx, ty = tap["target"]
        ring = ui.plain(lv.obj(root))
        ring.set_size(16, 16)
        ring.set_style_radius(8, 0)
        ring.set_style_border_width(2, 0)
        ring.set_style_border_color(ui.MUTED, 0)
        ring.set_pos(tx - 8, ty - 8)
        mx, my = tap["mapped"]
        dot = ui.plain(lv.obj(root))
        dot.set_size(12, 12)
        dot.set_style_radius(6, 0)
        hit = abs(mx - tx) <= result["tolerance"] and abs(my - ty) <= result["tolerance"]
        dot.set_style_bg_color(ui.GOOD if hit else ui.BAD, 0)
        dot.set_style_bg_opa(lv.OPA.COVER, 0)
        dot.set_pos(min(max(mx, 0), width - 1) - 6, min(max(my, 0), height - 1) - 6)

    panel = lv.obj(root)
    across = min(width - 24, 440)
    panel.set_width(across)
    panel.set_height(lv.SIZE_CONTENT)
    panel.set_style_max_height(height - 24, 0)
    panel.set_style_bg_color(ui.PANEL, 0)
    panel.set_style_bg_opa(230, 0)
    panel.set_style_border_width(0, 0)
    panel.set_style_radius(12, 0)
    panel.set_style_pad_all(12, 0)
    panel.set_style_pad_row(8, 0)
    panel.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    panel.center()
    inner = across - 24
    ok = result["ok"]
    verdict = ui.label(panel, "Touch is right" if ok else "Touch is off", ui.big, ui.GOOD if ok else ui.BAD)
    verdict.set_width(inner)
    for line in result["words"]:
        lbl = ui.label(panel, line, ui.small, ui.WHITE)
        lbl.set_width(inner)
        lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
    note = ui.label(panel, path if path.startswith("not saved") else "Saved to " + path, ui.tiny, ui.MUTED)
    note.set_width(inner)
    note.set_long_mode(lv.label.LONG_MODE.WRAP)
    ui.button(panel, "Again", again, color=ui.KEY)
