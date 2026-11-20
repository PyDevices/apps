# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Act 3: Solarpunk Reactor & Synth Cyber-Deck (Machine HMI Showcase).

Demonstrates an industrial control panel and audio workstation built with
pygraphics.Draw vector primitives (thick arcs, rotating polygon needles,
rounded rectangles) and pixel-art tactile controls (rocker switches, throttle
fader, coolant tank, dual-trace oscilloscope, 16-band spectrum analyzer, and an
8-pad live synth sequencer matrix).

Needs: pygraphics, bit_palette, bit_sprites.
"""

from array import array
from bit_palette import (
    ABYSS,
    AMBER,
    AQUA_GLOW,
    BRONZE,
    COPPER,
    CORAL,
    CREAM,
    CYAN,
    DARK_MOSS,
    DEEP_SLATE,
    DEEP_TEAL,
    EMERALD,
    KEY,
    FOREST,
    GOLD,
    ICE_CYAN,
    LIME_GLOW,
    MAGENTA,
    MIST,
    NEON_PINK,
    NIGHT,
    ORANGE,
    SILVER,
    SLATE,
    SIN256,
    STEEL,
    SUN_YELLOW,
    TEAL,
    VOID,
    WHITE,
    copy_frame,
    draw_pixel_panel,
    icos,
    isin,
    make_canvas,
    make_draw,
    make_fb,
    rect_sources,
    restore_rect,
    restore_sources,
)

# Change these to match your setup.
# The frame rate at which the FPS dial reads full scale.
FPS_FULL_SCALE = 60.0

SWITCH_NAMES = ("BOOST", "SHLD", "PHASE", "OVRD")
PAD_NOTES = ("D4", "E4", "F4", "A4", "C5", "D5", "E5", "A5")


class CyberDeckAct:
    """Render and operate Act 3: Solarpunk Reactor and Synth HMI Console."""

    # *background* is a (bytearray, FrameBuffer) pair from make_fb at the panel's size to
    # draw the static scene into; left as None, the act makes its own.
    def __init__(self, layout, sprites, sound, background=None):
        self.lay = layout
        self.sprites = sprites
        self.sound = sound
        self.phase = 0
        self.fps = 0.0
        self.auto_ms = 1800
        self.auto_step = 0

        # Live interactive HMI state shared with SoundEngine.
        self.switches = [True, True, False, False]
        self.throttle = 0.68
        self.pads = [True, False, True, True, False, True, True, True]
        self.state = {
            "boost": self.switches[0],
            "shield": self.switches[1],
            "phase": self.switches[2],
            "overdrive": self.switches[3],
            "throttle": self.throttle,
            "pads": self.pads,
        }

        # Precompute 6 instrument bay rectangles across the scene.
        w = layout.w
        sy = layout.scene_y
        sh = layout.scene_h
        pad = layout.pad
        top_h = int(sh * 0.50)
        bot_h = sh - top_h - pad * 3
        top_y = sy + pad
        bot_y = top_y + top_h + pad

        col1_w = int(w * 0.34)
        col2_w = int(w * 0.36)
        col3_w = w - col1_w - col2_w - pad * 4

        x1 = pad
        x2 = x1 + col1_w + pad
        x3 = x2 + col2_w + pad

        self.bay_gauges = (x1, top_y, col1_w, top_h)
        self.bay_scope = (x2, top_y, col2_w, top_h)
        self.bay_holo = (x3, top_y, col3_w, top_h)

        self.bay_switches = (x1, bot_y, col1_w, bot_h)
        self.bay_spectrum = (x2, bot_y, col2_w, bot_h)
        self.bay_pads = (x3, bot_y, col3_w, bot_h)

        # Compute hit rectangles for switches, throttle slider, and 8 synth pads.
        self.switch_rects = []
        sx, sy_sw, sw_w, sw_h = self.bay_switches
        throttle_w = 28 if layout.compact else 38
        sw_area_w = sw_w - throttle_w - 22
        gap = 4 if layout.compact else 6
        btn_w = (sw_area_w - gap * 3) // 4
        btn_h = sw_h - (28 if layout.compact else 36)
        for i in range(4):
            bx = sx + 8 + i * (btn_w + gap)
            by = sy_sw + (20 if layout.compact else 24)
            self.switch_rects.append((bx, by, btn_w, btn_h))

        self.throttle_rect = (
            sx + sw_w - throttle_w - 8,
            sy_sw + (20 if layout.compact else 24),
            throttle_w,
            btn_h,
        )

        self.pad_rects = []
        px, py_p, pw, ph = self.bay_pads
        pad_cols = 4
        pad_rows = 2
        pgap = 4 if layout.compact else 6
        cell_w = (pw - 16 - pgap * (pad_cols - 1)) // pad_cols
        cell_h = (ph - (24 if layout.compact else 30) - pgap) // pad_rows
        for r in range(pad_rows):
            for c in range(pad_cols):
                bx = px + 8 + c * (cell_w + pgap)
                by = py_p + (18 if layout.compact else 22) + r * (cell_h + pgap)
                self.pad_rects.append((bx, by, cell_w, cell_h))

        # Coolant tank bubble heights, in millionths of the liquid's height, and how fast
        # each rises, in thousandths of the liquid per second at throttle zero.
        self.bubbles = array("i", (150000, 420000, 680000, 850000))
        self._bubble_speed = (350, 430, 510, 590)

        # Made once, so a frame's repaint allocates none of them: the keys under which a
        # PanelState remembers each switch and pad, the needle polygon, and the readouts,
        # formatted again only when what they show changes.
        self._switch_keys = tuple(("switch", i) for i in range(len(self.switch_rects)))
        self._pad_keys = tuple(("pad", i) for i in range(len(self.pad_rects)))
        self._needle = array("h", [0] * 6)
        self._mw_shown = -1
        self._mw_text = ""
        self._fps_shown = -1
        self._fps_text = ""
        self._attract_tables()

        # Pre-render the brushed metal chassis and static dial bezels into bg_fb.
        self.bg_buf, self.bg_fb = background or make_fb(w, layout.h, VOID)
        self.bg_view = memoryview(self.bg_buf)
        self.bg_draw = make_draw(self.bg_fb)
        self._build_static_console()

        # The gauge needles turn in place, so the background under them is prepared once.
        self.gauge_sources = rect_sources(
            self.bg_buf,
            [(cx - rad - 3, cy - rad - 3, rad * 2 + 7, rad * 2 + 7) for cx, cy, rad, _ in self.gauge_centers],
            w,
            layout.h,
        )

        # The needles' hub, drawn once and then blitted with framebuf, which allocates
        # nothing; pygraphics' circles return an Area each.
        self._hub = make_canvas(bytearray(11 * 11 * 2), 11, 11)
        self._hub.fill(KEY)
        hub_draw = make_draw(self._hub)
        hub_draw.circle(5, 5, 4, BRONZE, True)
        hub_draw.circle(5, 5, 2, WHITE, True)

    # In attract mode the throttle follows the phase, so everything it moves is worked
    # out here once per phase, with the same float arithmetic the live path uses. A
    # frame then reads integers, where the live path would box a dozen floats.
    def _attract_tables(self):
        lay = self.lay
        # Index p is phase >> 1, the throttle the operator holds at that phase.
        self._thr_table = tuple(
            max(0.15, min(0.92, 0.62 + ((SIN256[p] * 24) / 102400.0))) for p in range(128)
        )
        # Where the throttle came from: its phase >> 1, or -1 when a pointer set it.
        self._thr_index = -1
        th_tank = self.bay_holo[3] - (26 if lay.compact else 30)
        th_fader = self.throttle_rect[3]
        self._level_table = array("h", (int(th_tank * (0.58 + t * 0.28)) for t in self._thr_table))
        self._fill_table = array(
            "h", (max(0, min(th_fader - 4, int(th_fader * t))) for t in self._thr_table)
        )
        self._permille_table = array("h", (self._permille(t) for t in self._thr_table))
        # Per phase and boost switch: the flux needle's angle and its MW readout. Per
        # phase and both switches: how many TEMP segments light.
        ang = array("B", bytes(512))
        mw = array("h", bytes(1024))
        segs = array("B", bytes(1024))
        for phase in range(256):
            t = self._thr_table[phase >> 1]
            jitter = (SIN256[(phase * 3) & 0xFF] * 3) / 10240.0
            for boost in (0, 1):
                val1 = min(1.0, max(0.05, t * 0.78 + (0.16 if boost else 0.0) + jitter))
                ang[phase * 2 + boost] = (96 + int(val1 * 170)) & 0xFF
                mw[phase * 2 + boost] = int(val1 * 990)
                for ovr in (0, 1):
                    val2 = min(1.0, max(0.05, t * 0.72 + (0.14 if ovr else 0.0) - jitter))
                    segs[phase * 4 + boost * 2 + ovr] = max(1, min(10, int(((val1 + val2) * 0.5) * 10)))
        self._ang_table = ang
        self._mw_table = mw
        self._segs_table = segs

    # The throttle in thousandths, for the bubbles' integer arithmetic.
    @staticmethod
    def _permille(t):
        return int(t * 1000.0 + 0.5)

    # Pre-render the industrial console chassis, rivets, and static gauge arcs.
    def _build_static_console(self):
        fb = self.bg_fb
        d = self.bg_draw
        lay = self.lay
        w = lay.w
        sy = lay.scene_y
        sh = lay.scene_h

        # Brushed steel chassis background with subtle horizontal scanlines.
        fb.fill_rect(0, sy, w, sh, NIGHT)
        for y in range(sy, sy + sh, 4):
            fb.hline(0, y, w, ABYSS)

        for rect, border, title, tcol in (
            (self.bay_gauges, CYAN, "REACTOR TELEMETRY", AQUA_GLOW),
            (self.bay_scope, EMERALD, "DUAL-TRACE OSCILLOSCOPE", LIME_GLOW),
            (self.bay_holo, GOLD, "HOLO-CORE & COOLANT", GOLD),
            (self.bay_switches, AMBER, "BREAKER BANK & THROTTLE", GOLD),
            (self.bay_spectrum, CYAN, "16-BAND HARMONIC FFT", AQUA_GLOW),
            (self.bay_pads, NEON_PINK, "SYNTH SEQUENCER MATRIX", NEON_PINK),
        ):
            bx, by, bw, bh = rect
            draw_pixel_panel(fb, bx, by, bw, bh, VOID, border, SILVER, ABYSS)
            max_chars = max(8, (bw - 14) // 8)
            fb.text(title[:max_chars], bx + 8, by + 5, tcol)

        # Pre-render the static multi-zone gauge rings using pygraphics.Draw.arc.
        gx, gy, gw, gh = self.bay_gauges
        r = min(gw // 4 - 6, (gh - 34) // 2)
        r = max(18, r)
        cy = gy + 20 + r + 4
        cx1 = gx + (gw >> 2) + 2
        cx2 = gx + ((gw * 3) >> 2) - 2
        self.gauge_centers = ((cx1, cy, r, "FLUX MW"), (cx2, cy, r, "FPS"))
        thick = 4 if lay.compact else 6
        # The flux dial runs green to red; the FPS dial runs red below 12 fps,
        # gold to 30 fps and green above, scaled to FPS_FULL_SCALE.
        fps_deg = 239 / FPS_FULL_SCALE
        zones = (
            ((135, 270, EMERALD), (270, 345, GOLD), (345, 405, CORAL)),
            (
                (135, 135 + int(12 * fps_deg), CORAL),
                (135 + int(12 * fps_deg), 135 + int(30 * fps_deg), GOLD),
                (135 + int(30 * fps_deg), 405, EMERALD),
            ),
        )
        for (cx, c_y, rad, label), dial_zones in zip(self.gauge_centers, zones):
            d.circle(cx, c_y, rad + 2, DEEP_SLATE, False)
            for dr in range(thick):
                for a0, a1, zcol in dial_zones:
                    d.arc(cx, c_y, rad - dr, a0, a1, zcol)
            lbl_x = cx - (len(label) * 4)
            fb.text(label, lbl_x, c_y + rad + (6 if lay.compact else 10), SILVER)

        # Pre-render the oscilloscope graticule grid inside bay_scope.
        sx, sy_s, sw, sh_s = self.bay_scope
        ox = sx + 8
        oy = sy_s + (18 if lay.compact else 22)
        ow = sw - 16
        oh = sh_s - (26 if lay.compact else 32)
        self.scope_well = (ox, oy, ow, oh)
        fb.rect(ox - 1, oy - 1, ow + 2, oh + 2, DEEP_TEAL)

    # Sync the exported state dictionary read by SoundEngine.
    def _sync_state(self):
        self.state["boost"] = self.switches[0]
        self.state["shield"] = self.switches[1]
        self.state["phase"] = self.switches[2]
        self.state["overdrive"] = self.switches[3]
        self.state["throttle"] = self.throttle

    # Handle pointer down or drag inside the Cyber-Deck console.
    def on_pointer_down(self, x, y, is_drag=False):
        # Check throttle slider first (supports continuous dragging).
        tx, ty, tw, th = self.throttle_rect
        if tx - 6 <= x <= tx + tw + 6 and ty - 4 <= y <= ty + th + 4:
            rel = 1.0 - ((y - ty) / max(1, th))
            self.throttle = max(0.08, min(1.0, rel))
            self._thr_index = -1
            self._sync_state()
            if not is_drag:
                self.sound.sfx_switch(True)
            return True

        if is_drag:
            return False

        # Check the 4 tactile breaker switches.
        for i, (bx, by, bw, bh) in enumerate(self.switch_rects):
            if bx <= x < bx + bw and by <= y < by + bh:
                self.switches[i] = not self.switches[i]
                self._sync_state()
                self.sound.sfx_switch(self.switches[i])
                return True

        # Check the 8 harmonic synth pads.
        for i, (bx, by, bw, bh) in enumerate(self.pad_rects):
            if bx <= x < bx + bw and by <= y < by + bh:
                self.pads[i] = not self.pads[i]
                # Ensure at least two pads stay active so the groove never goes empty.
                if sum(1 for p in self.pads if p) < 2:
                    self.pads[i] = True
                self.sound.sfx_pad(i, self.pads[i])
                return True

        return False

    # Advance coolant bubbles, gauge oscillation, and attract-mode operator.
    def update(self, dt, auto_mode=True):
        self.phase = (self.phase + 5) & 0xFF
        # Counted in whole ms and integer fractions, so a frame boxes no floats for them.
        dt_ms = round(dt * 1000.0)
        if self._thr_index >= 0:
            speed = 600 + self._permille_table[self._thr_index]
        else:
            speed = 600 + self._permille(self.throttle)
        bubbles = self.bubbles
        for i in range(len(bubbles)):
            # Millionths per frame: speed per mille times rate per mille times dt in ms.
            b = bubbles[i] + (self._bubble_speed[i] * speed // 1000) * dt_ms
            if b >= 1000000:
                b -= 1000000
            bubbles[i] = b

        # Attract-mode virtual operator: toggle switches, sweep throttle, tap pads.
        if auto_mode:
            self._thr_index = self.phase >> 1
            self.throttle = self._thr_table[self._thr_index]
            self._sync_state()
            self.auto_ms -= dt_ms
            if self.auto_ms <= 0:
                self.auto_ms = 2100
                self.auto_step = (self.auto_step + 1) & 7
                if (self.auto_step & 1) == 0:
                    sw_idx = (self.auto_step >> 1) & 3
                    self.switches[sw_idx] = not self.switches[sw_idx]
                    self._sync_state()
                    self.sound.sfx_switch(self.switches[sw_idx])
                else:
                    pad_idx = (self.auto_step * 3) & 7
                    self.pads[pad_idx] = not self.pads[pad_idx]
                    if sum(1 for p in self.pads if p) < 3:
                        self.pads[pad_idx] = True
                    self.sound.sfx_pad(pad_idx, self.pads[pad_idx])

    # Render the Cyber-Deck console into the target FrameBuffer and Draw wrapper.
    def draw(self, fb, draw_obj=None, st=None):
        if draw_obj is None:
            draw_obj = make_draw(fb)
        copy_frame(fb, self.bg_fb)

        self._draw_gauges(fb, draw_obj, True)
        self._draw_oscilloscope(fb)
        self._draw_holo_and_coolant(fb)
        self._draw_switches_and_throttle(fb)
        self._draw_spectrum_analyzer(fb)
        self._draw_synth_pads(fb)
        if st is not None:
            st.sig = {}
            play_slot = self.sound._step_index & 7
            for i in range(len(self.switch_rects)):
                st.sig[self._switch_keys[i]] = self.switches[i]
            for i in range(len(self.pad_rects)):
                st.sig[self._pad_keys[i]] = self._pad_look(i, play_slot)

    # How pad i looks: 0 off, 1 on, 2 on and playing.
    def _pad_look(self, i, play_slot):
        if not self.pads[i]:
            return 0
        return 2 if i == play_slot else 1

    # Repaint only what changed since this display buffer was last drawn: the gauge dials
    # get their background back, the wells paint over themselves, and the switches and pads
    # are redrawn when they flip. Which ones flipped is kept as bits, so nothing is allocated.
    def draw_changes(self, fb, draw_obj, st):
        lay = self.lay
        play_slot = self.sound._step_index & 7
        n_switches = len(self.switch_rects)
        n_pads = len(self.pad_rects)
        switch_flips = 0
        for i in range(n_switches):
            if st.changed(self._switch_keys[i], self.switches[i]):
                switch_flips |= 1 << i
        pad_flips = 0
        for i in range(n_pads):
            if st.changed(self._pad_keys[i], self._pad_look(i, play_slot)):
                pad_flips |= 1 << i
        restore_sources(fb, self.gauge_sources)
        for i in range(n_switches):
            if switch_flips >> i & 1:
                restore_rect(fb, self.bg_view, self.switch_rects[i], lay.w, lay.h)
        for i in range(n_pads):
            if pad_flips >> i & 1:
                restore_rect(fb, self.bg_view, self.pad_rects[i], lay.w, lay.h)

        self._draw_gauges(fb, draw_obj, False)
        self._draw_oscilloscope(fb)
        self._draw_holo_and_coolant(fb)
        for i in range(n_switches):
            if switch_flips >> i & 1:
                self._draw_switch(fb, i)
        self._draw_throttle(fb)
        self._draw_spectrum_analyzer(fb)
        for i in range(n_pads):
            if pad_flips >> i & 1:
                self._draw_synth_pad(fb, i, play_slot)

    # Render rotating polygon needles and digital readouts for the twin gauges.
    # The TEMP label is drawn only when full, as nothing paints over it.
    def _draw_gauges(self, fb, d, full):
        boost = 1 if self.switches[0] else 0
        ovr = 1 if self.switches[3] else 0
        if self._thr_index == self.phase >> 1:
            ang1 = self._ang_table[self.phase * 2 + boost]
            mw = self._mw_table[self.phase * 2 + boost]
            active_segs = self._segs_table[self.phase * 4 + boost * 2 + ovr]
        else:
            jitter = (isin(self.phase * 3) * 3) / 10240.0
            val1 = min(1.0, max(0.05, self.throttle * 0.78 + (0.16 if boost else 0.0) + jitter))
            val2 = min(1.0, max(0.05, self.throttle * 0.72 + (0.14 if ovr else 0.0) - jitter))
            ang1 = (96 + int(val1 * 170)) & 0xFF
            mw = int(val1 * 990)
            active_segs = max(1, min(10, int(((val1 + val2) * 0.5) * 10)))
        # The second dial shows the frame rate, full scale at FPS_FULL_SCALE.
        fps_val = min(1.0, max(0.0, self.fps / FPS_FULL_SCALE))
        if mw != self._mw_shown:
            self._mw_shown = mw
            self._mw_text = "%03dMW" % mw
        tenths = int(self.fps * 10.0 + 0.5)
        if tenths != self._fps_shown:
            self._fps_shown = tenths
            self._fps_text = "%.1f" % self.fps

        self._draw_needle(fb, d, 0, ang1, GOLD, self._mw_text)
        self._draw_needle(fb, d, 1, (96 + int(fps_val * 170)) & 0xFF, AQUA_GLOW, self._fps_text)

        # Draw a segmented Core Temp status bar along the bottom of the telemetry bay.
        gx, gy, gw, gh = self.bay_gauges
        bar_y = gy + gh - (16 if self.lay.compact else 20)
        if bar_y > self.gauge_centers[0][1] + self.gauge_centers[0][2] + 14:
            if full:
                fb.text("TEMP", gx + 8, bar_y, SILVER)
            bx0 = gx + 48
            bw_tot = gw - 58
            segs = 10
            seg_w = max(4, (bw_tot - (segs - 1) * 2) // segs)
            for s in range(segs):
                sx = bx0 + s * (seg_w + 2)
                if s < active_segs:
                    scol = CORAL if s >= 8 else (GOLD if s >= 6 else LIME_GLOW)
                else:
                    scol = DEEP_SLATE
                fb.fill_rect(sx, bar_y, seg_w, 8, scol)

    # Draw gauge idx's needle at phase index ang_idx, its hub and its readout txt. A value
    # from 0.0 to 1.0 maps to (96 + int(v * 170)) & 0xFF, about 210 degrees of the dial.
    def _draw_needle(self, fb, d, idx, ang_idx, col, txt):
        cx, cy, rad, _ = self.gauge_centers[idx]
        tip_len = rad - 4
        px = (icos((ang_idx + 64) & 0xFF) * 3) >> 10
        py = (isin((ang_idx + 64) & 0xFF) * 3) >> 10
        poly = self._needle
        poly[0] = cx + ((icos(ang_idx) * tip_len) >> 10)
        poly[1] = cy + ((isin(ang_idx) * tip_len) >> 10)
        poly[2] = cx + px
        poly[3] = cy + py
        poly[4] = cx - px
        poly[5] = cy - py
        fb.poly(0, 0, poly, col, True)
        if fb.__class__ is self._hub.__class__:
            fb.blit(self._hub, cx - 5, cy - 5, KEY)
        else:
            d.circle(cx, cy, 4, BRONZE, True)
            d.circle(cx, cy, 2, WHITE, True)
        fb.text(txt, cx - (len(txt) * 4), cy + (rad >> 1) - 2, WHITE)

    # Render the dual-trace oscilloscope with fundamental and phase-shifted traces.
    def _draw_oscilloscope(self, fb):
        ox, oy, ow, oh = self.scope_well
        fb.fill_rect(ox, oy, ow, oh, VOID)
        mid_y = oy + (oh >> 1)
        fb.hline(ox, mid_y, ow, NIGHT)
        fb.vline(ox + (ow >> 1), oy, oh, NIGHT)

        samples = self.sound.scope_samples
        n = len(samples)
        span_w = max(1, ow - 4)
        half_h = max(6, (oh >> 1) - 4)
        p1x = ox + 2
        p1y = mid_y
        p2x = ox + 2
        p2y = mid_y
        phase_shift = 6 if self.switches[2] else 3
        for i in range(n):
            sx = ox + 2 + (i * span_w) // (n - 1)
            s1 = samples[i]
            s2 = samples[(i + phase_shift) % n]
            y1 = mid_y - ((s1 * half_h) // 100)
            y2 = mid_y - ((s2 * (half_h - 3)) // 115)
            if i > 0:
                fb.line(p1x, p1y, sx, y1, AQUA_GLOW)
                fb.line(p2x, p2y, sx, y2, GOLD)
            p1x, p1y = sx, y1
            p2x, p2y = sx, y2

    # Render the Holo-Bit diagnostic projector and sloshing coolant tank.
    def _draw_holo_and_coolant(self, fb):
        bx, by, bw, bh = self.bay_holo
        tank_w = 24 if self.lay.compact else 34
        tx = bx + bw - tank_w - 8
        ty = by + (18 if self.lay.compact else 22)
        th = bh - (26 if self.lay.compact else 30)

        # Draw Holo-Bit hovering inside a cyan wireframe projection well.
        hx = bx + 8
        hw = tx - hx - 6
        fb.fill_rect(hx, ty, hw, th, VOID)
        fb.rect(hx, ty, hw, th, DEEP_TEAL)
        scan_y = ty + 2 + ((self.phase * max(1, th - 6)) >> 8)
        fb.hline(hx + 2, scan_y, hw - 4, DEEP_TEAL)

        bob = (isin(self.phase) * 4) >> 10
        hcx = hx + (hw >> 1)
        hcy = ty + (th >> 1) - 4 + bob
        self.sprites.draw_glow(fb, hcx, hcy, AQUA_GLOW, large=True)
        self.sprites.holo_bit.draw_center(fb, hcx, hcy)
        status = "OVRDRV!" if self.switches[3] else "NOMINAL"
        scol = CORAL if self.switches[3] else LIME_GLOW
        fb.text(status, hx + ((hw - len(status) * 8) >> 1), ty + th - 12, scol)

        # Draw the vertical Bioluminescent Coolant Tank with rising bubbles.
        fb.fill_rect(tx, ty, tank_w, th, VOID)
        fb.rect(tx, ty, tank_w, th, TEAL)
        if self._thr_index >= 0:
            level_h = self._level_table[self._thr_index]
        else:
            level_h = int(th * (0.58 + self.throttle * 0.28))
        liq_y = ty + th - level_h
        fb.fill_rect(tx + 2, liq_y, tank_w - 4, level_h - 2, FOREST)
        fb.hline(tx + 2, liq_y, tank_w - 4, LIME_GLOW)
        fb.hline(tx + 2, liq_y + 1, tank_w - 4, EMERALD)
        rise = max(4, level_h - 6)
        for idx in range(len(self.bubbles)):
            by_bub = ty + th - 4 - self.bubbles[idx] * rise // 1000000
            bx_bub = tx + 5 + ((idx * 7) % max(4, tank_w - 10))
            fb.fill_rect(bx_bub, by_bub, 3, 3, AQUA_GLOW)

    # Render the 4 tactile toggle switches and vertical throttle fader.
    def _draw_switches_and_throttle(self, fb):
        for i in range(len(self.switch_rects)):
            self._draw_switch(fb, i)
        self._draw_throttle(fb)

    # Render one tactile breaker switch.
    def _draw_switch(self, fb, i):
        bx, by, bw, bh = self.switch_rects[i]
        on = self.switches[i]
        border = LIME_GLOW if on else STEEL
        draw_pixel_panel(fb, bx, by, bw, bh, NIGHT, border)
        # Status LED bar at top of switch.
        led_col = LIME_GLOW if on else DEEP_SLATE
        fb.fill_rect(bx + 5, by + 5, bw - 10, 4, led_col)
        # Tactile rocker handle (up when ON, down when OFF).
        rock_h = max(10, (bh - 26) >> 1)
        rock_y = (by + 12) if on else (by + 12 + rock_h)
        rock_col = AQUA_GLOW if on else SLATE
        fb.fill_rect(bx + 5, rock_y, bw - 10, rock_h, rock_col)
        fb.hline(bx + 5, rock_y, bw - 10, WHITE if on else SILVER)
        # Label at bottom of switch.
        lbl = SWITCH_NAMES[i][: max(3, (bw - 4) // 8)]
        fb.text(lbl, bx + ((bw - len(lbl) * 8) >> 1), by + bh - 11, WHITE if on else MIST)

    # Render the vertical THROTTLE fader track and brass thumb cap.
    def _draw_throttle(self, fb):
        tx, ty, tw, th = self.throttle_rect
        fb.fill_rect(tx, ty, tw, th, VOID)
        fb.rect(tx, ty, tw, th, AMBER)
        if self._thr_index >= 0:
            fill_h = self._fill_table[self._thr_index]
        else:
            fill_h = max(0, min(th - 4, int(th * self.throttle)))
        if fill_h > 2:
            fb.fill_rect(tx + 3, ty + th - fill_h - 2, tw - 6, fill_h, COPPER)
        knob_y = ty + th - fill_h - 5
        knob_y = max(ty + 2, min(ty + th - 10, knob_y))
        fb.fill_rect(tx + 1, knob_y, tw - 2, 8, GOLD)
        fb.hline(tx + 2, knob_y + 1, tw - 4, WHITE)

    # Render the 16-band real-time FFT spectrum analyzer with peak-hold caps.
    def _draw_spectrum_analyzer(self, fb):
        bx, by, bw, bh = self.bay_spectrum
        wx = bx + 8
        wy = by + (18 if self.lay.compact else 22)
        ww = bw - 16
        wh = bh - (24 if self.lay.compact else 28)
        fb.fill_rect(wx, wy, ww, wh, VOID)
        fb.rect(wx, wy, ww, wh, DEEP_TEAL)

        bins = self.sound.spectrum_bins
        peaks = self.sound.spectrum_peaks
        n = len(bins)
        step_x = (ww - 6) // n
        bar_w = max(3, step_x - 2)
        max_bar_h = wh - 8
        base_y = wy + wh - 3

        for i in range(n):
            x = wx + 4 + i * step_x
            h = (bins[i] * max_bar_h) // 100
            ph = (peaks[i] * max_bar_h) // 100
            if h > 0:
                mid_h = min(h, max_bar_h >> 1)
                fb.fill_rect(x, base_y - mid_h, bar_w, mid_h, EMERALD)
                if h > mid_h:
                    top_h = h - mid_h
                    col = GOLD if h > (max_bar_h * 3) >> 2 else AQUA_GLOW
                    fb.fill_rect(x, base_y - h, bar_w, top_h, col)
            peak_y = max(wy + 2, base_y - ph - 2)
            fb.hline(x, peak_y, bar_w, WHITE)

    # Render the 2x4 harmonic synth pad matrix with live step highlighter.
    def _draw_synth_pads(self, fb):
        play_slot = self.sound._step_index & 7
        for i in range(len(self.pad_rects)):
            self._draw_synth_pad(fb, i, play_slot)

    # Render one synth pad.
    def _draw_synth_pad(self, fb, i, play_slot):
        bx, by, bw, bh = self.pad_rects[i]
        active = self.pads[i]
        playing = (i == play_slot) and active
        if playing:
            bg = MAGENTA
            border = WHITE
        elif active:
            bg = DEEP_TEAL
            border = AQUA_GLOW
        else:
            bg = NIGHT
            border = SLATE
        draw_pixel_panel(fb, bx, by, bw, bh, bg, border, ICE_CYAN if active else None)
        lbl = PAD_NOTES[i]
        fb.text(
            lbl,
            bx + ((bw - len(lbl) * 8) >> 1),
            by + ((bh - 8) >> 1),
            WHITE if active else STEEL,
        )
