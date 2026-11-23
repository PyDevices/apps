# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline on a screen: the box, its audio output, the floor and desk views and the keys.

The package's ``main`` brings this in, so the engine, the kits and the
songs import without LVGL or an audio output.
"""

import gc
import sys

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from multimer import ticks_diff, ticks_ms

import hmilink
from hmilink import local, tcp
from touchkit import ui

from . import ask as askmod
from . import box as boxmod
from . import floor as floormod
from . import footswitch, glyphs, kits, midipedal, remote
from . import page_data

SERVICE_MS = 4       # the pedals and the notes due
UI_MS = 30           # the panel and the screen
CODEC_VOLUME = 85
DESKTOPS = ("win32", "linux", "darwin")
K_SPACE, K_B, K_D, K_K, K_TAB, K_LEFT, K_RIGHT = 32, 98, 100, 107, 9, 1073741904, 1073741903
DESK_SIZE = (640, 400)       # the smallest screen that offers the desk view

state = None  # for the console


def _clock(out):
    """The frame the output renders next: the pump's count where it pumps,
    else the frames a wall clock says have gone since the start."""
    if getattr(out, "pumped", False):
        import audiopump

        return audiopump.now
    start = ticks_ms()
    rate = kits.RATE
    return lambda: ticks_diff(ticks_ms(), start) * rate // 1000


def _cast(box, prefs):
    """The desk view cast where the settings say (`remote.cast_target`), or
    None. A cast that can't start says why on the box and the box plays on."""
    try:
        target = remote.cast_target(prefs)
        if target is None:
            return None
        from . import cast

        caster = cast.start(box.device, target)
        box.cast = target.get("name") or target.get("host") or target["kind"]
        return caster
    except Exception as e:  # noqa: BLE001 - said on the screen
        box.error = "no cast: %s" % (e,)
        return None


def _config(scope):
    """The app's ``config.json`` (the MIDI input and the switches' map), or
    an empty dict where there's no data folder."""
    try:
        from touchkit import settings

        return settings.config(scope, {})
    except Exception:  # noqa: BLE001 - no data folder: start from the defaults
        return {}


def _save_config(scope, config):
    """Keep the map for the next start: learning a switch is rare, so it is
    written when it changes."""
    import json

    try:
        from appkit import data

        with open(data.join(scope.data_dir, "config.json"), "w") as f:
            json.dump(config, f)
    except (OSError, AttributeError, ValueError, ImportError) as e:
        print("backline: couldn't save the settings:", e)


def _midi_in(box, prefs, config):
    """The MIDI input the switches come in on (`midipedal.open_input`), or
    None. One that won't open says why on the box, and the box plays on."""
    try:
        return midipedal.open_input(spec=prefs.get("midi_in") or config.get("midi_in"))
    except Exception as e:  # noqa: BLE001 - said on the screen
        box.error = "no MIDI in: %s" % (e,)
        return None


def _switches(box, prefs, config, scope):
    """The switches on pins the settings name (`footswitch.open_switches`),
    and the function that gives BOOT back to the shell, or None.

    BOOT goes home in the touch shell, so a box whose footswitch is BOOT
    borrows it while it runs. A switch that won't open, or a shell that
    can't lend BOOT, says why on the box, and the box plays on."""
    named = {}
    for key, _which in footswitch.KEYS:
        named[key] = prefs.get(key) or config.get(key)
    give_back = None
    if "boot_button" in named.values():
        shell = getattr(getattr(scope, "launcher", None), "shell", None)
        if getattr(shell, "boot_pin", None) is not None:
            lend = getattr(shell, "lend_boot", None)
            if lend is None:
                box.error = "no footswitch: BOOT goes home in this shell, which can't lend it"
                return [], None
            give_back = lend()
    try:
        return footswitch.open_switches(named, box.pedal), give_back
    except Exception as e:  # noqa: BLE001 - said on the screen
        if give_back is not None:
            give_back()
        box.error = "no footswitch: %s" % (e,)
        return [], None


class Views:
    """The box's own screen: the floor view (``make_floor(on_switch)``), and
    in its place the desk view, made the first time it's asked for by
    ``make_desk(on_switch)``, or never where that is None (a screen under
    `DESK_SIZE`). Each view's ``on_switch`` shows the other, and
    ``on_show()``, when given, runs after either is shown.

    The view going away lets go of its art first (``hide``) and the heap is
    collected, so the one coming back draws into the room it left: the
    screen holds one view's pictures, not both. On an 8 MB board at 800x480
    both at once didn't fit.

    While a switch draws, `switching` is True and `poll` does nothing, so
    the app's timer can't read the panels into a view half drawn. A switch
    made from a tap already runs inside a timer, which holds the others
    off; one called from the console doesn't, and there a pass drew the
    floor's ring out of turn and spent the switch's time on the panels.
    """

    def __init__(self, make_floor, make_desk=None, on_show=None):
        self.shown = "floor"
        self.desk = None
        self.switching = False
        self._make_desk = make_desk
        self._on_show = on_show
        self.floor = make_floor(self._switch("desk") if make_desk is not None else None)

    def _switch(self, which):
        return lambda: self.show(which)

    def show(self, which):
        """Show ``"floor"`` or ``"desk"``."""
        if which == "desk" and self._make_desk is None:
            return
        self.switching = True
        try:
            self.shown = which
            hide = self.floor if which == "desk" else self.desk
            if hide is not None:
                hide.hide()
            gc.collect()
            if which == "desk" and self.desk is None:
                self.desk = self._make_desk(self._switch("floor"))
            (self.desk if which == "desk" else self.floor).show()
        finally:
            self.switching = False
        if self._on_show is not None:
            self._on_show()

    def poll(self, box):
        """One pass of the screen's work: the box's links, then each view's
        panel. Returns False, having done nothing, while a switch draws."""
        if self.switching:
            return False
        box.poll()
        self.floor.poll()
        if self.desk is not None:
            self.desk.poll()
        return True


def start(scope):
    global state
    W, H = scope.size
    status = ui.status(scope)
    try:
        from audiodev import AudioFormat
        import board_peripherals as bp

        power = getattr(bp, "audio_power", None)
        if power is not None:
            power(True, volume=CODEC_VOLUME)
        live = {"latency": "low"} if sys.platform in DESKTOPS else {}
        out = bp.audio_out(AudioFormat(kits.RATE, kits.CHANNELS, 16), **live)
    except Exception as e:  # noqa: BLE001 - said on the screen
        ui.missing(scope, "no audio", "Backline needs an audio output: %s" % (e,))
        return
    prefs = scope.store()
    config = _config(scope)
    # The chat server a song is asked for from: settings.json in the app's
    # data folder, as Huey keeps its own.
    ask_settings, trouble = None, None
    try:
        data = scope.data_dir
        ask_settings = askmod.load_settings(data + "/settings.json")
    except (ValueError, AttributeError) as e:
        data, trouble = None, "settings: %s" % (e,)
    try:
        box = boxmod.Box(_clock(out), song=prefs.get("song"), kit=prefs.get("kit"),
                         pedal_map=prefs.get("pedals") or config.get("pedals"), worker=getattr(scope, "worker", None),
                         ask_settings=ask_settings, user_songs=data + "/songs" if data else None)
        box.error = box.error or trouble
    except Exception as e:  # noqa: BLE001
        out.close()
        ui.missing(scope, "can't start", "Backline: %s" % (e,))
        return
    out.attach(scope)
    out.play(box.bus.output, loop=True)
    listener = box.device.add(local.serve())
    port = remote.listen_port(prefs)
    if port:
        try:
            box.device.add(tcp.serve(port, page=page_data.page()))
        except OSError as e:
            box.error = "desks can't join on port %d: %s" % (port, e)
    name = remote.ble_name(prefs, scope.data_dir)
    if name:
        try:
            from hmilink import ble

            box.device.add(ble.serve(name))
        except Exception as e:  # noqa: BLE001 - said on the screen
            box.error = "no desks over Bluetooth: %s" % (e,)
    panel = hmilink.Panel(local.connect(listener))
    box.poll()
    panel.poll()
    caster = _cast(box, prefs)
    box.midi_in = _midi_in(box, prefs, config)
    box.switches, give_boot_back = _switches(box, prefs, config, scope)
    kept = [box.midi.saved()]
    can_desk = W >= DESK_SIZE[0] and H >= DESK_SIZE[1]
    desk_panel = []

    def make_desk(on_switch):
        from .desk import Desk

        desk_panel.append(hmilink.Panel(local.connect(listener)))
        box.poll()
        desk_panel[0].poll()
        return Desk(scope.root, (W, H), desk_panel[0], on_switch=on_switch)

    def on_show():
        if own_status:
            status.move_foreground()

    views = Views(lambda on_switch: floormod.Floor(scope.root, (W, H), panel, on_switch=on_switch),
                  make_desk if can_desk else None, on_show)
    floor = views.floor
    show = views.show
    own_status = getattr(scope, "status", None) is None
    if own_status:
        status.move_foreground()
    state = {"box": box, "floor": floor, "out": out, "views": views, "show": show, "cast": caster}
    # On the status bar while a song plays: the part and the tempo. A tap
    # brings the floor view back to the front.
    bar = getattr(scope, "bar", None)
    if bar is not None:
        from appkit.bar import Item

        bar.add(Item("backline", lambda: glyphs.bar_reading(box.telemetry()), on_click=lambda: show("floor")), scope)
    held = set()

    def service(_t):
        box.service()

    def tick(_t):
        if not views.poll(box):
            return
        if caster is not None:
            caster.step()
        t = box.telemetry()
        prefs["song"] = box.songs[box.song_index][0]
        prefs["kit"] = box.engine.kit.spec if box.engine.kit is not None else None
        pedals = box.midi.saved()
        if pedals != kept[0]:
            kept[0] = config["pedals"] = pedals
            _save_config(scope, config)
        prefs["pedals"] = pedals
        # The shell's header has room for the song's place in the list; a
        # label of the app's own, over the view, says only what went wrong.
        status.set_text(t["error"] if own_status else
                        t["error"] or ("%s  •  %d of %d" % (t["song"], t["song_index"] + 1, t["songs"])
                                       if t["song_index"] >= 0 else t["song"]))

    def key_down(e):
        k = getattr(e, "key", None)
        if views.desk is not None and views.desk.typing():
            return  # the keys are words in the prompt, not pedals
        if k in held:
            return
        held.add(k)
        if k == K_SPACE:
            floor.pedal(0, True)
        elif k == K_B:
            floor.pedal(1, True)
        elif k == K_K:
            panel.command("kit", step=1)
        elif k in (K_D, K_TAB):
            show("floor" if views.shown == "desk" else "desk")
        elif k in (K_LEFT, K_RIGHT) and not box.engine.transport["playing"]:
            panel.command("song", step=1 if k == K_RIGHT else -1)

    def key_up(e):
        k = getattr(e, "key", None)
        if k not in held:
            return  # went down while the prompt had the keys
        held.discard(k)
        if k == K_SPACE:
            floor.pedal(0, False)
        elif k == K_B:
            floor.pedal(1, False)

    try:
        import events

        scope.on(events.KEYDOWN, key_down)
        scope.on(events.KEYUP, key_up)
    except ImportError:
        pass

    def close():
        global state
        state = None
        try:
            out.stop()
        except Exception:  # noqa: BLE001
            pass
        out.detach()
        out.close()
        panel.close()
        if caster is not None:
            caster.close()
        for p in desk_panel:
            p.close()
        box.close()  # after the output, so it never pulls a closed kit
        if give_boot_back is not None:
            give_boot_back()
        try:
            power = getattr(bp, "audio_power", None)
            if power is not None:
                power(False)
        except Exception:  # noqa: BLE001
            pass

    scope.on_close(close)
    scope.every(SERVICE_MS, service)
    scope.every(UI_MS, tick)
