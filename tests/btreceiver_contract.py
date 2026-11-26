# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bluetooth Receiver's screen against its demo phone, in one interpreter.

    python tests/btreceiver_contract.py   (from tests/, with lib/ and the root on the path)

The app runs under the shell's header on an 800 x 480 display in memory, with
the demo's pretend phone and hands-free unit in place of btclassic. Each state is checked through
the screen's own widgets: what shows, what's hidden, and what the buttons and
the slider send back. Prints PASS or FAIL per check, then ALL PASSED.
"""

import os
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


DATA = "_btreceiver_data"  # the app's data folder, in tests/, removed at the end


def forget_settings():
    try:
        os.remove(DATA + "/config.json")
    except OSError:
        pass


try:
    os.mkdir(DATA)
except OSError:
    pass
forget_settings()


class Scope:
    """What the launcher's shell hands an app: a root under the header, timers."""

    name = "btreceiver"
    data_dir = DATA

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


opens = []  # each hands-free unit the app opened
outs = []  # each speaker the app opened


class Out:
    """Stands in for the board's ``audio_out``: what it was handed to play."""

    def __init__(self, rate):
        self.rate = rate
        self.sample = None
        self.closed = False
        outs.append(self)

    def play(self, sample):
        self.sample = sample

    def stop(self):
        pass

    def close(self):
        self.closed = True


app._speaker = Out


def opened(state, call_audio=True, calls=True):
    """The app open on a demo phone held in *state*: ``(scope, sink, screen)``.
    *calls* is the calls setting, saved before it opens (None: left as it
    is). The phone's hands-free unit is ``app.state["hf"]``, None with the
    setting off; *call_audio* False is a board that can't take a call's
    audio."""
    sink = demo.DemoSink(state)

    def handsfree(bt, s, bits):
        hf = demo.DemoHandsFree(sink, call_audio=call_audio)
        opens.append(hf)
        return hf

    app._open_sink = lambda: (demo.DemoRadio("kitchen-speaker"), sink, demo, True)
    app._open_handsfree = handsfree
    scope = Scope()
    if calls is not None:
        app._save_config(scope, {"calls": calls})
    app.main(scope)
    scope.run()
    return scope, sink, app.state["screen"]


def colour(img):
    return img.get_style_image_recolor(0).to_int() & 0xFFFFFF


def battery_is(scope, scr, hf, level):
    hf.battery = level
    hf._bits |= demo.PHONE
    scope.run()
    return scr.battery_state == level


def lit(scr):
    return sum(1 for b in scr.signal_bars if b.get_style_bg_opa(0) == lv.OPA.COVER)


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
check("pairing shows no battery or signal: no phone yet", not shown(scr.battery) and not shown(scr.signal))
check("pairing shows no call card", not shown(scr.card))
scope.close()

# ---- Connected, nothing playing -----------------------------------------------

scope, sink, scr = opened("idle")
check("idle names the phone as the title", text(scr.title) == "Galaxy S21", text(scr.title))
check("idle says it's connected", text(scr.eyebrow) == "CONNECTED", text(scr.eyebrow))
check("idle doesn't repeat the phone's name above it", scr.src_name.get_text() == "", scr.src_name.get_text())
check("idle offers play, and no progress", shown(scr.play.obj) and not shown(scr.track))
check("idle shows the phone's battery from its hands-free link", shown(scr.battery) and scr.battery_state == 3,
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
hf = app.state["hf"]
check("the phone's battery shows, at its level", shown(scr.battery) and scr.battery_state == 4,
      str(scr.battery_state))
check("a battery above 1 of 5 is grey", colour(scr.battery) == screenmod.MUTED, "%06x" % colour(scr.battery))
for level in (5, 2):
    check("a battery of %d of 5 shows and is grey" % level,
          battery_is(scope, scr, hf, level) and shown(scr.battery) and colour(scr.battery) == screenmod.MUTED,
          "%s %06x" % (scr.battery_state, colour(scr.battery)))
for level in (1, 0):
    check("a battery of %d of 5 shows in amber" % level,
          battery_is(scope, scr, hf, level) and shown(scr.battery) and colour(scr.battery) == screenmod.AMBER,
          "%s %06x" % (scr.battery_state, colour(scr.battery)))
check("each battery level has its own icon", len(set(screenmod.BATTERY)) == 6)
check("the phone's signal shows as bars", shown(scr.signal) and lit(scr) == 2, str(lit(scr)))
hf.service = False
hf._bits |= demo.PHONE
scope.run()
check("no service empties the bars and says so", lit(scr) == 0 and scr.warn.get_text() == "No service",
      scr.warn.get_text())
hf.service = True
hf._bits |= demo.PHONE
scope.run()
check("service back, the bars and the note follow", lit(scr) == 2 and scr.warn.get_text() == "", scr.warn.get_text())
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
check("the volume moves under them", volume_y() == scr.lay.volume[4], str(volume_y()))
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
      scr.vol.get_y() == scr.lay.volume[2], str(scr.vol.get_y()))
scope.close()

# ---- A track with no cover ----------------------------------------------------

scope, sink, scr = opened("nocover")
check("with no cover, the placeholder shows", not shown(scr.art) and shown(scr.note))
check("a sender with no hands-free link shows no battery or signal", not shown(scr.battery) and not shown(scr.signal))
check("with no cover, the colour goes back to the default", scr.accent == screenmod.TEAL, "%06x" % scr.accent)
check("a podcast's length shows", text(scr.t_len) == "45:12", text(scr.t_len))
check("a length over an hour reads h:mm:ss", screenmod.clock(3725000) == "1:02:05", screenmod.clock(3725000))
scope.close()

# ---- A call ------------------------------------------------------------------

scope, sink, scr = opened("incoming")
hf = app.state["hf"]
check("an incoming call shows the card", shown(scr.card) and text(scr.call_word) == "INCOMING CALL", text(scr.call_word))
check("the card shows the caller's number", text(scr.caller) == demo.CALLER, text(scr.caller))
check("the card names the phone", text(scr.call_phone) == "on Galaxy S21", text(scr.call_phone))
check("ringing offers answer and decline, not hang up",
      shown(scr.answer.obj) and shown(scr.decline.obj) and not shown(scr.hang.obj) and not shown(scr.mute.obj))
check("the battery shows over the card", shown(scr.battery) and scr.battery_state == 4, str(scr.battery_state))
check("the phone paused its music for the call", not sink.playing)
tap(scr.answer.obj)
scope.run()
check("answer answers the call", hf.call == "active" and text(scr.call_word) == "ON A CALL", text(scr.call_word))
check("the call's audio comes to the board", hf.audio and app.state["talking"])
check("an answered call offers mute, the phone and hang up",
      shown(scr.hang.obj) and shown(scr.mute.obj) and shown(scr.route.obj) and not shown(scr.answer.obj))
check("an answered call shows its time", (text(scr.call_time) or "").startswith("0:"), str(text(scr.call_time)))
tap(scr.mute.obj)
scope.run()
check("mute turns the microphones off", app.state["muted"] and scr.call_labels[0].get_text() == "Unmute",
      scr.call_labels[0].get_text())
tap(scr.mute.obj)
scope.run()
check("and on again", not app.state["muted"] and scr.call_labels[0].get_text() == "Mute")
tap(scr.route.obj)
scope.run()
check("use phone hands the call's audio back", not hf.audio and not app.state["talking"]
      and text(scr.call_note) == "Talking on the phone", str(text(scr.call_note)))
check("with the audio on the phone, mute is off and the button offers the speaker",
      not scr.mute.enabled and scr.call_labels[1].get_text() == "Use speaker", scr.call_labels[1].get_text())
tap(scr.route.obj)
scope.run()
check("use speaker brings it back", hf.audio and app.state["talking"])
tap(scr.hang.obj)
scope.run()
check("hang up ends the call and the card goes", hf.call == "idle" and not shown(scr.card))
check("the music plays again after the call", sink.playing and not app.state["talking"])
check("the player is back with its track", text(scr.title) == "Neon Tides" and text(scr.eyebrow) == "NOW PLAYING",
      "%s %s" % (text(scr.title), text(scr.eyebrow)))
scope.close()

scope, sink, scr = opened("incoming")
hf = app.state["hf"]
tap(scr.decline.obj)
scope.run()
check("decline rejects the call and the card goes", hf.call == "idle" and not shown(scr.card))
check("the music plays again after a declined call", sink.playing)
scope.close()

scope, sink, scr = opened("call")
hf = app.state["hf"]
check("a call answered on the board shows the card with its time", shown(scr.card) and text(scr.call_word) == "ON A CALL"
      and text(scr.call_time) is not None)
scope.close()
check("closing the app during a call lets the hands-free link go", not hf.connected and not hf.audio)

# ---- A call on a board that can't take its audio ------------------------------

scope, sink, scr = opened("incoming", call_audio=False)
hf = app.state["hf"]
check("without call audio, the card still rings with answer and decline",
      shown(scr.card) and shown(scr.answer.obj) and shown(scr.decline.obj))
check("without call audio, the card says the audio stays on the phone",
      text(scr.call_note) == "The call's audio stays on the phone", str(text(scr.call_note)))
tap(scr.answer.obj)
scope.run()
check("without call audio, answer answers and the audio stays on the phone",
      hf.call == "active" and not hf.audio and not app.state["talking"] and app.state["call_out"] is None)
check("without call audio, an answered call offers hang up only",
      shown(scr.hang.obj) and not shown(scr.mute.obj) and not shown(scr.route.obj)
      and not shown(scr.call_labels[0]) and not shown(scr.call_labels[1]) and shown(scr.call_labels[2]))
check("without call audio, the call still shows its time", (text(scr.call_time) or "").startswith("0:"),
      str(text(scr.call_time)))
tap(scr.hang.obj)
scope.run()
check("without call audio, hang up ends the call and the music plays again",
      hf.call == "idle" and not shown(scr.card) and sink.playing)
scope.close()

# ---- The calls setting -------------------------------------------------------

forget_settings()
del opens[:]
scope, sink, scr = opened("playing", calls=None)
sw = app.state["switch"]
check("the calls setting starts off", not sw.has_state(lv.STATE.CHECKED) and not app.state["config"]["calls"])
check("its label says what it does", screenmod.CALLS_LABEL in [
    sw.get_parent().get_child(i).get_text() for i in range(sw.get_parent().get_child_count())
    if sw.get_parent().get_child(i).has_class(lv.label_class)])
check("it sits in the header", sw.get_parent() is scope.header)
check("off, no hands-free link is opened", app.state["hf"] is None and not opens, str(len(opens)))
check("off, the player's battery shows", shown(scr.battery) and scr.battery_state == "normal", str(scr.battery_state))
sink.battery = "warning"
sink._bits |= demo.PEER
scope.run()
check("off, a low player battery shows in amber", colour(scr.battery) == screenmod.AMBER,
      "%06x" % colour(scr.battery))
check("off, no signal shows", not shown(scr.signal))
sink.battery = "normal"
sink._bits |= demo.PEER
tap(sw)
scope.run()
hf = app.state["hf"]
check("on, the hands-free link opens", hf is not None and hf.connected and len(opens) == 1, str(len(opens)))
check("on, the phone's battery and signal show", scr.battery_state == 4 and shown(scr.signal),
      str(scr.battery_state))
check("on, the setting is saved", app._load_config(scope)["calls"] is True)
tap(sw)
scope.run()
check("off again, the link goes", app.state["hf"] is None and not hf.connected)
check("off again, the player's battery is back and the signal goes",
      scr.battery_state == "normal" and not shown(scr.signal), str(scr.battery_state))
check("off again, the setting is saved", app._load_config(scope)["calls"] is False)
tap(sw)
scope.run()
scope.close()
scope, sink, scr = opened("playing", calls=None)
check("the setting is kept when the app opens again",
      app.state["switch"].has_state(lv.STATE.CHECKED) and app.state["hf"] is not None)
scope.close()
forget_settings()
scope, sink, scr = opened("nocover", calls=False)
check("a sender that reports no battery shows none", not shown(scr.battery))
scope.close()

# ---- Chimes -------------------------------------------------------------------

from multimer import ticks_add, ticks_ms  # noqa: E402

try:
    import audiomixer  # noqa: F401
    import synthio  # noqa: F401
    CAN_MIX = True
except ImportError:
    CAN_MIX = False
    print("NOTE: no audiomixer or synthio here: the chimes' mixer isn't checked")


def played():
    return list(app.state["chimes"].played)


def later(key, ms):
    """Move the app's *key* time back *ms*, as if that long had passed."""
    app.state[key] = ticks_add(ticks_ms(), -ms)


forget_settings()
del outs[:]
scope, sink, scr = opened("incoming")
hf = app.state["hf"]
check("a ringing call chimes", played() == ["call"], str(played()))
if CAN_MIX:
    check("the chime opens the speaker on the chimes' mixer, at 44.1 kHz with no music yet",
          len(outs) == 1 and outs[0].rate == 44100 and outs[0].sample is app.state["chimes"].mixer
          and app.state["chimes"].synth is not None, str([(o.rate, o.sample) for o in outs]))
scope.run()
check("it doesn't chime again at once", played() == ["call"], str(played()))
later("rang", app.RING_MS)
scope.run()
check("it chimes again while the call still rings", played() == ["call", "call"], str(played()))
tap(scr.answer.obj)
scope.run()
later("rang", app.RING_MS)
scope.run()
check("an answered call stops the chimes", played() == ["call", "call"], str(played()))
scope.close()

scope, sink, scr = opened("incoming")
hf = app.state["hf"]
hf.in_band_ring = True
later("rang", app.RING_MS)
scope.run()
check("a phone that rings in band still chimes: it can send silence", played() == ["call", "call"],
      str(played()))
scope.close()

scope, sink, scr = opened("incoming", call_audio=False)
hf = app.state["hf"]
hf.in_band_ring = True
later("rang", app.RING_MS)
scope.run()
check("a board that can't take call audio chimes even for an in-band phone", played() == ["call", "call"],
      str(played()))
scope.close()

scope, sink, scr = opened("call")
msgs = app.state["msgs"]
later("map_asked", app.MAP_WAIT_MS)
scope.run()
scope.run()
msgs.arrive()
scope.run()
check("a text doesn't chime over a call's audio on the board", app.state["talking"] and played() == [],
      str(played()))
scope.close()

scope, sink, scr = opened("incoming", calls=False)
check("with the calls setting off there's no call to chime for", played() == [], str(played()))
scope.close()

del outs[:]
scope, sink, scr = opened("text", calls=False)
msgs = app.state["msgs"]
check("the message service opens with the calls setting off", msgs is not None and not msgs.connected)
later("map_asked", app.MAP_WAIT_MS)
scope.run()
scope.run()
check("it connects to the phone and asks for its reports", msgs.connected and msgs.notifying)
msgs.arrive()
scope.run()
check("a new text chimes once", played() == ["text"], str(played()))
if CAN_MIX:
    check("the music and the chimes share one mixer", len(outs) == 1 and outs[0].sample is app.state["chimes"].mixer,
          str(len(outs)))
msgs.arrive()
msgs.arrive()
scope.run()
check("two texts together chime once", played() == ["text", "text"], str(played()))
msgs.arrive("telecom/msg/sent")
scope.run()
check("a text the phone sent doesn't chime", played() == ["text", "text"], str(played()))
scope.close()
check("closing the app lets the message service go", not msgs.connected)

scope, sink, scr = opened("nocover", calls=False)
msgs = app.state["msgs"]
for _ in range(app.MAP_TRIES + 2):
    later("map_asked", app.MAP_PENDING_MS)
    scope.run()
check("a sender with no message service is asked a few times, then let be",
      not msgs.connected and app.state["map_tries"] == app.MAP_TRIES, str(app.state["map_tries"]))
scope.close()

forget_settings()
scope = Scope()
app._save_config(scope, {"texts": False})
scope.close()
scope, sink, scr = opened("text", calls=None)
check("texts off in config.json leaves the phone's messages alone", app.state["msgs"] is None)
scope.close()

forget_settings()
os.rmdir(DATA)

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
