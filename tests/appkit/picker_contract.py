# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's picker on real LVGL with no window, over endpointkit's fakes.

endpointkit's ``fake.bench`` stands in for a board's transports: I2S and
Bluetooth audio, MIDI, Wi-Fi and the rest, some of them slow to find. The
picker is opened over a running screen and pressed with a pointer and turned
with a wheel, and each check reads what endpointkit was told and what the
screen shows.

    python tests/appkit/picker_contract.py
    micropython tests/appkit/picker_contract.py

endpointkit and, on CPython, icons come from the omnipython checkout `_harness`
finds (``OMNIPYTHON_LIB``, or one beside this repository); MicroPython needs a
build with ttfio and icons frozen in. ``PICKER_SCREEN`` sets
the display (``480x320`` unless set); ``PICKER_SHOTS=<folder>`` saves each
page as a raw RGB565 frame (a ``w h`` line, then the pixels).
``PICKER_PLANT=<name>`` breaks the picker one way from `PLANTS`, and the
checks must then fail. Exits 1 if a check fails, 2 if something it needs
isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [_join(_ROOT, "lib"), _TESTS,
                _join(_OMNI, "packages", "endpointkit"), _LIB]
# On MicroPython icons comes frozen, so its font stays in flash and off the heap.
if sys.implementation.name != "micropython":
    sys.path.insert(3, _join(_OMNI, "packages", "icons"))

try:
    import endpointkit
    import icons  # noqa: F401
    import lvgl as lv
    from endpointkit import fake
except ImportError as e:
    print("can't run the picker checks:", e)
    sys.exit(2)

import _headless
from appkit import picker as P
from appkit import connections

# The fakes are this device: the Shell registers no real provider beside them.
connections.register = lambda registry=None: []

SW, SH = (int(n) for n in (os.getenv("PICKER_SCREEN") or "480x320").split("x"))
SHOTS = os.getenv("PICKER_SHOTS")
failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


# -- plants: each must make a check fail -------------------------------------


def _plant_many_moves():
    # A MANY kind treated like a ONE kind: tapping a second peer drops the first.
    real = P.toggle

    def toggle(registry, kind, endpoint_id, confirm=False):
        registry.select(kind, [endpoint_id], confirm=confirm)
        return registry.chosen(kind)

    P.toggle = toggle
    return real


def _plant_never_asks():
    # A conflict is confirmed without asking.
    def choose(self, endpoint_id, confirm=False):
        real(self, endpoint_id, True)

    P.Picker.choose = choose


def _plant_deaf():
    # News from the registry never redraws the page.
    P.Picker._changed = lambda self, event, kind: None


def _plant_keeps_listening():
    # Closing leaves the registry subscription behind.
    P.Picker.close = lambda self: self.root.add_flag(lv.obj.FLAG.HIDDEN)


def _plant_no_pin_note():
    real = P.summary
    P.summary = lambda registry, kind: real(registry, kind).split(" (pinned")[0]


def _plant_pairs_blind():
    # Tapping something that needs pairing chooses it unpaired.
    def choose(self, endpoint_id, confirm=False):
        try:
            P.toggle(self.registry, self.kind, endpoint_id, confirm=confirm)
        except endpointkit.Conflict as c:
            self._ask(c, endpoint_id)
            return
        self.show(self.kind)

    P.Picker.choose = choose


def _plant_no_address():
    # The picker ignores what an endpoint's caps say.
    real = P.rows

    def rows(registry, kind):
        return [(ep, chosen, P._STATES.get(ep.state, ep.state)) for ep, chosen, _ in real(registry, kind)]

    P.rows = rows


def _plant_secret_dropped():
    # The password typed never reaches the provider.
    real = P.Picker._pair
    P.Picker._pair = lambda self, endpoint_id, field: real(self, endpoint_id, None)


def _plant_grant_asks_first():
    # What the browser asks about gets the picker's own question first.
    real = P.Picker.choose

    def choose(self, endpoint_id, confirm=False):
        ep = self.registry.find(endpoint_id)
        if ep is not None and ep.caps.get("grant"):
            self._ask_pair(ep)
            return
        real(self, endpoint_id, confirm)

    P.Picker.choose = choose


PLANTS = {
    "grant_asks_first": _plant_grant_asks_first,
    "no_address": _plant_no_address,
    "pairs_blind": _plant_pairs_blind,
    "secret_dropped": _plant_secret_dropped,
    "many_moves": _plant_many_moves,
    "never_asks": _plant_never_asks,
    "deaf": _plant_deaf,
    "keeps_listening": _plant_keeps_listening,
    "no_pin_note": _plant_no_pin_note,
}

plant = os.getenv("PICKER_PLANT")
if plant:
    PLANTS[plant]()


# -- reading the screen ------------------------------------------------------


def rows(p):
    """``(button, text, detail, checked)`` for each row of the list on show."""
    out = []
    for i in range(p.list.get_child_count()):
        b = p.list.get_child(i)
        if b.get_child_count() < 2:
            continue   # a text row, not a button
        slot, words = b.get_child(0), b.get_child(1)
        text = words.get_child(0).get_text()
        detail = words.get_child(1).get_text() if words.get_child_count() > 1 else ""
        out.append((b, text, detail, slot.get_child_count() > 0))
    return out


def texts(p):
    return [r[1] for r in rows(p)]


def row(p, text):
    for r in rows(p):
        if r[1] == text:
            return r
    return None


def centre(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2


def tap(obj):
    obj.scroll_to_view_recursive(False)   # as you'd scroll to it
    x, y = centre(obj)
    # Each half longer than LVGL's 30 ms input read, so neither is missed.
    _headless.touch(x, y, True, 50)
    _headless.touch(x, y, False, 50)


def settle(ms=1000):
    for _ in range(ms // 50):
        _headless.advance(50)


def fits(obj):
    """Whether *obj* is wholly on the screen."""
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1 >= 0 and a.y1 >= 0 and a.x2 < SW and a.y2 < SH


def shot(name):
    _headless.refresh()
    if SHOTS:
        _headless.save_raw(_join(SHOTS, name + ".raw"), SW, SH)


# -- the checks --------------------------------------------------------------

_headless.display(SW, SH)
_headless.pointer()
app = lv.obj(None)
lv.label(app).set_text("The running app")
lv.screen_load(app)
# The app has a wheel on its own group: the picker must take it while open.
app_group = lv.group_create()
app_buttons = [lv.button(app), lv.button(app)]
for b in app_buttons:
    app_group.add_obj(b)
wheel = _headless.wheel(app_group)

reg = endpointkit.Registry()
fakes = fake.bench(reg, delay=2)

# Without the screen: the kinds, in the picker's order, the strangers last by name.
order = P.kinds(reg)
check(order == ["audio.out", "audio.in", "midi.in", "midi.out", "net", "camera",
                "espnow.peer", "thread.net"], "the kinds in order: %r" % (order,))
check(P.title("audio.out") == "Audio out" and P.title("espnow.peer") == "ESP-NOW peers",
      "a kind's title is endpointkit's, an added kind's too")
endpointkit.add_kind("test.bare", endpointkit.MANY)
check(P.title("test.bare") == "test.bare" and P.icon("test.bare") == P.OTHER_ICON,
      "a kind added with no title is its name, with the other icon")
endpointkit.add_kind("test.odd", endpointkit.MANY, icon="no_such_icon")
check(P.icon("audio.out") == "volume_up" and P.icon("test.odd") == P.OTHER_ICON,
      "endpointkit's icon, or the other one when icons hasn't it")
check(P.summary(reg, "audio.out") == "Nothing chosen", "nothing chosen yet")

p = P.Picker(reg)
check(not p.is_open(), "made hidden")
p.open()
_headless.advance(20)
check(p.is_open(), "open shows it")
check(p.heading.get_text() == "Connections", "the first page's heading")
names = texts(p)
check(names == [P.title(k) for k in order], "a row per kind: %r" % (names,))
check(all(fits(r[0]) or r[0].get_y() > 0 for r in rows(p)), "rows stay on the screen's width")
shot("kinds")

# A kind's page: what's found at once, then the slow ones as they're found.
tap(row(p, "Audio out")[0])
check(p.kind == "audio.out" and p.heading.get_text() == "Audio out", "tapping a kind opens its page")
check(texts(p) == ["Headphone jack"], "the I2S jack is there at once: %r" % (texts(p),))
settle(1000)
found = texts(p)
check("Bluetooth speaker" in found and "Earbuds" in found,
      "the Bluetooth ones show up as they're found: %r" % (found,))
buds = row(p, "Earbuds")
check(buds is not None and buds[2] == "Needs pairing", "what needs pairing says so")

# audio.out takes many: tapping adds, tapping again drops, and starts and stops.
tap(row(p, "Headphone jack")[0])
check(reg.chosen("audio.out") == ["i2s:0"], "tapping chooses: %r" % (reg.chosen("audio.out"),))
check(fakes["i2s"].started == ["0"], "the chosen jack is started")
check(row(p, "Headphone jack")[3], "the chosen row has its tick")
tap(row(p, "Bluetooth speaker")[0])
check(reg.chosen("audio.out") == ["i2s:0", "a2dp:spk"],
      "a kind that takes many takes both: %r" % (reg.chosen("audio.out"),))
shot("audio_out")
tap(row(p, "Headphone jack")[0])
check(reg.chosen("audio.out") == ["a2dp:spk"], "and tapping one again drops it: %r" % (reg.chosen("audio.out"),))
check(fakes["i2s"].started == [], "the dropped jack is stopped")

# What's lost while the page is open goes from it.
fakes["a2dp"].remove("buds")
settle(500)
check(row(p, "Earbuds") is None, "an endpoint that goes leaves the page")

tap(p.back)
check(p.kind is None and p.heading.get_text() == "Connections", "back goes to the list of kinds")
check(row(p, "Audio out")[2] == "Bluetooth speaker", "the kind's row says what's chosen: %r" % (row(p, "Audio out")[2],))

# The network takes one: tapping moves the choice.
tap(row(p, "Network")[0])
settle(1000)
tap(row(p, "Ethernet")[0])
check(reg.chosen("net") == ["eth:0"], "a kind that takes one moves to the tap: %r" % (reg.chosen("net"),))
check(row(p, "Ethernet")[3] and not row(p, "Wi-Fi: home")[3], "the tick is on the one chosen")
check(row(p, "Wi-Fi: home")[2] == "Connected", "a connected endpoint says so")

# A network behind a password asks for it, on the keyboard, before it's chosen.
from appkit import keys


def type_in(text):
    for ch in text:
        keys.push(ch)
    settle(200)


tap(row(p, "Wi-Fi: cafe")[0])
check(p.asking is not None and p.typing is not None, "a network that needs its password asks for it")
check(reg.chosen("net") == ["eth:0"], "nothing is chosen while it asks")
if p.typing is not None:
    check(p.typing.get_password_mode(), "the password is hidden as it's typed")
    check(keys.is_shown() and keys.keyboard().get_textarea() == p.typing, "the on-screen keyboard opens on it")
    shot("join")
    type_in("latte")
    keys.push(lv.KEY.ENTER)
    settle(200)
check(p.asking is not None and reg.chosen("net") == ["eth:0"], "a wrong password is refused and asked again")
said = p.asking.get_content().get_child(0).get_text() if p.asking is not None else ""
check("Wrong password" in said, "saying why: %r" % (said,))
if p.typing is not None:
    type_in("espresso")
    tap(p.asking.get_footer().get_child(0))   # Join
check(p.asking is None and reg.chosen("net") == ["wlan:cafe"],
      "the right one joins and is chosen: %r" % (reg.chosen("net"),))
check(not keys.is_shown() and keys.keyboard().get_textarea() is None, "the keyboard closes with the question")
check(row(p, "Wi-Fi: cafe")[2] == "", "and it no longer needs joining: %r" % (row(p, "Wi-Fi: cafe")[2],))
if p.asking is not None:   # a broken join leaves it asking; the checks below need the page
    p._answer("wlan:cafe", False)
tap(row(p, "Ethernet")[0])

# A device that needs pairing and asks nothing typed: a yes pairs it, then a
# choice that would stop something sharing its radio asks first.
tap(row(p, "Phone over Bluetooth")[0])
check(p.asking is not None and p.typing is None, "pairing with nothing to type asks only a yes")
check(reg.chosen("net") == ["eth:0"], "and chooses nothing yet")
if p.asking is not None:
    tap(p.asking.get_footer().get_child(0))   # Pair
check(reg.find("btpan:phone").state == endpointkit.AVAILABLE, "Pair pairs it")
check(p.asking is not None, "a conflict asks before stopping anything")
check(reg.chosen("audio.out") == ["a2dp:spk"] and reg.chosen("net") == ["eth:0"],
      "nothing changes while it asks")
shot("conflict")
if p.asking is not None:
    tap(p.asking.get_footer().get_child(1))   # Cancel
    check(p.asking is None and reg.chosen("net") == ["eth:0"], "Cancel changes nothing")
tap(row(p, "Phone over Bluetooth")[0])
if p.asking is not None:
    tap(p.asking.get_footer().get_child(0))   # Stop it
check(reg.chosen("net") == ["btpan:phone"], "Stop it makes the choice: %r" % (reg.chosen("net"),))
check(reg.chosen("audio.out") == [], "and drops what shared the radio: %r" % (reg.chosen("audio.out"),))
check(row(p, "Phone over Bluetooth")[3] and not row(p, "Ethernet")[3], "the tick moved")

# A start that fails says why on its row.
tap(p.back)
tap(row(p, "MIDI in")[0])
fakes["uart"].fail.append("1")
tap(row(p, "MIDI DIN in")[0])
detail = row(p, "MIDI DIN in")[2]
check("won't start" in detail, "a failed start shows its error: %r" % (detail,))

# Scan asks the providers again.
fakes["uart"].add("2", "MIDI DIN in 2")
fakes["uart"]._dirty = False   # only a scan finds it now
tap(p.scan)
check(row(p, "MIDI DIN in 2") is not None, "Scan finds what's new")

# What the browser asks about itself (a page's "Allow MIDI") pairs at the
# tap, with no question of the picker's, and what it grants is listed.
class _Grant(endpointkit.Provider):
    kind = "midi.out"
    name = "page"

    def __init__(self):
        endpointkit.Provider.__init__(self)
        self.asked = 0

    def scan(self):
        if self.asked:
            return [self.endpoint("synth", "Web synth")]
        return [self.endpoint("allow", "Allow MIDI", endpointkit.NEEDS_PAIRING, caps={"grant": True})]

    def pair(self, endpoint, secret=None):
        self.asked += 1


grant = reg.register(_Grant())
tap(p.back)
tap(row(p, "MIDI out")[0])
tap(row(p, "Allow MIDI")[0])
check(p.asking is None, "the browser's grant opens no question of the picker's")
check(grant.asked == 1, "one tap has the browser ask: %d" % grant.asked)
check(row(p, "Web synth") is not None, "what it grants is listed: %r" % (texts(p),))
if p.asking is not None:
    p._answer("page:allow", False)
reg.unregister(grant)

# A pin is shown, and the device's choice under it is kept.
reg.pin("net", ["eth:0"], "Synth Station")
tap(p.back)
summary = row(p, "Network")[2]
check("pinned by Synth Station" in summary, "the kind's row names the pin: %r" % (summary,))
tap(row(p, "Network")[0])
check(not p.note.has_flag(lv.obj.FLAG.HIDDEN) and "Synth Station" in p.note.get_text(),
      "the kind's page says the app is using its own choice")
check(row(p, "Phone over Bluetooth")[3], "the device's own choice keeps its tick under the pin")
shot("pinned")
reg.unpin("net", "Synth Station")

# An encoder works it: turn to a row, press to choose.
p.show("audio.out")
target = row(p, "Headphone jack")[0]
for _ in range(p.group.get_obj_count()):
    if p.group.get_focused() == target:
        break
    _headless.turn(1)
_headless._wheel["pressed"] = True
_headless.advance(50)
_headless._wheel["pressed"] = False
_headless.advance(50)
if p.asking is not None:
    p.choose("i2s:0", confirm=True)
check(reg.chosen("audio.out") == ["i2s:0"], "a wheel turns to a row and chooses it: %r" % (reg.chosen("audio.out"),))

# A mirror says why it can't run, and where to open it once it does.
import _mirror_standin  # noqa: E402

mirror = reg.register(_mirror_standin.Mirror(password=None))
p.show("cast.target")
detail = row(p, "Browser on this network")[2]
check("WebREPL password" in detail, "an unavailable mirror says why: %r" % (detail,))
mirror.password = "secret"
reg.poll()
p.show("cast.target")
tap(row(p, "Browser on this network")[0])
reg.poll()
p.show("cast.target")
detail = row(p, "Browser on this network")[2]
check(detail == "Open http://192.0.2.7/", "a chosen mirror says where to open it: %r" % (detail,))
mirror.watch()
reg.poll()
p.show("cast.target")
detail = row(p, "Browser on this network")[2]
check(detail.endswith("someone is viewing"), "and whether someone is: %r" % (detail,))
tap(row(p, "Browser on this network")[0])   # tapping the chosen one keeps it
check(reg.chosen("cast.target") == ["mirror:browser"], "tapping it again keeps it on")
reg.select("cast.target", None)
reg.poll()
p.show("cast.target")
detail = row(p, "Browser on this network")[2]
check("http" not in detail, "let go, the address goes: %r" % (detail,))

# Closing hides it and stops listening; the choices stay.
p.close()
check(not p.is_open(), "close hides it")
was = app_group.get_focused()
_headless.turn(1)
check(app_group.get_focused() != was, "the app has its wheel back")
p._dirty = False
fakes["i2s"].add("1", "Line out")
reg.poll()
check(not p._dirty, "a closed picker isn't told of news")
check(reg.chosen("audio.out") == ["i2s:0"], "the choice outlives the picker")

# The Shell opens one over the running app.
from appkit.shell import Shell


class _Launcher:
    home = None


s = Shell(_Launcher())
got = s.open_picker("net")
check(got is s.picker and got.kind == "net" and got.is_open(), "Shell.open_picker opens it at a kind")
got.close()
check(s.open_picker() is got, "and reuses it the next time")
got.close()

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
