# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline on a screen: the box, its audio output, the floor view and the keys.

The package's ``main`` brings this in, so the engine, the kits and the
songs import without LVGL or an audio output.
"""

import sys

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from multimer import ticks_diff, ticks_ms

import hmilink
from hmilink import local
from touchkit import ui

from . import box as boxmod
from . import floor as floormod
from . import kits

SERVICE_MS = 4       # the pedals and the notes due
UI_MS = 30           # the panel and the screen
CODEC_VOLUME = 85
DESKTOPS = ("win32", "linux", "darwin")
K_SPACE, K_B, K_K, K_LEFT, K_RIGHT = 32, 98, 107, 1073741904, 1073741903

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
    panel = hmilink.Panel(local.connect(listener))
    box.poll()
    panel.poll()
    floor = floormod.Floor(scope.root, (W, H), panel)
    own_status = getattr(scope, "status", None) is None
    if own_status:
        status.move_foreground()
    state = {"box": box, "floor": floor, "out": out}
    held = set()

    def service(_t):
        box.service()

    def tick(_t):
        box.poll()
        floor.poll()
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
