# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Effects rig: the rig's drive -> chorus -> delay, with its pedals on screen.

What the PC plays to the board's USB sound card goes through the pedals and
out of the 3.5 mm jack; a USB MIDI keyboard's knobs move them
(the map is the rig's own ``KNOBS``). Tap a pedal's switch to turn it on or
off, or Bypass for the whole chain.

The rig's audio loop copies USB audio into the pedals' ring every
millisecond, in Python, so it runs in the program's foreground loop
(``scope.foreground``; ``main.py`` ends in ``appkit.serve()``) rather than
from a timer: no timer can come round that often. At the REPL, after a
Ctrl-C, the pedals wait until ``appkit.serve()`` runs again. The screen works around
the loop: LVGL reads the touch panel every 100 ms instead of 33 (each read
leaves garbage, and a collection stalls the loop), and a label is redrawn
only when its value changes.

It needs the rig's ``rig.py`` and ``rig_inputs.py`` in ``/lib``.
"""

import lvgl as lv

from devkit import shell, ui

TOUCH_MS = 100
REFRESH_MS = 250


current = None  # the running Rig, for the console


class _Stop(Exception):
    pass


def _knob_rows(rig):
    """Per pedal, its knobs: [(label, (channel, cc)), ...] in KNOBS order."""
    rows = [[] for _ in rig.NAMES]
    for key in sorted(rig.KNOBS):
        fx_i, label = rig.KNOBS[key]
        if key == (1, 1):
            continue  # the mod wheel doubles the Drive knob
        rows[fx_i].append((label, key))
    return rows


def _button_for(rig, which):
    for key, w in rig.BUTTONS.items():
        if w == which:
            return key
    return None


def main(scope):
    global current
    scr = scope.root
    W, H = scope.size
    status = ui.status(scope)
    status.set_text("starting")
    try:
        import rig
    except ImportError:
        status.set_text("no rig module")
        ui.label(scr, "This needs the rig's rig.py and rig_inputs.py in /lib.", ui.font, ui.WHITE).align(
            lv.ALIGN.CENTER, 0, 0
        )
        return

    r = current = rig.Rig(midi=False, verbose=False)
    st = {"stop": False, "midi": "looking for the keyboard...", "shown": {}}

    def close():
        st["stop"] = True
        r.stop()
        if rig._rig is r:
            rig._rig = None

    scope.on_close(close)
    shell.touch_period(scope, TOUCH_MS)

    # -- the pedals --------------------------------------------------------
    gap = 12
    w = (W - 4 * gap) // 3
    top = gap
    h = H - top - 64 - gap
    rows = _knob_rows(rig)
    values = []  # (fx_i, label, value label)
    switches = []
    for i, name in enumerate(rig.NAMES):
        card = ui.box(scr, gap + i * (w + gap), top, w, h)
        title = ui.label(card, name.upper(), ui.big, ui.WHITE)
        title.align(lv.ALIGN.TOP_LEFT, 4, 4)
        btn, lbl = ui.button(card, "ON", (lambda k: lambda: r.toggle(k))(i), w=86, h=48)
        btn.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        switches.append((btn, lbl))
        cc = _button_for(rig, i)
        if cc:
            ui.label(card, "ch%d CC%d" % cc, ui.small, ui.MUTED).align(lv.ALIGN.TOP_RIGHT, -4, 54)
        y = 92
        for label, key in rows[i]:
            ui.label(card, label, ui.font, ui.WHITE).set_pos(4, y)
            v = ui.label(card, "", ui.font, ui.ACCENT)
            v.align(lv.ALIGN.TOP_RIGHT, -4, y)
            ui.label(card, "knob ch%d CC%d" % key, ui.small, ui.MUTED).set_pos(4, y + 26)
            values.append((i, label, v))
            y += 62
    bypass, bypass_lbl = ui.button(scr, "Bypass", lambda: r.toggle("all"), w=180, h=48)
    bypass.set_pos(gap, H - 56)
    cc = _button_for(rig, "all")
    hint = ui.label(scr, "", ui.small, ui.MUTED)
    hint.set_pos(gap + 196, H - 46)

    def show(key, obj, text, color=None):
        if st["shown"].get(key) == text:
            return
        st["shown"][key] = text
        obj.set_text(text)
        if color is not None:
            obj.set_style_text_color(color, 0)

    # Each knob's macro index, worked out once: refresh() runs between the
    # loop's polls, so it does nothing at all unless something changed.
    knobs = []
    for fx_i, label, v in values:
        fx = r.effects[fx_i]
        knobs.append((fx_i, label, v, fx, type(fx).MACRO_LABELS.index(label)))
    seen = [-1, None]

    def refresh(t=None):
        # A knob that lands is logged (r.log); a switch or bypass flips r.off
        # or r.bypassed. Nothing else changes what's on screen.
        flags = (tuple(r.off), r.bypassed)
        if len(r.log) == seen[0] and flags == seen[1]:
            return
        seen[0], seen[1] = len(r.log), flags
        if len(r.log) > 200:
            del r.log[:100]
            seen[0] = len(r.log)
        for fx_i, label, v, fx, idx in knobs:
            show(("v", fx_i, label), v, str(int(fx.get_macro(idx))), ui.MUTED if r.off[fx_i] or r.bypassed else ui.ACCENT)
        for i, (btn, lbl) in enumerate(switches):
            on = not r.off[i]
            if st["shown"].get(("sw", i)) != on:
                st["shown"][("sw", i)] = on
                lbl.set_text("ON" if on else "OFF")
                btn.set_style_bg_color(ui.GOOD if on else ui.MUTED, 0)
        if st["shown"].get("bypass") != r.bypassed:
            st["shown"]["bypass"] = r.bypassed
            bypass_lbl.set_text("Bypassed" if r.bypassed else "Bypass")
            bypass.set_style_bg_color(ui.WARN if r.bypassed else ui.ACCENT, 0)
        show("hint", hint, "%s.  Bypass: ch%d CC%d" % ((st["midi"],) + (cc or (0, 0))))

    def stats(t=None):
        s = r.inp.stats()
        # Just the state: a label that changed every few seconds would cost
        # the loop a redraw each time (the effects app's current.line() has the counters).
        if st.get("waiting"):
            text = "waiting for the foreground loop (appkit.serve())"
        else:
            text = "playing" if s.get("streaming") else "waiting for the PC to play"
        show("status", status, text)

    refresh()
    stats()
    scope.every(REFRESH_MS, refresh)
    scope.every(5000, stats)

    # -- the loop --------------------------------------------------------------

    def hook():
        if st["stop"]:
            raise _Stop

    def loop():
        if st["stop"]:
            return
        if st.get("waiting"):
            st["waiting"] = False
            stats()
        if r.port is None and r.host is None:
            r._open_midi()
            if r.port is not None:
                st["midi"] = "Keyboard: knobs live"
            else:
                st["midi"] = "No MIDI keyboard: knobs off"
            seen[0] = -1  # show it
        try:
            r.run(hook=hook)
        except _Stop:
            return
        except Exception:
            if st["stop"]:
                return  # the app closed under the loop: its ring is gone
            raise
        if not st["stop"]:
            raise KeyboardInterrupt  # Ctrl-C reached the rig's own loop

    if not scope.foreground(loop, steps=False):
        st["waiting"] = True
        stats()
