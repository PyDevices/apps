# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""How a person drives the camera: the board's buttons, or the screen.

A board whose config has a keypad or an encoder keeps them. A board with a
touch screen uses the Menu, Up, Down and Select pictures the pages already
draw: tap one, tap the picture to press the knob, and swipe up or down to
turn it.
"""

try:
    import lvgl as lv
except ImportError:
    lv = None

POINTER, ENCODER, KEYPAD = 2, 3, 4  # appdev device types

# Pixels from the stage's centre to each hint, as the pages draw them.
HINT_X = 100
HINT_TOP, HINT_UP, HINT_DOWN = -47, 0, 55
ZONE_W, ZONE_H = 40, 46
SWIPE_REACH = 24  # pixels a press must travel to be a swipe, not a tap


def devices_for(device_types, on_desktop=False):
    """Which controls to wire, as ``(hardware, touch)``.

    *device_types* are the appdev device types the app has. A keypad or an
    encoder means the board has buttons and a knob. A pointer means a touch
    screen, which gets the tap zones as well: a board with only a Boot button
    still needs them. A desktop has the keyboard and the mouse, which is a touch.
    """
    if on_desktop:
        return True, True
    hardware = any(t in (ENCODER, KEYPAD) for t in device_types)
    return hardware, POINTER in device_types or not hardware


def button_table(keys, board_config=None):
    """Key code -> "menu", "up", "down" or "encoder".

    A board names its own in ``board_config.camera_buttons``, a dict of the
    names to key codes (a name may have several, as a tuple). Without one the
    table is the Eye's: M or Escape, the arrow keys, and Enter.
    """
    given = getattr(board_config, "camera_buttons", None)
    if given:
        table = {}
        for name, codes in given.items():
            for code in codes if isinstance(codes, (tuple, list)) else (codes,):
                table[code] = name
        return table
    return {
        keys.K_m: "menu",
        keys.K_ESCAPE: "menu",  # the Eye's Menu button
        keys.K_UP: "up",
        keys.K_DOWN: "down",
        keys.K_RETURN: "encoder",
        keys.K_KP_ENTER: "encoder",
    }


def swipe(dx, dy, reach=SWIPE_REACH):
    """"up" or "down" when a press moved mostly vertically by at least
    *reach* panel pixels, else None."""
    if abs(dy) >= reach and abs(dy) > 2 * abs(dx):
        return "down" if dy > 0 else "up"
    return None


def swipe_detents(direction):
    """The knob detents one vertical swipe turns: three make a step.

    *direction* is "up" or "down". Up turns left (closer), down turns right.
    Anything else turns nothing.
    """
    return {"up": -3, "down": 3}.get(direction, 0)


def top_button(select_showing):
    """What the top hint does: the knob press where the page draws Select,
    Menu where it draws Menu."""
    return "encoder" if select_showing else "menu"


class TouchControls:
    """Clear tap zones over one stage's Menu, Up and Down pictures, a tap on
    the rest of the page for the knob press, and a vertical swipe for the
    knob's turn. A long press on the top picture is always Menu."""

    def __init__(self, box, eye, scale=1):
        self.eye = eye
        self.scale = scale
        self._start = (0, 0)
        self._swiped = False
        # A clear sheet over the whole page, so a press lands here whatever
        # is drawn under it; the three zones sit on top of it.
        sheet = lv.obj(box)
        sheet.remove_style_all()
        sheet.set_size(lv.pct(100), lv.pct(100))
        sheet.add_flag(lv.obj.FLAG.CLICKABLE)
        sheet.remove_flag(lv.obj.FLAG.SCROLLABLE)
        sheet.add_event_cb(self._press_knob, lv.EVENT.CLICKED, None)
        sheet.add_event_cb(self._down, lv.EVENT.PRESSED, None)
        sheet.add_event_cb(self._up, lv.EVENT.RELEASED, None)
        top = self._zone(box, HINT_TOP)
        top.add_event_cb(self._top, lv.EVENT.CLICKED, None)
        top.add_event_cb(self._menu, lv.EVENT.LONG_PRESSED, None)
        self._zone(box, HINT_UP).add_event_cb(lambda e: eye.button("up"), lv.EVENT.CLICKED, None)
        self._zone(box, HINT_DOWN).add_event_cb(lambda e: eye.button("down"), lv.EVENT.CLICKED, None)

    @staticmethod
    def _zone(box, y):
        z = lv.obj(box)
        z.remove_style_all()
        z.set_size(ZONE_W, ZONE_H)
        z.align(lv.ALIGN.CENTER, HINT_X, y)
        z.add_flag(lv.obj.FLAG.CLICKABLE)
        z.remove_flag(lv.obj.FLAG.SCROLLABLE)
        z.remove_flag(lv.obj.FLAG.EVENT_BUBBLE)
        return z

    def _press_knob(self, e):
        if self._swiped:
            self._swiped = False  # the release that ended a swipe is not a tap
            return
        self.eye.button("encoder")

    def _top(self, e):
        self.eye.button(top_button(self.eye.select_showing()))

    def _menu(self, e):
        self.eye.button("menu")

    def _point(self):
        p = lv.point_t()
        lv.indev_active().get_point(p)
        return p.x, p.y

    def _down(self, e):
        self._start = self._point()
        self._swiped = False

    def _up(self, e):
        x, y = self._point()
        direction = swipe(x - self._start[0], y - self._start[1], SWIPE_REACH * self.scale)
        n = swipe_detents(direction)
        if n:
            self._swiped = True
        for _ in range(abs(n)):
            self.eye.detent(1 if n > 0 else -1)
