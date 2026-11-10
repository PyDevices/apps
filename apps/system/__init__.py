# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""System: whether this board is well, at a glance.

The arc turns once a second, stepping every frame, with the seconds counted in
its middle: when the arc and the count drift apart, so do the timers. Beside
it are the display's frame rate, the interpreter and its version, and a button that counts taps and shows where
the last touch landed, so touch turned the wrong way on a rotated panel shows
at once. The moving parts share one card, so the screen redraws as little as
it can while it measures itself.

The rows go in order of importance: memory, boot, network, audio, then what
the board is. The moving card's font is the largest the firmware has at or
below a twentieth of the screen's short side. The rows take the largest at or
below that which fits them all; a screen too small for all of them at the
smallest font drops them from the end. The cards sit side by side only when
the screen is more than 1.5 times wider than tall.

On a round screen everything goes in one centred column, each line no wider
than the circle is at its height, and the rows go on down while the circle
leaves them two fifths of its width. A driver says its panel is round with a
``round`` attribute; a GC9A01's is taken to be.

On a screen 400 pixels or more on its short side, More has the last app
switches, the restarts, the largest free block and Wi-Fi setup. The heap line
there is the one to watch: switching back and forth all day should leave
"in use" where it started, give or take a few KB.

`stats` returns the same numbers as a dict, whether the screen is open or
not, so they can be read from the REPL while the apps keep running::

    >>> import apps.system
    >>> apps.system.stats()
"""

import gc
import os
import sys
import time

import lvgl as lv

from touchkit import net, shell, ui

try:
    from board_config import display_drv
except ImportError:
    display_drv = None

try:
    import machine
except ImportError:
    machine = None

try:
    import esp32
except ImportError:
    esp32 = None

try:
    import microcontroller  # CircuitPython's
except ImportError:
    microcontroller = None

try:
    import platform
except ImportError:
    platform = None

_SIZES = tuple(range(12, 50, 2))  # the Montserrat sizes LVGL builds, from the smallest worth reading
GC_MS = 10000  # how often the open screen times a collection
ROWS_MS = 5000  # how often the rows are read again
SMALL = 400  # below this short side there's no More page

# What the open screen has counted, for stats().
_st = {"seconds": None, "taps": 0, "touch": None, "gc_ms": None}
_ident = {}  # what doesn't change while the board runs, read once


# -- reading the board ---------------------------------------------------------


def _ticks_ms():
    try:
        return time.ticks_ms()
    except AttributeError:  # CPython
        return int(time.monotonic() * 1000)


def _ticks_diff(a, b):
    try:
        return time.ticks_diff(a, b)
    except AttributeError:
        return a - b


def _uptime_s():
    # CPython's and CircuitPython's monotonic clocks start at boot; MicroPython
    # has the tick counter, which wraps after some days on most ports.
    mono = getattr(time, "monotonic", None)
    if mono is not None:
        return int(mono())
    return time.ticks_ms() // 1000


def collect():
    """Run ``gc.collect()`` and return how many milliseconds it took."""
    t = _ticks_ms()
    gc.collect()
    ms = _ticks_diff(_ticks_ms(), t)
    _st["gc_ms"] = ms
    return ms


def _reset_cause():
    if machine is not None and hasattr(machine, "reset_cause"):
        try:
            cause = machine.reset_cause()
        except Exception:
            return None
        for const, text in (
            ("PWRON_RESET", "power on"),
            ("HARD_RESET", "hard reset"),
            ("WDT_RESET", "watchdog"),
            ("DEEPSLEEP_RESET", "deep sleep"),
            ("SOFT_RESET", "soft reset"),
            ("BROWNOUT_RESET", "brownout"),
        ):
            if getattr(machine, const, None) == cause:
                return text
        return str(cause)
    if microcontroller is not None:
        try:
            reason = str(microcontroller.cpu.reset_reason)
        except Exception:
            return None
        return reason[reason.rfind(".") + 1 :].replace("_", " ").lower()
    return None


def _built():
    """The day this interpreter was built."""
    build = getattr(platform, "python_build", None)
    if build is not None:  # CPython: "Aug 14 2024 14:39:54"
        try:
            return " ".join(build()[1].split()[:3])
        except Exception:
            return None
    try:
        version = os.uname().version  # "v1.30.0-preview on 2026-11-05"
    except Exception:
        return None
    i = version.rfind(" on ")
    return version[i + 4 :].split()[0] if i >= 0 else None


def _interpreter():
    impl = sys.implementation
    name = {"micropython": "MicroPython", "circuitpython": "CircuitPython", "cpython": "CPython"}.get(
        impl.name, impl.name
    )
    if impl.name == "circuitpython":
        # Its version tuple leaves out the pre-release, which tells one
        # alpha from the next: "11.0.0-alpha.2 on 2026-11-05".
        try:
            return "%s %s" % (name, os.uname().version.split(" on ")[0])
        except Exception:
            pass
    v = impl.version
    return "%s %d.%d.%d" % (name, v[0], v[1], v[2])


def _board_and_cpu():
    board = getattr(sys.implementation, "_machine", None)
    if board:  # "Generic ESP32S3 module with ESP32S3": the CPU has a row of its own
        i = board.rfind(" with ")
        return (board[:i], board[i + 6 :]) if i >= 0 else (board, None)
    arch = None
    if platform is not None and hasattr(platform, "machine"):
        arch = platform.machine()
    return "%s computer" % sys.platform, arch


def _mhz():
    try:
        if machine is not None:
            f = machine.freq()
            if isinstance(f, tuple):  # stm32: (sysclk, hclk, pclk1, pclk2)
                f = f[0]
            return f // 1000000
        if microcontroller is not None:
            return microcontroller.cpu.frequency // 1000000
    except Exception:
        pass
    return None


def _temp_c():
    """The chip's own temperature in degrees C, where it has a sensor."""
    try:
        if esp32 is not None and hasattr(esp32, "mcu_temperature"):
            return esp32.mcu_temperature()
        if microcontroller is not None:
            t = microcontroller.cpu.temperature
            return None if t is None else round(t)
    except Exception:
        pass
    return None


def _identity():
    if not _ident:
        board, cpu = _board_and_cpu()
        _ident.update(
            board=board,
            cpu=cpu,
            mhz=_mhz(),
            python=_interpreter(),
            built=_built(),
            reset=_reset_cause(),
        )
        name = net.hostname()
        if name and hasattr(sys.implementation, "_machine"):
            name += ".local"
        _ident["hostname"] = name
    return _ident


def _audio():
    """``(pump running, underruns)``. The pump is only asked when something
    has loaded it: then it can't be running, and nothing new is imported."""
    p = sys.modules.get("audiodev.pump")
    if p is None:
        return False, None
    try:
        h = p.health()
    except Exception:
        h = None
    if h is None:
        return False, None
    return bool(h.get("running")), h.get("dropped")


def stats(collect_now=False):
    """What the System screen shows, as a dict, whether it's open or not.

    It reads everything fresh but the identity, and blocks for nothing:
    ``gc_ms`` is the last collection the open screen timed, unless
    *collect_now* runs one here. ``seconds``, ``fps`` and the touch figures
    are from the screen, and ``None`` (or 0 taps) while it's closed.
    """
    if collect_now:
        collect()
    s = dict(_identity())
    s["open"] = _st["seconds"] is not None
    s["seconds"] = _st["seconds"]
    s["taps"] = _st["taps"]
    s["touch"] = _st["touch"]
    fps = getattr(display_drv, "fps", None)
    s["fps"] = fps() if fps is not None else None
    if hasattr(gc, "mem_free"):
        s["heap_free"] = gc.mem_free()
        s["heap_used"] = gc.mem_alloc()
    else:  # CPython counts no heap of its own
        s["heap_free"] = s["heap_used"] = None
    s["gc_ms"] = _st["gc_ms"]
    s["uptime_s"] = _uptime_s()
    s["ip"] = net.ip()
    s["rssi"] = net.rssi()
    s["webrepl"] = net.webrepl_on()
    s["pump"], s["underruns"] = _audio()
    s["temp_c"] = _temp_c()
    s["screen"] = (int(display_drv.width), int(display_drv.height)) if display_drv is not None else None
    s["rotation"] = int(getattr(display_drv, "rotation", 0) or 0)
    return s


# -- the rows, in order of importance ------------------------------------------------------


def _size(n):
    return "%.2f MB" % (n / 1e6) if n >= 1000000 else "%d KB" % (n // 1024)


def _duration(sec):
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, sec = divmod(sec, 60)
    if d:
        return "%d d %d h" % (d, h)
    if h:
        return "%d h %02d min" % (h, m)
    if m:
        return "%d min" % m
    return "%d s" % sec


def _memory(s):
    if s["heap_free"] is None:
        return "not counted here"
    return "%s free, %s used" % (_size(s["heap_free"]), _size(s["heap_used"]))


def _boot(s):
    up = "up " + _duration(s["uptime_s"])
    return "%s, %s" % (up, s["reset"]) if s["reset"] else up


def _network(s):
    if not s["ip"]:
        return "not connected"
    return "%s, %d dBm" % (s["ip"], s["rssi"]) if s["rssi"] else s["ip"]


def _pump(s):
    if s["underruns"] is None and not s["pump"]:
        return "pump not started"
    return "pump %s, %d underruns" % ("running" if s["pump"] else "stopped", s["underruns"] or 0)


def _cpu(s):
    parts = [p for p in (s["cpu"], s["mhz"] and "%d MHz" % s["mhz"]) if p]
    if s["temp_c"] is not None:
        parts.append("%d °C" % s["temp_c"])
    return ", ".join(parts) or "-"


def _screen(s):
    if s["screen"] is None:
        return "-"
    return "%dx%d, rotation %d" % (s["screen"][0], s["screen"][1], s["rotation"])


ROWS = (
    ("Memory", _memory),
    ("Collect", lambda s: "-" if s["gc_ms"] is None else "%d ms" % s["gc_ms"]),
    ("Boot", _boot),
    ("Built", lambda s: s["built"] or "-"),
    ("Network", _network),
    ("WebREPL", lambda s: "on" if s["webrepl"] else "off"),
    ("Audio", _pump),
    ("Board", lambda s: s["board"] or "-"),
    ("Host", lambda s: s["hostname"] or "-"),
    ("CPU", _cpu),
    ("Screen", _screen),
)


# -- the screen ------------------------------------------------------------------------


def _fonts(limit):
    """The Montserrat sizes this firmware has at or below *limit* pixels,
    smallest first; the smallest it has when none is that small."""
    fonts = []
    for size in _SIZES:
        font = getattr(lv, "font_montserrat_%d" % size, None)
        if font is not None and (not fonts or size <= limit):
            fonts.append(font)
    return fonts or [lv.font_default()]


def _font_for(short):
    """The largest Montserrat this firmware has at or below a twentieth of
    *short*, or its smallest when none is that small."""
    return _fonts(short // 20)[-1]


def _card(parent, flow, pad):
    c = lv.obj(parent)
    c.set_style_bg_color(ui.PANEL, 0)
    c.set_style_text_color(ui.WHITE, 0)
    c.set_style_border_width(0, 0)
    c.set_style_radius(pad * 2, 0)
    c.set_style_pad_all(pad, 0)
    c.set_style_pad_gap(pad // 2, 0)
    c.set_flex_flow(flow)
    c.remove_flag(lv.obj.FLAG.SCROLLABLE)
    c.add_flag(lv.obj.FLAG.EVENT_BUBBLE)  # a press anywhere shows where it landed
    return c


def _dark(obj):
    """System's own colours on *obj*, so it reads the same whether or not the
    shell put a dark theme on the display."""
    obj.set_style_bg_color(ui.BG, 0)
    obj.set_style_bg_opa(lv.OPA.COVER, 0)
    obj.set_style_text_color(ui.WHITE, 0)


def _is_round():
    """Whether the panel is round: its driver says so with ``round``, or it's
    a GC9A01, a controller made for round panels."""
    if display_drv is None or int(display_drv.width) != int(display_drv.height):
        return False
    r = getattr(display_drv, "round", None)
    if r is None:
        r = type(display_drv).__name__.upper().startswith("GC9A01")
    return bool(r)


def _round_page(root, size, font, big, pad, tapped, more=None):
    """System on a round screen: one centred column, each line no wider than
    the circle is at its height.

    Returns ``(page, arc, seconds, fps, tap, touch, more, info, values)``:
    *more* is the More button when *more* is given, and the rows are *info*'s
    children. A row with too little of the circle left for it is hidden, as
    the square layout hides the rows that don't fit.
    """
    page = ui.plain(lv.obj(root))
    page.set_size(size, size)
    page.set_style_text_font(font, 0)
    page.add_flag(lv.obj.FLAG.CLICKABLE)
    _dark(page)
    r = size // 2
    inner = r - pad  # everything keeps inside this circle
    gap = max(2, pad // 2)

    # As small as the square layout's smallest: an arc round the rim looked
    # right, but its redraws halved the frame rate it was there to show.
    d = max(4 * font.line_height, size // 4)
    width = max(4, d // 12)
    arc = lv.arc(page)
    arc.set_size(d, d)
    arc.set_bg_angles(0, 360)
    arc.set_rotation(270)
    arc.set_angles(0, 0)
    arc.remove_style(None, lv.PART.KNOB)
    arc.remove_flag(lv.obj.FLAG.CLICKABLE)
    arc.set_style_arc_width(width, lv.PART.MAIN)
    arc.set_style_arc_width(width, lv.PART.INDICATOR)

    def room(y, h):
        # The circle's width across the band from y to y + h, at its narrowest.
        dy = max(abs(y - r), abs(y + h - r))
        return 2 * int((inner * inner - dy * dy) ** 0.5) if dy < inner else 0

    def place(obj, y, w):
        # Centred at the first y, going down, where the circle is w wide.
        h = obj.get_height()
        while room(y, h) < w and y < r:
            y += 1
        obj.set_pos(r - w // 2, y)
        return y + h + gap

    def line(text, sample, font=None, color=None):
        # A centred label as wide as *sample*, the widest text it will show.
        lbl = ui.label(page, sample, font, color)
        page.update_layout()
        lbl.set_width(lbl.get_width())
        lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        lbl.set_text(text)
        return lbl

    # The count takes the big font only while four digits fit inside the arc.
    seconds_lbl = ui.label(arc, "0000", big)
    arc.update_layout()
    if seconds_lbl.get_width() > d - 2 * width - 4:
        seconds_lbl.set_style_text_font(font, 0)
    seconds_lbl.set_text("0")
    seconds_lbl.center()
    fps_lbl = line(_fps_text(False), "88.8 fps, 88.8 ms, 100% busy", None, ui.MUTED)
    python_lbl = line(_identity()["python"], _identity()["python"])
    buttons = _box(page, lv.FLEX_FLOW.ROW, pad)
    _, tap_lbl = _button(buttons, "Tap  0", pad, tapped)
    more_btn = None
    if more is not None:
        more_btn, _ = _button(buttons, "More", pad, more)
        more_btn.set_style_bg_color(ui.KEY, 0)
    touch_lbl = ui.label(buttons, "touch 888, 888", None, ui.MUTED)
    page.update_layout()
    touch_lbl.set_width(touch_lbl.get_width())
    touch_lbl.set_text("touch -")
    page.update_layout()
    y = r - inner
    for obj in (arc, fps_lbl, python_lbl, buttons):
        y = place(obj, y, obj.get_width())

    # The rows, in order of importance, while the circle leaves them room.
    info = ui.plain(lv.obj(page))
    info.remove_flag(lv.obj.FLAG.CLICKABLE)  # the Tap button above it stays pressable
    info.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
    info.set_pos(0, y)
    info.set_size(size, size - y)
    top = y
    line_h = font.line_height
    narrowest = size * 2 // 5
    values = []
    for key, _fn in ROWS:
        w = room(y, line_h)
        row = ui.plain(lv.obj(info))
        row.set_size(max(w, narrowest), line_h)
        row.set_pos(r - max(w, narrowest) // 2, y - top)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_style_pad_column(pad, 0)
        row.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        ui.label(row, key, None, ui.MUTED)
        v = lv.label(row)
        v.set_flex_grow(1)
        v.set_height(line_h)
        v.set_long_mode(lv.label.LONG_MODE.DOTS)
        v.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        values.append(v)
        if w < narrowest:
            row.add_flag(lv.obj.FLAG.HIDDEN)
        y += line_h + gap
    return page, arc, seconds_lbl, fps_lbl, tap_lbl, touch_lbl, more_btn, info, values


def _box(parent, flow, gap):
    b = ui.plain(lv.obj(parent))
    b.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
    b.set_flex_flow(flow)
    b.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    b.set_style_pad_gap(gap, 0)
    b.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
    return b


def _button(parent, text, pad, cb):
    b = lv.button(parent)
    b.set_style_pad_hor(pad * 2, 0)
    b.set_style_pad_ver(pad, 0)
    b.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
    lbl = lv.label(b)
    lbl.set_text(text)
    lbl.center()
    b.add_event_cb(lambda e: cb(), lv.EVENT.CLICKED, None)
    return b, lbl


def _fps_text(split):
    fps = getattr(display_drv, "fps", None)
    f = fps() if fps is not None else None
    if f is None:
        return "fps n/a"
    return "%.1f fps%s%.1f ms, %d%% busy" % (f["fps"], "\n" if split else ", ", f["present_ms"], round(f["busy"] * 100))


def main(scope):
    root = scope.root
    W, H = scope.size
    scr = root.get_screen()
    short = min(scr.get_width(), scr.get_height())
    font = _font_for(short)
    big = _font_for(short * 2)
    pad = max(4, short // 40)
    landscape = W * 2 > H * 3  # side by side only when more than 1.5 times wider than tall
    # A round panel gets its own layout when the app has the whole screen.
    round_ = _is_round() and getattr(scope, "rect", (0, 0, W, H)) == (0, 0, scr.get_width(), scr.get_height())
    across = not landscape and W * 10 >= H * 9  # the live card's own long side
    timers = []
    # The meter goes on first, so the frame rate's two lines are there to lay out.
    measuring = getattr(display_drv, "fps", None) is not None and display_drv.fps() is not None
    if not measuring and hasattr(display_drv, "measure_fps"):
        display_drv.measure_fps(True)

    def tapped():
        _st["taps"] += 1
        tap_lbl.set_text("Tap  %d" % _st["taps"])

    _st["taps"] = 0
    _st["touch"] = None

    if round_:
        more = (lambda: show_more(True)) if short >= SMALL else None
        page, arc, seconds_lbl, fps_lbl, tap_lbl, touch_lbl, more_btn, info, values = _round_page(
            root, W, font, big, pad, tapped, more
        )
    else:
        page = ui.plain(lv.obj(root))
        page.set_size(W, H)
        page.set_style_text_font(font, 0)
        page.set_style_pad_all(pad, 0)
        page.set_style_pad_gap(pad, 0)
        page.set_flex_flow(lv.FLEX_FLOW.ROW if landscape else lv.FLEX_FLOW.COLUMN)
        page.add_flag(lv.obj.FLAG.CLICKABLE)
        _dark(page)

        # The live card: every moving part, so the dirty areas stay together.
        live = _card(page, lv.FLEX_FLOW.ROW if across else lv.FLEX_FLOW.COLUMN, pad)
        live.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        if landscape:
            live.set_size(W * 2 // 5, lv.pct(100))
        else:
            live.set_size(lv.pct(100), lv.SIZE_CONTENT)

        arc = lv.arc(live)
        arc.set_bg_angles(0, 360)
        arc.set_rotation(270)
        arc.set_angles(0, 0)
        arc.remove_style(None, lv.PART.KNOB)
        arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        seconds_lbl = ui.label(arc, "0", big)
        seconds_lbl.center()

        side = _box(live, lv.FLEX_FLOW.COLUMN, pad // 2) if across else live
        fps_lbl = ui.label(side, _fps_text(True), None, ui.MUTED)
        fps_lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        # The interpreter sits with the moving parts, which no screen drops, so
        # twin boards on different Pythons tell apart at a glance. It never changes.
        ui.label(side, _identity()["python"])

        # Beside the arc, the buttons share a line to keep the card low.
        buttons = _box(side, lv.FLEX_FLOW.ROW, pad) if across else side
        _, tap_lbl = _button(buttons, "Tap  0", pad, tapped)
        touch_lbl = None if across else ui.label(side, "touch -", None, ui.MUTED)
        more_btn = None
        if short >= SMALL:
            more_btn, _ = _button(buttons, "More", pad, lambda: show_more(True))
            more_btn.set_style_bg_color(ui.KEY, 0)
        if touch_lbl is None:
            touch_lbl = ui.label(side, "touch -", None, ui.MUTED)

        # The rows, in order of importance, as many as fit.
        info = _card(page, lv.FLEX_FLOW.COLUMN, pad)
        info.set_flex_grow(1)
        if landscape:
            info.set_height(lv.pct(100))
        else:
            info.set_width(lv.pct(100))
        line_h = font.line_height
        values = []
        for key, _fn in ROWS:
            row = ui.plain(lv.obj(info))
            row.set_width(lv.pct(100))
            row.set_flex_flow(lv.FLEX_FLOW.ROW)
            row.set_style_pad_column(pad, 0)  # a key never runs into its value
            row.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
            ui.label(row, key, None, ui.MUTED)
            v = lv.label(row)
            v.set_flex_grow(1)
            v.set_long_mode(lv.label.LONG_MODE.DOTS)
            v.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
            values.append(v)

        def size_arc():
            # The arc takes the room the live card's other parts leave.
            page.update_layout()
            if across:
                d = min(max(min(W, H) // 3, side.get_height()), W - side.get_width() - 6 * pad)
            elif not landscape:  # a tall screen: the card is as high as it needs
                d = min(W, H) * 2 // 5
            else:
                used = sum(live.get_child(i).get_height() for i in range(1, live.get_child_count()))
                gaps = (live.get_child_count() - 1) * (pad // 2)
                d = min(live.get_content_width(), live.get_content_height() - used - gaps)
            d = max(d, 4 * line_h)
            arc.set_size(d, d)
            arc.set_style_arc_width(max(4, d // 12), lv.PART.MAIN)
            arc.set_style_arc_width(max(4, d // 12), lv.PART.INDICATOR)
            page.update_layout()
            # The rows take the largest font at or below the screen's that fits
            # them all in the room left; only the smallest one drops rows.
            bottom = info.get_content_height()
            # The choice is by height alone: a value too wide for its row ends in
            # dots. The gap between rows gives way, down to 2 px, before the font.
            n = len(ROWS)
            sizes = _fonts(short // 20)
            row_font = sizes[0]
            for f in sizes:
                if n * f.line_height + (n - 1) * 2 <= bottom:
                    row_font = f
            gap = max(2, min(pad // 2, (bottom - n * row_font.line_height) // (n - 1)))
            info.set_style_pad_gap(gap, 0)
            info.set_style_text_font(row_font, 0)
            for i in range(info.get_child_count()):
                row = info.get_child(i)
                row.set_height(row_font.line_height)
                row.get_child(1).set_height(row_font.line_height)
            page.update_layout()
            # A row that would still run past the card's foot goes, and every row after it.
            for i in range(info.get_child_count()):
                row = info.get_child(i)
                if row.get_y() + row.get_height() > bottom:
                    row.add_flag(lv.obj.FLAG.HIDDEN)

        size_arc()
    shown = [not info.get_child(i).has_flag(lv.obj.FLAG.HIDDEN) for i in range(len(ROWS))]

    def read_rows(_t=None):
        s = stats()
        for i, (_key, fn) in enumerate(ROWS):
            if shown[i]:
                text = fn(s)
                if values[i].get_text() != text:
                    values[i].set_text(text)
        if more_page is not None and not more_page.has_flag(lv.obj.FLAG.HIDDEN):
            more_text.set_text(_more_lines(scope.launcher, block[0]))

    def pressed(e):
        ind = lv.indev_active()
        if ind is None:
            return
        p = lv.point_t()
        ind.get_point(p)
        _st["touch"] = (p.x, p.y)
        touch_lbl.set_text("touch %d, %d" % (p.x, p.y))

    page.add_event_cb(pressed, lv.EVENT.PRESSED, None)

    # -- More: the switches, the restarts, the largest block and Wi-Fi setup --
    more_page = more_text = None
    block = [None]

    def show_more(on):
        if on:
            more_page.remove_flag(lv.obj.FLAG.HIDDEN)
            page.add_flag(lv.obj.FLAG.HIDDEN)
            more_text.set_text(_more_lines(scope.launcher, block[0]))
        else:
            page.remove_flag(lv.obj.FLAG.HIDDEN)
            more_page.add_flag(lv.obj.FLAG.HIDDEN)

    if more_btn is not None:
        more_page = ui.plain(lv.obj(root))
        more_page.set_size(W, H)
        more_page.set_style_text_font(_font_for(short * 3 // 4), 0)  # a step down: it's a page of text
        # On a round screen the page keeps to the square inside the circle.
        more_page.set_style_pad_all(W * 3 // 20 if round_ else pad, 0)
        more_page.set_style_pad_gap(pad, 0)
        more_page.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        _dark(more_page)
        more_page.add_flag(lv.obj.FLAG.HIDDEN)
        text_card = _card(more_page, lv.FLEX_FLOW.COLUMN, pad)
        text_card.set_width(lv.pct(100))
        text_card.set_flex_grow(1)
        text_card.add_flag(lv.obj.FLAG.SCROLLABLE)
        more_text = lv.label(text_card)
        more_text.set_width(lv.pct(100))
        bar = _box(more_page, lv.FLEX_FLOW.ROW_WRAP, pad)
        bar.set_width(lv.pct(100))

        def measure():
            block[0] = scope.launcher.heap()[1]
            more_text.set_text(_more_lines(scope.launcher, block[0]))

        def wifi_setup():
            # The setup page blocks until a network is joined: never from a timer.
            if scope.foreground(job, steps=False):
                ui.status(scope).set_text("Wi-Fi setup: join the board's network from a phone")
            else:
                ui.status(scope).set_text("Wi-Fi setup waits for the foreground loop (appkit.serve())")

        def job():
            net.setup_job()
            scope.foreground(None)

        back, _ = _button(bar, lv.SYMBOL.LEFT + "  Back", pad, lambda: show_more(False))
        back.set_style_bg_color(ui.KEY, 0)
        _button(bar, "Largest block", pad, measure)
        _button(bar, "Wi-Fi setup", pad, wifi_setup)

    # -- the timers --
    # The arc steps at the display's refresh period, so it changes every frame
    # and the frame rate shown is the display's, not this app's pace. Its angle
    # comes from the clock: one turn a second at any period, in step with the
    # seconds counter, which shows if the two timers drift.
    frame_ms = int(getattr(display_drv, "refresh_period_ms", 0) or 33)
    t0 = _ticks_ms()

    def step_arc(_t):
        arc.set_angles(0, _ticks_diff(_ticks_ms(), t0) % 1000 * 360 // 1000)

    def second(_t):
        _st["seconds"] += 1
        seconds_lbl.set_text(str(_st["seconds"]))
        fps_lbl.set_text(_fps_text(not round_))

    def time_gc(_t):
        collect()

    _st["seconds"] = 0
    collect()
    read_rows()
    timers.append(lv.timer_create(step_arc, frame_ms, None))
    timers.append(lv.timer_create(second, 1000, None))
    timers.append(lv.timer_create(read_rows, ROWS_MS, None))
    timers.append(lv.timer_create(time_gc, GC_MS, None))

    def close():
        for t in timers:
            t.delete()
        _st["seconds"] = None
        if not measuring and hasattr(display_drv, "measure_fps"):
            display_drv.measure_fps(False)
        try:
            import wifi_manager

            wifi_manager.cancel()
        except Exception:
            pass

    scope.on_close(close)


def _more_lines(launcher, block=None):
    lines = [shell.heap_text()]
    if block:
        lines.append("largest free block %s" % _size(block))
    base = launcher.baseline
    if base and base[0]:
        lines.append("at start: free %s; restart below %s free" % (_size(base[0]), _size(launcher.min_free or 0)))
    lines.append("restarts in a row before this boot: %d;  BOOT presses: %d" % (launcher.restarts, shell.boot_presses))
    lines.append("")
    lines.append("last switches (app, how, ms, free after the close):")
    for name, how, ms, free in getattr(launcher, "history", ())[-8:]:
        lines.append(
            "   %-12s %-7s %5s ms   %s" % (name, how, ms if ms is not None else "-", _size(free) if free else "-")
        )
    if launcher.problems:
        lines.append("last close reported: " + "; ".join(launcher.problems[:2]))
    a = shell.audit()
    lines.append("")
    lines.append(
        "audio pump %s, I2S %s, USB host devices %s, SD %s"
        % (a.get("audiopump"), a.get("i2s"), a.get("host_devices"), a.get("sd") or "not mounted")
    )
    return "\n".join(lines)
