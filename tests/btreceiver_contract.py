# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bluetooth Receiver's screen against its demo phone, in one interpreter.

    python tests/btreceiver_contract.py   (from tests/, with lib/ and the root on the path)

The app runs under the shell's header on an 800 x 480 display in memory, with
the demo's pretend phone in place of btclassic. Each state is checked through
the screen's own widgets: what shows, what's hidden, and what the buttons and
the slider send back. Prints PASS or FAIL per check, then ALL PASSED.
"""

import sys

sys.path.insert(0, "..")
sys.path.insert(0, "../lib")  # ahead of tests/, whose appkit folder would hide the real one

import lvgl as lv  # noqa: E402

import _headless  # noqa: E402

SW, SH = 800, 480
_headless.display(SW, SH)
_headless.pointer()

from touchkit import ui  # noqa: E402
from touchkit.shell import TouchShell  # noqa: E402

ui.apply_theme()


class _NS:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


_shell = _NS(launcher=_NS(home="home", info={"btreceiver": {"title": "Bluetooth Receiver"}}))

import apps.btreceiver as app  # noqa: E402
from apps.btreceiver import demo  # noqa: E402
from apps.btreceiver import screen as screenmod  # noqa: E402

failures = []


def check(name, ok, why=""):
    if ok:
        print("PASS " + name)
    else:
        print("FAIL %s: %s" % (name, why))
        failures.append(name)


class Scope:
    """What the launcher's shell hands an app: a root under the header, timers."""

    name = "btreceiver"

    def __init__(self):
        self.scr = ui.plain(lv.obj(lv.screen_active()))
        self.scr.set_size(SW, SH)
        self.scr.update_layout()
        self.root = TouchShell.make_root(_shell, self)
        self.size = (SW, SH - ui.HEADER)
        self.rect = (0, ui.HEADER, SW, SH - ui.HEADER)
        self.timers = []
        self.closers = []

    def screen(self):
        return self.scr

    def every(self, ms, cb):
        self.timers.append(cb)

    def on_close(self, fn):
        self.closers.append(fn)

    def run(self):
        for cb in list(self.timers):
            cb(None)
        _headless.advance(40)

    def close(self):
        for fn in self.closers:
            fn()
        self.scr.delete()


def opened(state):
    """The app open on a demo phone held in *state*: ``(scope, sink, screen)``."""
    sink = demo.DemoSink(state)
    app._open_sink = lambda: (demo.DemoRadio("kitchen-speaker"), sink, demo, True)
    scope = Scope()
    app.main(scope)
    scope.run()
    return scope, sink, app.state["screen"]


def shown(obj):
    return not obj.has_flag(lv.obj.FLAG.HIDDEN)


def text(lbl):
    return lbl.get_text() if shown(lbl) else None


def tap(obj):
    a = lv.area_t()
    obj.get_coords(a)
    x, y = (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2
    _headless.touch(x, y, True, 40)
    _headless.touch(x, y, False, 40)


# ---- Waiting to be paired -----------------------------------------------------

scope, sink, scr = opened("pairing")
check("pairing shows the board's name as the title", text(scr.title) == "kitchen-speaker", text(scr.title))
check("pairing says it's ready to pair", text(scr.eyebrow) == "READY TO PAIR", text(scr.eyebrow))
check("pairing shows the steps and the PIN", shown(scr.steps) and "0000" in scr.pin.get_text(), scr.pin.get_text())
check("pairing hides the transport and the progress",
      not shown(scr.play.obj) and not shown(scr.vol) and not shown(scr.track) and not shown(scr.bars.obj))
check("pairing shows the rings, not the cover", shown(scr.pair) and not shown(scr.cover_box))
check("pairing hides shuffle and repeat", not shown(scr.shuffle) and not shown(scr.repeat))
scope.close()

# ---- Connected, nothing playing -----------------------------------------------

scope, sink, scr = opened("idle")
check("idle names the phone as the title", text(scr.title) == "Galaxy S21", text(scr.title))
check("idle says it's connected", text(scr.eyebrow) == "CONNECTED", text(scr.eyebrow))
check("idle doesn't repeat the phone's name above it", scr.src_name.get_text() == "", scr.src_name.get_text())
check("idle offers play, and no progress", shown(scr.play.obj) and not shown(scr.track))
check("idle shows the battery too, here charging", shown(scr.battery) and scr.battery_state == "external",
      str(scr.battery_state))
sink.title = "Not Provided"  # what Android sends with nothing playing
sink._bits |= demo.TRACK
scope.run()
check("Android's \"Not Provided\" title still shows idle", text(scr.title) == "Galaxy S21", text(scr.title))
sink.title = ""
tap(scr.play.obj)
scope.run()
check("play on the idle screen starts the phone", sink.playing and text(scr.title) == "Neon Tides", text(scr.title))
scope.close()

# ---- Playing ------------------------------------------------------------------

scope, sink, scr = opened("playing")
check("the title, artist and album show", (text(scr.title), text(scr.artist), text(scr.album))
      == ("Neon Tides", "Halcyon Drive", "Afterglow Coast"), "%s %s %s" % (text(scr.title), text(scr.artist), text(scr.album)))
check("the track number, count and genre show", text(scr.meta) == "TRACK 3 OF 11  /  SYNTHWAVE", text(scr.meta))
check("the status shows", text(scr.eyebrow) == "NOW PLAYING", text(scr.eyebrow))
check("the sender's name heads the column", scr.src_name.get_text() == "Galaxy S21", scr.src_name.get_text())
check("the phone's battery shows when it reports one", shown(scr.battery) and scr.battery_state == "normal",
      str(scr.battery_state))
sink.battery = "warning"
sink._bits |= demo.PEER
scope.run()
check("a low battery shows in amber",
      scr.battery.get_style_image_recolor(0).to_int() & 0xFFFFFF == screenmod.AMBER,
      "%06x" % (scr.battery.get_style_image_recolor(0).to_int() & 0xFFFFFF))
check("the codec, rate and channels show", text(scr.codec) == "SBC  /  44.1 kHz  /  Joint stereo", text(scr.codec))
check("the position and length show", text(scr.t_pos) == "1:42" and text(scr.t_len) == "4:12",
      "%s %s" % (text(scr.t_pos), text(scr.t_len)))
check("the cover shows, and gives the screen its colour", shown(scr.art) and scr.accent != screenmod.TEAL,
      "%06x" % scr.accent)


def lit(icon):
    return icon.get_style_image_recolor(0).to_int() & 0xFFFFFF == scr.accent


def volume_y():
    return scr.vol.get_y()


check("shuffle and repeat show when the phone reports them", shown(scr.shuffle) and shown(scr.repeat))
check("shuffle on is lit in the accent, repeat off is not", lit(scr.shuffle_icon) and not lit(scr.repeat_icon))
check("the volume moves under them", volume_y() == screenmod.MODES[2], str(volume_y()))
tap(scr.repeat)
scope.run()
check("repeat goes off to all on the phone, and lights", sink.repeat == "all" and lit(scr.repeat_icon), str(sink.repeat))
tap(scr.repeat)
scope.run()
check("then all to single, marked with a 1", sink.repeat == "single" and shown(scr.repeat_one), str(sink.repeat))
tap(scr.repeat)
scope.run()
check("then single back to off", sink.repeat == "off" and not lit(scr.repeat_icon) and not shown(scr.repeat_one),
      str(sink.repeat))
tap(scr.shuffle)
scope.run()
check("shuffle turns off on the phone, and dims", sink.shuffle == "off" and not lit(scr.shuffle_icon), str(sink.shuffle))
sink.shuffle = "all"
sink._bits |= demo.SETTINGS
scope.run()
check("shuffle turned on at the phone lights here", lit(scr.shuffle_icon))
tap(scr.play.obj)
scope.run()
check("pause pauses the phone and says so", not sink.playing and text(scr.eyebrow) == "PAUSED", text(scr.eyebrow))
tap(scr.next.obj)
scope.run()
check("next moves the phone on a track", text(scr.title) == "Glass Orchard", text(scr.title))
sink.volume = 40
scope.run()
check("the slider follows the phone's volume", scr.vol.get_value() == 40, str(scr.vol.get_value()))
a = lv.area_t()
scr.vol.get_coords(a)
y = (a.y1 + a.y2) // 2
_headless.touch(a.x2 - 2, y, True, 40)
_headless.touch(a.x2 - 1, y, True, 40)
_headless.touch(a.x2 - 1, y, False, 40)
check("dragging the slider sets the phone's volume", sink.volume > 100, str(sink.volume))
sink.title, sink.artist, sink.album, sink.genre = "Only a title", "", "", ""
sink.track_number = sink.track_count = None
sink._bits |= demo.TRACK
scope.run()
check("a field the sender leaves empty isn't shown",
      text(scr.title) == "Only a title" and text(scr.artist) is None and text(scr.album) is None and text(scr.meta) is None,
      "%s %s %s %s" % (text(scr.title), text(scr.artist), text(scr.album), text(scr.meta)))
scope.close()
check("closing the app lets the phone go", not sink.connected)

# ---- A phone that doesn't report its modes -----------------------------------

scope, sink, scr = opened("long")
check("a phone that reports no modes shows no shuffle or repeat", not shown(scr.shuffle) and not shown(scr.repeat))
check("and the volume stays beside the play button",
      scr.vol.get_y() == screenmod.VOLUME[1], str(scr.vol.get_y()))
scope.close()

# ---- A track with no cover ----------------------------------------------------

scope, sink, scr = opened("nocover")
check("with no cover, the placeholder shows", not shown(scr.art) and shown(scr.note))
check("a phone that reports no battery shows none", not shown(scr.battery))
check("with no cover, the colour goes back to the default", scr.accent == screenmod.TEAL, "%06x" % scr.accent)
check("a podcast's length shows", text(scr.t_len) == "45:12", text(scr.t_len))
check("a length over an hour reads h:mm:ss", screenmod.clock(3725000) == "1:02:05", screenmod.clock(3725000))
scope.close()

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
