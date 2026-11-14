# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Check that Bit World's partial repaint draws the same pixels as a full redraw.

Runs every act for a few hundred frames, drawing each one twice: once from scratch
into a reference frame, and once through draw_changes into one of two alternating
buffers that start out dirty. Any differing pixel is reported with its rows and
columns. The app draws into one buffer; two alternating ones are the harder case.

Run it from the app's folder, on CPython or MicroPython:

    python tests/repaint_check.py [width height frames]
    MICROPYPATH=".:.frozen" micropython -X heapsize=96M tests/repaint_check.py
"""

import sys

# The app's modules import each other by name, as they do on a board.
_app = __file__.replace("\\", "/").rsplit("/", 2)
_app = _app[0] if len(_app) == 3 else "."
if _app not in sys.path:
    sys.path.insert(0, _app)

from act_deck import CyberDeckAct
from act_game import SkyRuinsAct
from act_pet import WorkshopAct
from bit_palette import VOID, Layout, PanelState, init_rng, make_fb
from bit_sound import SoundEngine
from bit_sprites import SpriteBank
from pygraphics import Draw


class NoAudio:
    pass  # no audio_out, so the sound engine runs silent


def check(w=800, h=480, frames=300, report=print):
    """Draw every act both ways for *frames* frames; return how many frames differed."""
    lay = Layout(w, h)
    sprites = SpriteBank(lay)
    snd = SoundEngine(NoAudio, None)
    acts = (WorkshopAct(lay, sprites, snd), SkyRuinsAct(lay, sprites, snd), CyberDeckAct(lay, sprites, snd))
    ref_buf, ref_fb = make_fb(w, h, VOID)
    panels = []
    for _ in range(2):
        b, f = make_fb(w, h, 0x1234)  # start dirty on purpose
        panels.append((b, f, Draw(f), PanelState()))
    row = w * 2
    bad = 0
    full = 0
    fast = 0
    for ai, act in enumerate(acts):
        for st in (p[3] for p in panels):
            st.act = -1
        init_rng(7)
        for frame in range(frames):
            auto = frame % 200 < 150
            if frame % 37 == 5:
                if ai == 0:
                    act.trigger_action((frame // 37) % 5)
                elif ai == 1:
                    act.jump()
                    act.fire()
                else:
                    act.on_pointer_down(*(act.switch_rects[frame % 4][:2]))
                    act.on_pointer_down(*(act.pad_rects[frame % 8][:2]))
            if ai == 0:
                act.update_pointer_look(100 + frame * 3 % 600, 100 + frame * 5 % 300)
            act.update(0.033, auto)
            snd.update(0.033, ai, acts[2].state)
            init_rng(frame)
            act.draw(ref_fb, Draw(ref_fb))
            b, f, d, st = panels[frame & 1]
            init_rng(frame)
            if frame % 90 == 60:
                st.act = -1  # as after a wipe
            if st.act == ai:
                act.draw_changes(f, d, st)
                fast += 1
            else:
                act.draw(f, d, st)
                st.act = ai
                full += 1
            if bytes(ref_buf) != bytes(b):
                diff = [i for i in range(len(b)) if ref_buf[i] != b[i]]
                ys = sorted(set(i // row for i in diff))
                xs = sorted(set((i % row) // 2 for i in diff))
                report("MISMATCH act %d frame %d bytes %d rows %d-%d cols %d-%d"
                       % (ai, frame, len(diff), ys[0], ys[-1], xs[0], xs[-1]))
                bad += 1
                if bad > 5:
                    return bad
    report("equiv %d %d bad %d full %d fast %d" % (w, h, bad, full, fast))
    return bad


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:4]]
    sys.exit(1 if check(*args) else 0)
