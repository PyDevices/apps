# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline on a screen: the box, its audio output, the floor and desk views and the keys.

The package's ``main`` brings this in, so the engine, the kits and the
songs import without LVGL or an audio output.
"""

import sys

import lvgl as lv

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from multimer import ticks_diff, ticks_ms

import hmilink
from hmilink import local, tcp
from touchkit import ui

from . import box as boxmod
from . import floor as floormod
from . import kits, remote
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

        return cast.start(box.device, target)
    except Exception as e:  # noqa: BLE001 - said on the screen
        box.error = "no cast: %s" % (e,)
        return None


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
    try:
        box = boxmod.Box(_clock(out), song=prefs.get("song"), kit=prefs.get("kit"))
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
    panel = hmilink.Panel(local.connect(listener))
    box.poll()
    panel.poll()
    caster = _cast(box, prefs)
    views = {"floor": None, "desk": None, "desk_panel": None, "shown": "floor"}
    can_desk = W >= DESK_SIZE[0] and H >= DESK_SIZE[1]

    def show(which):
        """Show the floor or the desk view; the desk is made the first time."""
        if which == "desk" and not can_desk:
            return
        if which == "desk" and views["desk"] is None:
            from .desk import Desk

            views["desk_panel"] = hmilink.Panel(local.connect(listener))
            box.poll()
            views["desk_panel"].poll()
            views["desk"] = Desk(scope.root, (W, H), views["desk_panel"], on_switch=lambda: show("floor"))
        views["shown"] = which
        hide, keep = (views["floor"], views["desk"]) if which == "desk" else (views["desk"], views["floor"])
        if hide is not None:
            hide.base.add_flag(lv.obj.FLAG.HIDDEN)
        keep.base.remove_flag(lv.obj.FLAG.HIDDEN)
        if own_status:
            status.move_foreground()

    floor = floormod.Floor(scope.root, (W, H), panel, on_switch=(lambda: show("desk")) if can_desk else None)
    views["floor"] = floor
    own_status = getattr(scope, "status", None) is None
    if own_status:
        status.move_foreground()
    state = {"box": box, "floor": floor, "out": out, "views": views, "show": show, "cast": caster}
    held = set()

    def service(_t):
        box.service()

    def tick(_t):
        box.poll()
        floor.poll()
        if views["desk"] is not None:
            views["desk"].poll()
        if caster is not None:
            caster.step()
        t = box.telemetry()
        prefs["song"] = box.songs[box.song_index][0]
        prefs["kit"] = box.engine.kit.spec if box.engine.kit is not None else None
        # The shell's header has room for the song's place in the list; a
        # label of the app's own, over the view, says only what went wrong.
        status.set_text(t["error"] if own_status else
                        t["error"] or "%s  •  %d of %d" % (t["song"], t["song_index"] + 1, t["songs"]))

    def key_down(e):
        k = getattr(e, "key", None)
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
            show("floor" if views["shown"] == "desk" else "desk")
        elif k in (K_LEFT, K_RIGHT) and not box.engine.transport["playing"]:
            panel.command("song", step=1 if k == K_RIGHT else -1)

    def key_up(e):
        k = getattr(e, "key", None)
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
        if views["desk_panel"] is not None:
            views["desk_panel"].close()
        box.close()  # after the output, so it never pulls a closed kit
        try:
            power = getattr(bp, "audio_power", None)
            if power is not None:
                power(False)
        except Exception:  # noqa: BLE001
            pass

    scope.on_close(close)
    scope.every(SERVICE_MS, service)
    scope.every(UI_MS, tick)
