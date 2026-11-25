# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The status bar: Home, the running app's title and status line, then the
clock, the network, Bluetooth, the battery and the audio output along the
top of the screen, and a button for every connection the device has. It is
the app's title bar too: there's no second strip under it.

The Shell makes it when asked (``Shell(launcher, bar=True)``) and gives each
app the screen below it. An app says in its ``app.json`` whether it wants it::

    "bar": "shell"   the Shell's bar, the app gets the rest (the default)
    "bar": "own"     the whole screen; the app draws its own bar from `Bar.status`
    "bar": "none"    the whole screen and no bar

The bar is 32 px tall on a screen under 480 px tall and 40 px from there
up (`height_for`). An app under it gets ``scope.header``, the stretch of the
bar between Home and the clock that holds its title, and ``scope.status``,
its status line, at the header's right. The title gives way first: it ends
in dots, down to `TITLE_MIN`, before the status line does. On a screen
under `STATUS_ROW_UNDER` wide the status line has a row of its own under
the bar instead.

An app reaches the bar as ``scope.bar``: `hide` and `show` it for a while (a
video, a game), or `add` an item of its own, which goes when the app closes::

    scope.bar.add(bar.Item("cast", lambda: ("cast", "Living room")), scope)

On a round screen or one under 320x240 the bar is a compact cap at the top
middle: the clock, the network and the battery, and a tap opens the picker.

One timer runs once a second. It polls endpointkit, so slow providers report,
and redraws only the items whose icon or text changed: each redraw costs a
board's display time that audio may need.
"""

import sys
import time

import lvgl as lv
from icons import lvgl as lvicons

try:
    import endpointkit
except ImportError:
    endpointkit = None

#: The compact cap's height, and its icons' size, in pixels.
HEIGHT = 24
ICON = 20
#: The full bar's height: SHORT on a screen under TALL_FROM px tall, TALL from there.
SHORT = 32
TALL = 40
TALL_FROM = 480
#: The full bar's icons, in pixels.
FULL_ICON = 24
#: A long title ends in dots down to this width, in pixels, before the status line gives way.
TITLE_MIN = 72
#: Under this screen width the status line has its own row below the bar.
STATUS_ROW_UNDER = 480
#: The title's colour (LVGL's teal, touchkit's accent) and the status line's.
TITLE = 0x009688
MUTED = 0x9E9E9E
#: How often the bar reads its items, in milliseconds.
TICK_MS = 1000
#: The bar's colours: its background, and its icons and text.
BACKGROUND = 0x202020
FOREGROUND = 0xFFFFFF
#: Under this width or height the bar is the compact cap.
FULL_MIN = (320, 240)


class Item:
    """One thing the bar shows.

    Args:
        name (str): unique on the bar.
        read: a function returning ``(icon, text)`` (either may be None), or
            None to show nothing now. Called on the bar's tick; keep it quick.
        every (int): read it every this many ticks.
        on_click: called with no arguments when the item is tapped.
    """

    def __init__(self, name, read, every=1, on_click=None):
        self.name = name
        self.read = read
        self.every = every
        self.on_click = on_click


# -- the built-in items --------------------------------------------------------


def clock_item():
    """The time, ``14:05``, from ``time.localtime``."""

    def read():
        t = time.localtime()
        return None, "%02d:%02d" % (t[3], t[4])

    return Item("clock", read)


def _uplink_icon(ep):
    res = ep.resources
    if "radio.wifi" in res:
        return "wifi"
    if "radio.bt" in res:
        return "bluetooth"
    for r in res:
        if r.startswith("eth"):
            return "lan"
        if r.startswith("usb"):
            return "usb"
    return "link"


def net_item(registry):
    """The network carrying traffic: Wi-Fi, Ethernet, USB or Bluetooth by its
    icon, or Wi-Fi off when nothing is connected."""

    def read():
        up = [ep for ep in registry.endpoints("net") if ep.state == endpointkit.CONNECTED]
        if not up:
            return "wifi_off", None
        chosen = registry.selection("net")
        up.sort(key=lambda ep: ep.id not in chosen)   # the device's choice first
        return _uplink_icon(up[0]), None

    return Item("net", read)


def bluetooth_item(registry):
    """Bluetooth, shown while something on the radio is connected or chosen."""

    def read():
        chosen = False
        for kind in endpointkit.kinds():
            picked = registry.selection(kind)
            for ep in registry.endpoints(kind):
                if "radio.bt" not in ep.resources:
                    continue
                if ep.state == endpointkit.CONNECTED:
                    return "bluetooth_connected", None
                chosen = chosen or ep.id in picked
        return ("bluetooth", None) if chosen else None

    return Item("bluetooth", read)


def audio_item(registry, on_click=None):
    """Where sound goes: headphones or a speaker, and nothing when no output
    is chosen. A tap opens the picker at audio out."""

    def read():
        out = registry.selected("audio.out")
        if not out:
            return None
        return ("headphones" if "phone" in out[0].label.lower() else "volume_up"), None

    return Item("audio", read, on_click=on_click)


def cast_item(registry, on_click=None):
    """The cast icon while the screen goes somewhere, a browser mirroring it
    for one, with "viewing" while someone watches. Nothing otherwise, so a
    mirror left on shows on every screen. A tap opens the picker at cast to,
    which says the address to open."""

    def read():
        out = registry.selected("cast.target")
        if not out or out[0].state != endpointkit.CONNECTED:
            return None
        return "cast", ("viewing" if out[0].caps.get("viewing") else None)

    return Item("cast", read, on_click=on_click)


def _battery_percent(source):
    """A percentage from a fuel gauge's ``percent`` or, failing that, a
    single LiPo cell's ``voltage`` (3.3 V empty, 4.2 V full). None with no
    battery. The battery drivers give both as properties."""
    p = getattr(source, "percent", None)
    if p is not None:
        return max(0, min(100, int(p)))
    v = source.voltage
    if v is None:
        return None
    return max(0, min(100, int((v - 3.3) * 100 / 0.9)))


def battery_item(source):
    """The battery from *source*, the board's ``battery()`` (a gauge with a
    ``percent`` property or an ADC with ``voltage``); hidden while it reads none."""

    def read():
        p = _battery_percent(source)
        if p is None:
            return None
        if getattr(source, "charging", False):
            return "battery_charging_full", "%d%%" % p
        icon = "battery_full" if p >= 95 else "battery_%d_bar" % (p * 7 // 100)
        return icon, "%d%%" % p

    return Item("battery", read, every=30)


def board_battery():
    """The battery the board config gives (``board_peripherals.battery()``),
    if one is imported and has the role; None otherwise."""
    board = sys.modules.get("board_peripherals")
    make = getattr(board, "battery", None)
    if make is None:
        return None
    return make()


# -- the bar -------------------------------------------------------------------


def height_for(w, h):
    """The full bar's height on a *w* x *h* screen."""
    return TALL if h >= TALL_FROM else SHORT


def _font_up_to(px):
    """The largest built-in Montserrat no taller than *px*, or the default."""
    for size in range(px, 9, -1):
        f = getattr(lv, "font_montserrat_%d" % size, None)
        if f is not None:
            return f
    return lv.font_default()


def _plain(obj):
    obj.set_style_bg_opa(lv.OPA.TRANSP, 0)
    obj.set_style_border_width(0, 0)
    obj.set_style_pad_all(0, 0)
    obj.set_style_radius(0, 0)
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return obj


class Bar:
    """The bar, on ``lv.layer_top()``.

    Args:
        registry (endpointkit.Registry): whose network, Bluetooth and audio
            it shows, and polls; the device's when None.
        on_home: called when Home is tapped; no Home button when None.
        on_picker: called with a kind or None when the connections button
            (or an item that opens the picker) is tapped.
        compact (bool): the compact cap; None decides from the screen.
        items (list): the `Item` list to start with; None for the built-in
            ones this device has.
        tick_ms (int): the timer's period, or 0 to leave ticking to the caller.
    """

    def __init__(self, registry=None, on_home=None, on_picker=None, compact=None, items=None, tick_ms=TICK_MS):
        if registry is None and endpointkit is not None:
            registry = endpointkit.registry
        self.registry = registry
        self.on_picker = on_picker
        disp = lv.display_get_default()
        w, h = disp.get_horizontal_resolution(), disp.get_vertical_resolution()
        if compact is None:
            from .shell import is_round

            compact = is_round() or w < FULL_MIN[0] or h < FULL_MIN[1]
        self.compact = compact
        self.height = HEIGHT if compact else height_for(w, h)
        self.icon = ICON if compact else FULL_ICON
        self.status_below = not compact and w < STATUS_ROW_UNDER
        self.group = lv.group_create()
        self._ticks = 0
        self._shown = {}   # name -> [box, image or None, label or None, (icon, text) last drawn]
        self._listening = None
        self._on_change = None   # the Shell's, told when the bar hides or shows

        root = _plain(lv.obj(lv.layer_top()))
        root.set_style_bg_opa(lv.OPA.COVER, 0)
        root.set_style_bg_color(lv.color_hex(BACKGROUND), 0)
        root.set_flex_flow(lv.FLEX_FLOW.ROW)
        root.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        root.set_style_pad_column(6, 0)
        root.set_style_pad_hor(4, 0)
        if compact:
            root.set_size(lv.SIZE_CONTENT, HEIGHT)
            root.set_style_radius(HEIGHT // 2, 0)
            root.set_style_pad_hor(HEIGHT // 2, 0)
            root.align(lv.ALIGN.TOP_MID, 0, 2)
            root.add_flag(lv.obj.FLAG.CLICKABLE)
            root.add_event_cb(lambda e: self._picker(None), lv.EVENT.CLICKED, None)
            self.group.add_obj(root)
        else:
            root.set_size(lv.pct(100), self.height)
            root.align(lv.ALIGN.TOP_MID, 0, 0)
        from . import scope

        scope.keep(root)   # the program's, whichever app is running
        self.root = root

        self.home = None
        if on_home is not None and not compact:
            self.home = self._button("home", on_home)
            self.home.set_ext_click_area(4)   # a thumb's width, though the bar is short
        # The cap keeps the clock at its left; the full bar puts it at the right.
        self.left = None
        if compact:
            self.left = _plain(lv.obj(root))
            self.left.set_size(lv.SIZE_CONTENT, HEIGHT)
            self.left.set_flex_flow(lv.FLEX_FLOW.ROW)
            self.left.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            self.left.remove_flag(lv.obj.FLAG.CLICKABLE)
            self.left.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        self.header = self.title = self.status_line = self.under = None
        if not compact:
            self._make_header(scope, w)
        self.right = _plain(lv.obj(root))
        self.right.set_size(lv.SIZE_CONTENT, self.height)
        self.right.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.right.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.right.set_style_pad_column(6, 0)
        self.right.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.right.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        self.connections = None
        if on_picker is not None and not compact:
            self.connections = self._button("tune", lambda: self._picker(None))

        self.items = []
        for item in (items if items is not None else self.default_items()):
            self.add(item)
        self._timer = None
        if tick_ms:
            self._timer = lv.timer_create(lambda t: self.tick(), tick_ms, None)
        if registry is not None:
            # Kept: endpointkit unsubscribes by identity.
            self._listening = registry.subscribe(None, self._changed)
        self.tick()

    def _make_header(self, scope, w):
        """The stretch between Home and the clock: the app's title, and its
        status line here or in a row of its own under the bar."""
        self.title_font = _font_up_to(self.height * 6 // 10)
        self.status_font = _font_up_to(self.height * 4 // 10 + 2)
        hdr = _plain(lv.obj(self.root))
        hdr.set_height(self.height)
        hdr.set_flex_grow(1)
        hdr.remove_flag(lv.obj.FLAG.CLICKABLE)
        hdr.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        self.header = hdr
        t = lv.label(hdr)
        t.set_style_text_font(self.title_font, 0)
        t.set_style_text_color(lv.color_hex(TITLE), 0)
        t.set_long_mode(lv.label.LONG_MODE.DOTS)
        t.set_height(self.title_font.line_height)
        t.set_text("")
        t.align(lv.ALIGN.LEFT_MID, 0, 0)
        self.title = t
        self._title_w = 0
        if self.status_below:
            under = _plain(lv.obj(lv.layer_top()))
            under.set_style_bg_opa(lv.OPA.COVER, 0)
            under.set_style_bg_color(lv.color_hex(BACKGROUND), 0)
            under.set_size(w, self.status_font.line_height + 4)
            under.set_pos(0, self.height)
            under.add_flag(lv.obj.FLAG.HIDDEN)
            scope.keep(under)
            self.under = under
        hdr.add_event_cb(lambda e: self._fit_header(), lv.EVENT.SIZE_CHANGED, None)

    def _new_status(self):
        """A fresh status line for the app being opened: the last app may
        have moved or restyled its own."""
        if self.status_line is not None:
            self.status_line.delete()
        parent = self.under if self.status_below else self.header
        st = lv.label(parent)
        st.set_style_text_font(self.status_font, 0)
        st.set_style_text_color(lv.color_hex(MUTED), 0)
        st.set_long_mode(lv.label.LONG_MODE.DOTS)
        st.set_height(self.status_font.line_height)
        st.set_text("")
        if self.status_below:
            st.set_style_max_width(self.under.get_width() - 2 * self._title_x(), 0)
            st.align(lv.ALIGN.LEFT_MID, self._title_x(), 0)
        else:
            st.align(lv.ALIGN.RIGHT_MID, 0, 0)
            st.add_event_cb(lambda e: self._fit_header(), lv.EVENT.SIZE_CHANGED, None)
        self.status_line = st
        return st

    def _title_x(self):
        """Where the title starts on the screen: past Home and the gap."""
        self.root.update_layout()
        return self.header.get_x()

    def open(self, title, status=True):
        """Set the bar up for the app being opened: *title* in the header,
        and with *status* a fresh, empty status line (in its row under the
        bar on a narrow screen). What the last app put in the header goes.
        Returns ``(header, status line)``; both None on the compact cap, and
        the status line None without *status*."""
        if self.header is None:
            return None, None
        self._clear_header()
        self.title.set_text(title or "")
        self._title_w = self._text_width(title or "", self.title_font)
        st = None
        if status:
            st = self._new_status()
        elif self.status_line is not None:
            self.status_line.delete()
            self.status_line = None
        if self.under is not None:
            if st is not None and self.is_shown():
                self.under.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.under.add_flag(lv.obj.FLAG.HIDDEN)
        self._fit_header()
        return self.header, st

    @staticmethod
    def _text_width(text, font):
        """*text*'s width in *font*, from a label that's thrown away: LVGL's
        text measuring calls differ between its versions."""
        if not text:
            return 0
        m = lv.label(lv.layer_top())
        m.set_style_text_font(font, 0)
        m.set_text(text)
        m.update_layout()
        w = m.get_width()
        m.delete()
        return w

    def _clear_header(self):
        """Delete what the last app had in the header: its status line, and
        anything it put there. The title, the header's first child, stays.
        LVGL hands back a new wrapper for a child, so they're told apart by
        place, not identity."""
        for i in range(self.header.get_child_count() - 1, 0, -1):
            self.header.get_child(i).delete()
        if not self.status_below:
            self.status_line = None   # deleted with the rest

    def _fit_header(self):
        """The title takes what the status line leaves it, ending in dots;
        the status line takes all but `TITLE_MIN` of it (less for a short
        title), and ends in dots past that."""
        hdr = self.header
        hw = hdr.get_width()
        if hw <= 0:
            return
        gap = 8
        st = self.status_line
        sw = 0
        if st is not None and st.get_parent() is hdr:
            keep = min(self._title_w, TITLE_MIN)
            st.set_style_max_width(max(0, hw - keep - gap), 0)
            st.update_layout()
            sw = st.get_width() + gap if st.get_text() else 0
        tw = max(0, min(self._title_w, hw - sw))
        if self.title.get_width() != tw:
            self.title.set_width(tw)

    def chrome_height(self):
        """How much of the screen's top the bar takes while it shows: the
        bar, and the status line's row under it when that's out."""
        if not self.is_shown() or self.compact:
            return 0
        if self.under is not None and not self.under.has_flag(lv.obj.FLAG.HIDDEN):
            return self.height + self.under.get_height()
        return self.height

    def default_items(self):
        """The built-in items this device has: the clock, and with endpointkit
        the network, Bluetooth, audio out and casting, and the battery when the
        board has one."""
        out = [clock_item()]
        if self.registry is not None:
            out.append(net_item(self.registry))
            if not self.compact:
                out.append(bluetooth_item(self.registry))
                out.append(audio_item(self.registry, lambda: self._picker("audio.out")))
                out.append(cast_item(self.registry, lambda: self._picker("cast.target")))
        source = board_battery()
        if source is not None:
            out.append(battery_item(source))
        return out

    def _button(self, icon_name, on_click):
        b = _plain(lv.button(self.root))
        b.set_style_shadow_width(0, 0)
        b.set_size(self.height + 12 if not self.compact else HEIGHT + 8, self.height)
        lvicons.image(b, icon_name, self.icon, lv.color_hex(FOREGROUND)).center()
        b.add_event_cb(lambda e: on_click(), lv.EVENT.CLICKED, None)
        self.group.add_obj(b)
        return b

    def _picker(self, kind):
        if self.on_picker is not None:
            self.on_picker(kind)

    # -- items -----------------------------------------------------------------

    def add(self, item, owner=None):
        """Show *item*; with *owner*, an app's scope, it goes when the app closes.
        An item of the same name is replaced. Returns *item*."""
        self.remove(item.name)
        self.items.append(item)
        if owner is not None:
            owner.on_close(lambda: self.remove(item.name))
        self._draw(item, force=True)
        return item

    def remove(self, name):
        """Take the item called *name* off the bar, if it's there."""
        self.items = [i for i in self.items if i.name != name]
        shown = self._shown.pop(name, None)
        if shown is not None:
            shown[0].delete()

    def status(self):
        """``[(name, icon, text)]`` for each item showing something, in the
        bar's order: what an app with its own bar draws."""
        out = []
        for item in self.items:
            shown = self._shown.get(item.name)
            if shown is not None and shown[3] is not None:
                out.append((item.name, shown[3][0], shown[3][1]))
        return out

    def tick(self):
        """Poll endpointkit and redraw each item that is due and changed;
        the bar's timer calls it once a second."""
        if self.registry is not None:
            self.registry.poll()
        for item in self.items:
            if self._ticks % item.every == 0:
                self._draw(item)
        self._ticks += 1

    def _changed(self, event, kind):
        # A choice or a state moved: the network and radio items see it now.
        for item in self.items:
            if item.name in ("net", "bluetooth", "audio"):
                self._draw(item)

    def _draw(self, item, force=False):
        try:
            value = item.read()
        except Exception as exc:  # noqa: BLE001 - one item can't stop the bar
            if hasattr(sys, "print_exception"):
                sys.print_exception(exc)
            print("bar: item %r failed: %r" % (item.name, exc))
            value = None
        shown = self._shown.get(item.name)
        if shown is not None and shown[3] == value and not force:
            return
        if shown is not None:
            shown[0].delete()
            del self._shown[item.name]
        if value is None:
            self._shown[item.name] = [_plain(lv.obj(self.right)), None, None, None]
            self._shown[item.name][0].set_size(0, 0)
            return
        icon_name, text = value
        parent = self.left if item.name == "clock" and self.left is not None else self.right
        box = _plain(lv.obj(parent))
        box.set_size(lv.SIZE_CONTENT, self.height)
        box.set_flex_flow(lv.FLEX_FLOW.ROW)
        box.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        box.set_style_pad_column(2, 0)
        img = label = None
        if icon_name:
            img = lvicons.image(box, icon_name, self.icon, lv.color_hex(FOREGROUND))
        if text:
            label = lv.label(box)
            label.set_text(text)
            # On the label itself: the theme gives every plain object its own
            # text colour, so the bar's wouldn't reach it.
            label.set_style_text_color(lv.color_hex(FOREGROUND), 0)
        if item.on_click is not None and not self.compact:
            box.add_flag(lv.obj.FLAG.CLICKABLE)
            box.add_event_cb(lambda e: item.on_click(), lv.EVENT.CLICKED, None)
            self.group.add_obj(box)
        else:
            box.remove_flag(lv.obj.FLAG.CLICKABLE)
            box.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        self._place(item, box, parent)
        self._shown[item.name] = [box, img, label, value]

    def _place(self, item, box, parent):
        """Keep the items in the order they were added."""
        index = 0
        for other in self.items:
            if other is item:
                break
            shown = self._shown.get(other.name)
            if shown is not None and shown[0].get_parent() == parent:
                index += 1
        box.move_to_index(index)

    # -- showing ---------------------------------------------------------------

    def is_shown(self):
        return not self.root.has_flag(lv.obj.FLAG.HIDDEN)

    def hide(self):
        """Hide the bar until `show`: the app's area grows to the whole screen."""
        if self.is_shown():
            self.root.add_flag(lv.obj.FLAG.HIDDEN)
            if self.under is not None:
                self._under_was = not self.under.has_flag(lv.obj.FLAG.HIDDEN)
                self.under.add_flag(lv.obj.FLAG.HIDDEN)
            if self._on_change is not None:
                self._on_change(False)

    def show(self):
        """Show the bar again; the app's area gives it back its strip."""
        if not self.is_shown():
            self.root.remove_flag(lv.obj.FLAG.HIDDEN)
            if self.under is not None and getattr(self, "_under_was", False):
                self.under.remove_flag(lv.obj.FLAG.HIDDEN)
            if self._on_change is not None:
                self._on_change(True)

    def set_home(self, visible):
        """Show the Home button or not (the Shell hides it on the home screen)."""
        if self.home is not None:
            if visible:
                self.home.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.home.add_flag(lv.obj.FLAG.HIDDEN)

    def close(self):
        """Stop the timer and listening, and delete the bar."""
        if self._timer is not None:
            self._timer.delete()
            self._timer = None
        if self._listening is not None:
            self.registry.unsubscribe(self._listening)
            self._listening = None
        from . import scope

        scope.unkeep(self.root)
        self.root.delete()
        if self.under is not None:
            scope.unkeep(self.under)
            self.under.delete()
