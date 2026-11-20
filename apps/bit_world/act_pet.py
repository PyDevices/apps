# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Act 1: Bit's Solarpunk Workshop (Desktop Companion and Smart Assistant).

Showcases how pygraphics powers expressive desktop pets, smart home companions,
and ambient desk displays with multi-shade pixel art, eye tracking, typewriter
speech bubbles, live voice waveforms, and interactive reaction buttons.

Needs: pygraphics, bit_palette, bit_sprites.
"""

from array import array

from bit_palette import (
    ABYSS,
    ABYSS_RGB,
    AMBER,
    AQUA_GLOW,
    BRONZE,
    COPPER,
    CORAL,
    CREAM,
    CYAN,
    DARK_MOSS,
    DARK_WOOD,
    DEEP_SLATE,
    DEEP_SLATE_RGB,
    DEEP_TEAL,
    EMERALD,
    FOREST,
    GOLD,
    ICE_CYAN,
    LIME_GLOW,
    MIST,
    MOSS,
    NEON_PINK,
    NIGHT,
    NIGHT_RGB,
    OAK,
    SILVER,
    SLATE,
    STEEL,
    SUN_YELLOW,
    TEAL,
    VOID,
    VOID_RGB,
    WHITE,
    copy_frame,
    draw_pixel_panel,
    icos,
    isin,
    make_fb,
    paint_gradient,
    rect_sources,
    restore_area,
    restore_rects,
    restore_sources,
    rng_int,
)

# Most moving rectangles a frame can have outside the fixed boxes.
MAX_MOVED = 40

# What the speech card's text needs: nothing, the newly typed letters, or a full redraw.
SPEECH_SAME = 0
SPEECH_ADD = 1
SPEECH_ALL = 2

# The clock's hundredths, made once so the readout needs no new string each frame.
TWO_DIGITS = tuple("%02d" % i for i in range(60))

# Action button definitions: (label, mood, emote_key, accent_color, speech_line).
ACTIONS = (
    (
        "1:GREET",
        "love",
        "heart",
        NEON_PINK,
        "Hi! I'm Bit -- your pixel-art desktop companion built on pygraphics!",
    ),
    (
        "2:SING",
        "sing",
        "note",
        AQUA_GLOW,
        "Synthesizing polyphonic chiptune harmonies via real-time synthio!",
    ),
    (
        "3:SCAN",
        "scan",
        "sparkle",
        LIME_GLOW,
        "Scanning Maker Lab... Temp 22.4C, Solar Array 99%, Inspiration HIGH!",
    ),
    (
        "4:COFFEE",
        "coffee",
        "bolt",
        GOLD,
        "Espresso capacitor charged! Ready to build games, pets & HMIs!",
    ),
    (
        "5:NAP",
        "sleep",
        "zzz",
        CYAN,
        "Entering cozy low-power standby... tap anywhere to wake me up!",
    ),
)


class WorkshopAct:
    """Render and animate Act 1: Bit's Solarpunk Maker Lab and Companion HUD."""

    # *background* is a (bytearray, FrameBuffer) pair from make_fb at the panel's size to
    # draw the static scene into; left as None, the act makes its own.
    def __init__(self, layout, sprites, sound, background=None):
        self.lay = layout
        self.sprites = sprites
        self.sound = sound
        self.phase = 0
        self.time_ms = 0
        self.mood = "happy"
        self._mood_label = (None, "")  # (mood, its label), so the label is made once
        self.mood_ms = 3500
        self.active_btn = 0
        self.bounce_vy = 0.0
        self.bounce_y = 0.0
        self.scan_sweep = 0.0

        # Eye tracking target relative to Bit's center.
        self.look_dx = 0
        self.look_dy = 0

        # Typewriter dialogue state (start fully revealed so first frame is complete).
        self.speech_full = ACTIONS[0][4]
        self.speech_chars = len(self.speech_full)

        # Attract-mode timer for automatic companion demonstrations.
        self.auto_ms = 1600
        self.auto_index = 0

        # Precompute key layout rectangles for 480x320 through 800x480.
        w = layout.w
        sy = layout.scene_y
        sh = layout.scene_h
        pad = layout.pad

        self.win_rect = (pad, sy + pad, int(w * 0.27), int(sh * 0.56))
        self.desk_y = sy + int(sh * 0.67)
        self.btn_bar_y = sy + sh - (30 if layout.compact else 38)
        self.btn_bar_h = 26 if layout.compact else 32

        # Center pedestal where Bit hovers.
        self.bit_home_x = int(w * 0.45)
        self.bit_home_y = sy + int(sh * 0.40)

        # Right-side holographic assistant cards.
        rx = int(w * 0.62)
        rw = w - rx - pad
        ch1 = int(sh * 0.24)
        ch2 = int(sh * 0.26)
        ch3 = (self.btn_bar_y - sy) - ch1 - ch2 - pad * 4
        self.card_chrono = (rx, sy + pad, rw, ch1)
        self.card_voice = (rx, sy + pad * 2 + ch1, rw, ch2)
        self.card_speech = (rx, sy + pad * 3 + ch1 + ch2, rw, max(44, ch3))

        # Five interactive bottom buttons.
        self.btn_rects = []
        btn_count = len(ACTIONS)
        avail_w = w - pad * 2
        gap = 4 if layout.compact else 8
        bw = (avail_w - gap * (btn_count - 1)) // btn_count
        for i in range(btn_count):
            bx = pad + i * (bw + gap)
            self.btn_rects.append((bx, self.btn_bar_y, bw, self.btn_bar_h))

        # Window starfield coordinates: [x, y, phase_offset].
        wx, wy, ww, wh = self.win_rect
        self.stars = []
        for i in range(22):
            sx = wx + 8 + ((i * 37 + 13) % max(8, ww - 16))
            sy_star = wy + 8 + ((i * 53 + 7) % max(8, int(wh * 0.62)))
            self.stars.append((sx, sy_star, i * 19))

        # Floating emote particles: [x, y, vx, vy, emote_name, life], life counted in
        # hundred-thousandths so that it boxes no floats.
        self.particles = []

        # Pre-render the static workshop interior into a background FrameBuffer.
        self.bg_buf, self.bg_fb = background or make_fb(w, layout.h, VOID)
        self.bg_view = memoryview(self.bg_buf)
        self._build_static_background()

        # Rising spore motes above the terrarium: [x, y, phase, color, path, step].
        self.spores = []
        self._init_spores()

        # The clock's text up to its hundredths, made again once a second.
        self._clock_s = -1
        self._clock_text = ""
        # The speech card's line breaks, as start and end letter indexes in speech_full.
        cx, cy, cw, ch = self.card_speech
        self._speech_cols = max(14, (cw - 16) // 8)
        self._speech_line_h = 11 if layout.compact else 13
        self._speech_lines = max(2, (ch - 22) // self._speech_line_h)
        self._spans = array("h", bytes(4 * self._speech_lines))
        self._spans_was = array("h", bytes(4 * self._speech_lines))
        self._lines = 0
        self._lines_was = 0
        self._simple_text = None
        self._simple = False

        # The stars, the clock's hundredths and the telemetry bars change in place, and
        # the spores, steam, pad ring and Bit move inside boxes that hold nothing else,
        # so the background under all of them is prepared once.
        cx, cy, cw, ch = self.card_chrono
        bx0 = cx + cw - (64 if layout.compact else 84)
        bar_max = 6 + ((2048 * (ch - 26)) >> 12)
        step = 8 if layout.compact else 10
        fixed = [(sx - 1, sy_star - 1, 3, 3) for sx, sy_star, _ in self.stars]
        fixed.append((cx + 80, cy + 17, 16, 21))
        fixed.append((bx0, cy + ch - 7 - bar_max, 6 * step + 6, bar_max))
        self._cards = (
            self.card_chrono,
            self.card_voice,
            self.card_speech,
            (0, self.btn_bar_y, w, self.btn_bar_h),
        )
        self._spore_box = self._safe(self._spore_bounds())
        self._steam_box = self._safe(self._bounds(self._put_steam))
        self._pad_box = self._safe(self._bounds(self._put_pad))
        self._bit_box = self._safe(self._bounds(self._put_bit))
        for box in (self._spore_box, self._steam_box, self._pad_box, self._bit_box):
            if box is not None:
                fixed.append(box)
        self.fixed_sources = rect_sources(self.bg_buf, fixed, w, layout.h)
        # Where this frame's other moving parts are; it trades places with the array
        # a PanelState keeps, so each display buffer remembers its own.
        self._moved = array("h", bytes(8 * MAX_MOVED))

    # Populate rising bioluminescent spore particles above the desk terrarium.
    def _init_spores(self):
        wx, _, _, _ = self.win_rect
        tx = wx + 18
        ty = self.desk_y - 16
        self._spore_reset = self._spore_path(self.ter_y + 10)
        for i in range(8):
            path = self._spore_path(ty - (i * 11) % 64)
            self.spores.append(
                [
                    tx + (i * 7) % 36,
                    path[0],
                    i * 31,
                    LIME_GLOW if (i & 1) == 0 else AQUA_GLOW,
                    path,
                    0,
                ]
            )

    # The whole pixel rows a spore starting at y passes through, rising 0.45 a frame,
    # until it drops below the terrarium again. The float steps are taken here once,
    # so a frame only reads the next row.
    def _spore_path(self, y):
        limit = self.ter_y - 34
        rows = [int(y)]
        while True:
            y -= 0.45
            if y < limit:
                return array("h", rows)
            rows.append(int(y))

    # The box every spore stays in, glow included.
    def _spore_bounds(self):
        sways = [(isin(p) * 3) >> 10 for p in range(256)]
        xs = [sp[0] for sp in self.spores]
        ys = list(self._spore_reset)
        for sp in self.spores:
            ys.extend(sp[4])
        x0 = min(xs) + min(sways) - 7
        y0 = min(ys) - 7
        return (x0, y0, max(xs) + max(sways) + 9 - x0, max(ys) + 9 - y0)

    # The box around every rectangle put(out, n, phase) makes, over all phases.
    def _bounds(self, put):
        out = array("h", bytes(8 * 4))
        x0 = y0 = 32767
        x1 = y1 = -32768
        for phase in range(256):
            n = put(out, 0, phase)
            for i in range(0, n, 4):
                x0 = min(x0, out[i])
                y0 = min(y0, out[i + 1])
                x1 = max(x1, out[i] + out[i + 2])
                y1 = max(y1, out[i + 1] + out[i + 3])
        return (x0, y0, x1 - x0, y1 - y0)

    # box, if restoring it every frame can't erase anything drawn only now and then:
    # the cards, the buttons or the stage bar. Otherwise None, and its parts are
    # restored one rectangle at a time.
    def _safe(self, box):
        x, y, w, h = box
        if y < self.lay.scene_y:
            return None
        for ox, oy, ow, oh in self._cards:
            if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                return None
        return box

    # Render the static workshop wall, observatory window, workbench, and holo frames.
    def _build_static_background(self):
        fb = self.bg_fb
        lay = self.lay
        w = lay.w
        sy = lay.scene_y
        sh = lay.scene_h

        # Paint the workshop back wall gradient and subtle steel paneling seams.
        paint_gradient(fb, 0, sy, w, self.desk_y - sy, NIGHT_RGB, DEEP_SLATE_RGB, step=3)
        seam_step = 48 if lay.compact else 64
        for x in range(seam_step, w, seam_step):
            fb.vline(x, sy, self.desk_y - sy, NIGHT)
            fb.pixel(x + 1, sy + 8, STEEL)
            fb.pixel(x + 1, self.desk_y - 10, STEEL)

        # Draw the arched night-sky observatory window on the left wall.
        wx, wy, ww, wh = self.win_rect
        draw_pixel_panel(fb, wx, wy, ww, wh, VOID, STEEL, SILVER, ABYSS)
        paint_gradient(fb, wx + 3, wy + 3, ww - 6, wh - 6, VOID_RGB, ABYSS_RGB, step=2)

        # Draw twin solarpunk moons inside the window.
        moon_x = wx + ww - (26 if lay.compact else 38)
        moon_y = wy + (22 if lay.compact else 30)
        moon_r = 10 if lay.compact else 14
        fb.ellipse(moon_x, moon_y, moon_r, moon_r, SUN_YELLOW, True)
        fb.ellipse(moon_x - 4, moon_y - 3, moon_r - 2, moon_r - 2, VOID, True)
        fb.ellipse(moon_x - moon_r - 14, moon_y + 12, 4, 4, AQUA_GLOW, True)

        # Draw silhouetted solarpunk botanical domes and spires along the horizon.
        hor_y = wy + wh - (26 if lay.compact else 36)
        fb.fill_rect(wx + 3, hor_y, ww - 6, wy + wh - 3 - hor_y, NIGHT)
        dome_x1 = wx + int(ww * 0.28)
        dome_x2 = wx + int(ww * 0.65)
        fb.ellipse(dome_x1, hor_y, int(ww * 0.18), 14, DEEP_TEAL, True)
        fb.ellipse(dome_x2, hor_y + 2, int(ww * 0.14), 10, DARK_MOSS, True)
        fb.vline(dome_x1, hor_y - 22, 22, CYAN)
        fb.pixel(dome_x1, hor_y - 23, ICE_CYAN)
        # Window muntin bars and brass sill.
        fb.hline(wx + 3, wy + int(wh * 0.45), ww - 6, SLATE)
        fb.vline(wx + ww // 2, wy + 3, wh - 6, SLATE)
        fb.fill_rect(wx - 2, wy + wh - 2, ww + 4, 5, BRONZE)
        fb.hline(wx - 2, wy + wh - 2, ww + 4, GOLD)

        # Draw a hanging solarpunk bookshelf and overhead pendant lamp above Bit.
        shelf_x = wx + ww + (16 if lay.compact else 26)
        shelf_w = self.card_chrono[0] - shelf_x - (16 if lay.compact else 26)
        shelf_y = wy + (26 if lay.compact else 38)
        if shelf_w > 60:
            # Brass ceiling suspension rods and oak shelf plank.
            fb.vline(shelf_x + 10, sy, shelf_y - sy, BRONZE)
            fb.vline(shelf_x + shelf_w - 11, sy, shelf_y - sy, BRONZE)
            fb.fill_rect(shelf_x, shelf_y, shelf_w, 6, OAK)
            fb.hline(shelf_x, shelf_y, shelf_w, GOLD)
            fb.hline(shelf_x, shelf_y + 5, shelf_w, DARK_WOOD)
            # Pixel-art technical manuals on the shelf.
            bx = shelf_x + 14
            for b_col, b_h in ((CORAL, 18), (CYAN, 22), (GOLD, 16), (EMERALD, 20), (NEON_PINK, 17)):
                if bx + 10 < shelf_x + shelf_w - 36:
                    fb.fill_rect(bx, shelf_y - b_h, 7, b_h, b_col)
                    fb.hline(bx + 1, shelf_y - b_h + 3, 5, WHITE)
                    bx += 9
            # Glowing plasma specimen jar on the right end of the shelf.
            jx = shelf_x + shelf_w - 28
            fb.fill_rect(jx, shelf_y - 18, 12, 18, DEEP_TEAL)
            fb.rect(jx, shelf_y - 18, 12, 18, SILVER)
            fb.fill_rect(jx + 3, shelf_y - 12, 6, 9, AQUA_GLOW)
            fb.fill_rect(jx + 2, shelf_y - 20, 8, 3, GOLD)
            # Trailing bioluminescent ivy vine hanging from the left shelf edge.
            for vy_step in range(0, 28, 5):
                fb.fill_rect(shelf_x + 3 + (vy_step & 1) * 2, shelf_y + 6 + vy_step, 4, 4, EMERALD)
                fb.pixel(shelf_x + 4, shelf_y + 7 + vy_step, LIME_GLOW)

        # Draw the warm oak and brushed-copper maker workbench surface.
        desk_h = (sy + sh) - self.desk_y
        fb.fill_rect(0, self.desk_y, w, desk_h, DARK_WOOD)
        fb.fill_rect(0, self.desk_y, w, 10, OAK)
        fb.hline(0, self.desk_y, w, GOLD)
        fb.hline(0, self.desk_y + 1, w, AMBER)
        fb.hline(0, self.desk_y + 9, w, BRONZE)

        # Draw maker tool drawers and an illuminated power bus on the workbench apron.
        apron_y = self.desk_y + (16 if lay.compact else 22)
        apron_h = self.btn_bar_y - apron_y - (6 if lay.compact else 10)
        if apron_h >= 24:
            dw = int(ww * 0.92)
            draw_pixel_panel(fb, wx, apron_y, dw, apron_h, OAK, BRONZE, GOLD)
            mid_ay = apron_y + (apron_h >> 1)
            fb.hline(wx + 4, mid_ay, dw - 8, DARK_WOOD)
            fb.fill_rect(wx + (dw >> 1) - 12, apron_y + 6, 24, 4, GOLD)
            fb.fill_rect(wx + (dw >> 1) - 12, mid_ay + 6, 24, 4, GOLD)

            bus_x = self.bit_home_x - (56 if lay.compact else 78)
            bus_w = 112 if lay.compact else 156
            draw_pixel_panel(fb, bus_x, apron_y, bus_w, apron_h, ABYSS, TEAL, CYAN)
            bus_lbl = "LAB BUS" if lay.compact else "LAB POWER BUS"
            fb.text(bus_lbl, bus_x + ((bus_w - len(bus_lbl) * 8) >> 1), apron_y + 6, AQUA_GLOW)
            for i in range(6):
                lx = bus_x + 10 + i * (16 if lay.compact else 22)
                ly = apron_y + apron_h - (12 if lay.compact else 16)
                lcol = LIME_GLOW if i < 4 else GOLD
                fb.fill_rect(lx, ly, 10 if lay.compact else 14, 6, lcol)

        # Draw the holographic emitter pad on the workbench beneath Bit.
        pad_rx = 44 if lay.compact else 64
        pad_ry = 8 if lay.compact else 11
        pad_cy = self.desk_y + (4 if lay.compact else 5)
        fb.ellipse(self.bit_home_x, pad_cy, pad_rx + 6, pad_ry + 2, BRONZE, True)
        fb.ellipse(self.bit_home_x, pad_cy, pad_rx, pad_ry, DEEP_TEAL, True)
        fb.ellipse(self.bit_home_x, pad_cy, pad_rx, pad_ry, CYAN, False)
        fb.ellipse(self.bit_home_x, pad_cy, pad_rx >> 1, max(2, pad_ry >> 1), AQUA_GLOW, False)

        # Blit the static terrarium capsule and copper coffee mug onto the left desk.
        ter = self.sprites.terrarium
        mug = self.sprites.mug
        self.ter_x = wx + 12
        self.ter_y = self.desk_y - ter.h + 4
        ter.draw(fb, self.ter_x, self.ter_y)

        self.mug_x = self.ter_x + ter.w + (12 if lay.compact else 20)
        self.mug_y = self.desk_y - mug.h + 4
        mug.draw(fb, self.mug_x, self.mug_y)

        # Draw the three right-hand holographic HUD card frames.
        for rect, border in (
            (self.card_chrono, CYAN),
            (self.card_voice, EMERALD),
            (self.card_speech, AMBER),
        ):
            cx, cy, cw, ch = rect
            draw_pixel_panel(fb, cx, cy, cw, ch, ABYSS, border, ICE_CYAN, VOID)

    # Trigger one of the 5 companion actions by index (0..4).
    def trigger_action(self, idx):
        idx = idx % len(ACTIONS)
        self.active_btn = idx
        _, mood, emote_key, _, speech = ACTIONS[idx]
        self.mood = mood
        self.mood_ms = 4000
        self.speech_full = speech
        self.speech_chars = 0
        self.bounce_vy = -5.5
        if mood == "scan":
            self.scan_sweep = 1.0
        self.sound.chirp(mood)
        self._spawn_emotes(emote_key, 4)

    # Spawn floating pixel-art reaction emotes around Bit.
    def _spawn_emotes(self, emote_key, count=3):
        for i in range(count):
            ox = rng_int(-42, 42)
            oy = rng_int(-28, 10)
            vx = (ox / 28.0) + (i - 1) * 0.35
            vy = -1.2 - rng_int(0, 10) * 0.1
            self.particles.append(
                [
                    float(self.bit_home_x + ox),
                    float(self.bit_home_y - 18 + oy),
                    vx,
                    vy,
                    emote_key,
                    100000,
                ]
            )
        if len(self.particles) > 14:
            self.particles = self.particles[-14:]

    # Handle pointer down inside the Workshop scene; return True if consumed.
    def on_pointer_down(self, x, y):
        self.update_pointer_look(x, y)
        # Check the 5 bottom action buttons first.
        for i, (bx, by, bw, bh) in enumerate(self.btn_rects):
            if bx <= x < bx + bw and by <= y < by + bh:
                self.trigger_action(i)
                return True
        # Check if the user tapped directly on Bit to pet/boop the robot.
        body = self.sprites.bit_body[0]
        if (
            abs(x - self.bit_home_x) <= (body.w >> 1) + 12
            and abs(y - self.bit_home_y) <= (body.h >> 1) + 12
        ):
            next_act = (self.active_btn + 1) % len(ACTIONS)
            self.trigger_action(next_act)
            return True
        # Check if the user tapped the coffee mug or terrarium.
        if self.mug_x <= x <= self.mug_x + self.sprites.mug.w and y >= self.mug_y - 10:
            self.trigger_action(3)
            return True
        if self.ter_x <= x <= self.ter_x + self.sprites.terrarium.w and y >= self.ter_y - 10:
            self.trigger_action(2)
            return True
        return False

    # Aim Bit's CRT eyes toward the latest pointer coordinate.
    def update_pointer_look(self, x, y):
        dx = (x - self.bit_home_x) // 28
        dy = (y - self.bit_home_y) // 32
        self.look_dx = max(-6, min(6, dx))
        self.look_dy = max(-4, min(4, dy))

    # Advance physics, particles, typewriter text, and attract-mode choreography.
    def update(self, dt, auto_mode=True):
        self.phase = (self.phase + 4) & 0xFF
        # The timers count whole ms, so a frame boxes no floats for them.
        dt_ms = round(dt * 1000.0)
        self.time_ms += dt_ms

        # Advance typewriter speech reveal.
        if self.speech_chars < len(self.speech_full):
            self.speech_chars = min(
                len(self.speech_full), self.speech_chars + max(1, dt_ms * 42 // 1000)
            )

        # Spring physics for Bit's excited vertical bounce.
        if self.bounce_y != 0.0 or self.bounce_vy != 0.0:
            self.bounce_y += self.bounce_vy
            self.bounce_vy += 0.48
            if self.bounce_y >= 0.0 and self.bounce_vy > 0.0:
                self.bounce_y = 0.0
                self.bounce_vy = 0.0

        if self.scan_sweep > 0.0:
            self.scan_sweep = max(0.0, self.scan_sweep - dt * 0.85)

        # Decay temporary reaction moods back to happy/neutral.
        if self.mood_ms > 0:
            self.mood_ms -= dt_ms
            if self.mood_ms <= 0 and self.mood != "sleep":
                self.mood = "happy"

        # Attract-mode choreography: cycle through Bit's reactions automatically.
        if auto_mode:
            self.look_dx = (isin(self.phase >> 1) * 5) >> 10
            self.look_dy = (icos(self.phase >> 1) * 3) >> 10
            self.auto_ms -= dt_ms
            if self.auto_ms <= 0:
                self.auto_ms = 3400
                self.auto_index = (self.auto_index + 1) % len(ACTIONS)
                self.trigger_action(self.auto_index)

        # Update floating emote particles.
        i = len(self.particles) - 1
        while i >= 0:
            p = self.particles[i]
            p[0] += p[2]
            p[1] += p[3]
            p[5] -= dt_ms * 65
            if p[5] <= 0:
                self.particles.pop(i)
            i -= 1

        # Update rising terrarium spores.
        for sp in self.spores:
            step = sp[5] + 1
            if step >= len(sp[4]):
                sp[4] = self._spore_reset
                step = 0
            sp[5] = step
            sp[1] = sp[4][step]
            sp[2] = (sp[2] + 5) & 0xFF

    # Render the complete Workshop scene into the target FrameBuffer.
    def draw(self, fb, draw_obj=None, st=None):
        # Copy the pre-rendered workshop interior in one fast C-level blit.
        copy_frame(fb, self.bg_fb)
        if st is not None:
            st.sig = {}
        self._draw_scene(fb, st, True, SPEECH_ALL, True, True)
        if st is not None:
            if st.moved is None:
                st.moved = array("h", bytes(8 * MAX_MOVED))
            st.moved_n = self._moving(st.moved)
            self._remember(st.sig)

    # Record in sig what the speech card, buttons and mood card show now.
    def _remember(self, sig):
        sig["speech_text"] = self.speech_full
        sig["speech_chars"] = self.speech_chars
        sig["buttons"] = self.active_btn
        sig["mood"] = self.mood

    # Repaint only what moved since this display buffer was last drawn.
    def draw_changes(self, fb, draw_obj, st):
        cur = self._moved
        n = self._moving(cur)
        w = self.lay.w
        h = self.lay.h
        view = self.bg_view
        sig = st.sig
        buttons = sig.get("buttons") != self.active_btn
        mood = sig.get("mood") != self.mood
        # An emote can drift over a card, and restoring where it was erases what the card
        # draws only now and then, so a card it touched is drawn again.
        touched = self._touched(cur, n) | self._touched(st.moved, st.moved_n)
        buttons = buttons or touched & 8
        if sig.get("speech_text") != self.speech_full or touched & 4:
            speech = SPEECH_ALL
        elif sig.get("speech_chars") != self.speech_chars:
            speech = SPEECH_ADD if self._speech_grew(sig.get("speech_chars")) else SPEECH_ALL
        else:
            speech = SPEECH_SAME
        restore_sources(fb, self.fixed_sources)
        for i in range(0, n, 4):
            restore_area(fb, view, cur[i], cur[i + 1], cur[i + 2], cur[i + 3], w, h)
        # What this buffer showed last time, unless it was just restored above.
        was = st.moved
        for j in range(0, st.moved_n, 4):
            x = was[j]
            y = was[j + 1]
            rw = was[j + 2]
            rh = was[j + 3]
            for i in range(0, n, 4):
                if cur[i] == x and cur[i + 1] == y and cur[i + 2] == rw and cur[i + 3] == rh:
                    break
            else:
                restore_area(fb, view, x, y, rw, rh, w, h)
        if speech == SPEECH_ALL:
            cx, cy, cw, ch = self.card_speech
            restore_area(fb, view, cx + 6, cy + 18, cw - 12, ch - 18, w, h)
        if buttons:
            restore_rects(fb, view, self.btn_rects, w, h)
        if mood:
            cx, cy, cw, ch = self.card_voice
            restore_area(fb, view, cx + 4, cy + 4, cw - 8, 12, w, h)
        # The clock's text up to its hundredths, when the second changed (16).
        if sig.get("clock") != self.time_ms // 1000:
            cx, cy, cw, ch = self.card_chrono
            restore_area(fb, view, cx + 4, cy + 17, cw - 8, 21, w, h)
            touched |= 16
        self._draw_scene(fb, st, False, speech, buttons, mood, touched)
        st.moved = cur
        st.moved_n = n
        self._moved = was
        self._remember(sig)

    # Which of the chrono card (1), the voice card (2), the speech card (4) and the
    # button bar (8) the n numbers of rectangles in rects overlap, as bits.
    def _touched(self, rects, n):
        bits = 0
        for i in range(0, n, 4):
            x = rects[i]
            y = rects[i + 1]
            x1 = x + rects[i + 2]
            y1 = y + rects[i + 3]
            bit = 1
            for ox, oy, ow, oh in self._cards:
                if x < ox + ow and ox < x1 and y < oy + oh and oy < y1:
                    bits |= bit
                bit <<= 1
        return bits

    # Put the rectangle x, y, w, h in out at n and return where the next one goes.
    @staticmethod
    def _put(out, n, x, y, w, h):
        out[n] = x
        out[n + 1] = y
        out[n + 2] = w
        out[n + 3] = h
        return n + 4

    # Put in out the rectangles of what the scene paints over the background now, apart
    # from the fixed sources and the boxes, and return how many numbers that took.
    def _moving(self, out):
        put = self._put
        n = 0
        wx, wy, ww, wh = self.win_rect
        meteor_tick = (self.phase >> 1) & 0x7F
        if meteor_tick < 24:
            mx = wx + 14 + meteor_tick * ((ww - 36) // 24)
            my = wy + 10 + meteor_tick * 2
            n = put(out, n, mx - 8, my - 4, 9, 5)
        if self._spore_box is None:
            for sp in self.spores:
                sx = sp[0] + ((isin(sp[2]) * 3) >> 10)
                n = put(out, n, sx - 7, sp[1] - 7, 16, 16)
        if self._steam_box is None:
            n = self._put_steam(out, n, self.phase)
        if self._pad_box is None:
            n = self._put_pad(out, n, self.phase)
        # Bit stays in his box unless a bounce lifts him out of it.
        m = self._put_bit(out, n, self.phase, int(self.bounce_y))
        box = self._bit_box
        if (
            box is None
            or out[n] < box[0]
            or out[n + 1] < box[1]
            or out[n] + out[n + 2] > box[0] + box[2]
            or out[n + 1] + out[n + 3] > box[1] + box[3]
        ):
            n = m
        if self.scan_sweep > 0.0:
            scan_y = int(
                self.lay.scene_y
                + 24
                + (1.0 - self.scan_sweep) * (self.desk_y - self.lay.scene_y - 16)
            )
            beam_x0 = wx + 8
            n = put(out, n, beam_x0, scan_y, self.card_chrono[0] - beam_x0 - 8, 2)
        for p in self.particles:
            em = self.sprites.emotes.get(p[4])
            if em is not None and n < len(out):
                n = put(out, n, int(p[0]) - (em.w >> 1), int(p[1]) - (em.h >> 1), em.w, em.h)
        return n

    # Put the three steam puffs' rectangles at phase in out at n.
    def _put_steam(self, out, n, phase):
        for i in range(3):
            p = (phase + i * 85) & 0xFF
            rise = (p * 26) >> 8
            sway = (isin((p * 2) & 0xFF) * 4) >> 10
            st_x = self.mug_x + (self.sprites.mug.w >> 1) - 2 + sway
            n = self._put(out, n, st_x, self.mug_y - 4 - rise, 3, 2)
        return n

    # Put the pad ring's rectangle at phase in out at n.
    def _put_pad(self, out, n, phase):
        pad_cy = self.desk_y + (4 if self.lay.compact else 5)
        pulse_r = (34 if self.lay.compact else 50) + ((isin(phase * 2) * 6) >> 10)
        return self._put(out, n, self.bit_home_x - pulse_r - 1, pad_cy - 7, pulse_r * 2 + 3, 15)

    # Put the rectangle of Bit, his thruster flame and the glows around them at phase,
    # bounced by bounce pixels, in out at n.
    def _put_bit(self, out, n, phase, bounce=0):
        bob = ((isin(phase) * (5 if self.lay.compact else 8)) >> 10) + bounce
        bit_cy = self.bit_home_y + bob
        frame = (phase >> 4) & 1
        body = self.sprites.bit_body[frame & 1]
        flame = self.sprites.flames[frame % len(self.sprites.flames)]
        px = self.sprites.pet_px
        top = bit_cy - (body.h >> 1)
        flame_cy = top + body.h - px + (flame.h >> 1)
        half = max(body.w >> 1, 12) + px * 2 + 2
        bottom = max(top + body.h - px + flame.h, flame_cy + 12, top + body.h) + 2
        return self._put(out, n, self.bit_home_x - half, top - 10, half * 2, bottom - top + 10)

    # Paint everything that moves. The speech card's text as speech asks, the buttons
    # and the mood label only when asked, and the cards' fixed labels only when full.
    def _draw_scene(self, fb, st, full, speech, buttons, mood, touched=0):
        # Animate twinkling stars and a periodic shooting star in the window.
        wx, wy, ww, wh = self.win_rect
        for sx, sy_star, offs in self.stars:
            b = isin((self.phase + offs) & 0xFF)
            col = WHITE if b > 600 else (AQUA_GLOW if b > 0 else STEEL)
            fb.pixel(sx, sy_star, col)
            if b > 780:
                fb.hline(sx - 1, sy_star, 3, ICE_CYAN)
                fb.vline(sx, sy_star - 1, 3, ICE_CYAN)

        meteor_tick = (self.phase >> 1) & 0x7F
        if meteor_tick < 24:
            mx = wx + 14 + meteor_tick * ((ww - 36) // 24)
            my = wy + 10 + meteor_tick * 2
            fb.line(mx - 8, my - 4, mx, my, ICE_CYAN)
            fb.pixel(mx, my, WHITE)

        # Draw rising bioluminescent spores above the terrarium with soft alpha glow.
        for sp in self.spores:
            sx = int(sp[0]) + ((isin(sp[2]) * 3) >> 10)
            sy_sp = int(sp[1])
            self.sprites.draw_glow(fb, sx + 1, sy_sp + 1, sp[3], large=False)
            fb.fill_rect(sx, sy_sp, 2, 2, WHITE)

        # Draw curling warm steam puffs above the copper coffee mug.
        for i in range(3):
            p = (self.phase + i * 85) & 0xFF
            rise = (p * 26) >> 8
            sway = (isin((p * 2) & 0xFF) * 4) >> 10
            st_x = self.mug_x + (self.sprites.mug.w >> 1) - 2 + sway
            st_y = self.mug_y - 4 - rise
            col = WHITE if rise < 12 else MIST
            fb.fill_rect(st_x, st_y, 3, 2, col)

        # Draw pulsing holographic rings and vertical projection beams under Bit.
        pad_cy = self.desk_y + (4 if self.lay.compact else 5)
        pulse_r = (34 if self.lay.compact else 50) + ((isin(self.phase * 2) * 6) >> 10)
        fb.ellipse(self.bit_home_x, pad_cy, pulse_r, 6, AQUA_GLOW, False)

        # Compute Bit's vertical hover bob + bounce offset.
        bob = ((isin(self.phase) * (5 if self.lay.compact else 8)) >> 10) + int(self.bounce_y)
        bit_cy = self.bit_home_y + bob

        # Choose current expression (with natural periodic blink in happy/neutral mood).
        draw_mood = self.mood
        if draw_mood in ("happy", "neutral") and ((self.phase & 0x7F) > 120):
            draw_mood = "blink"

        self.sprites.draw_workshop_bit(
            fb,
            self.bit_home_x,
            bit_cy,
            (self.phase >> 4) & 1,
            draw_mood,
            self.look_dx,
            self.look_dy,
            glow_col=AQUA_GLOW,
        )

        # If SCAN is active, sweep a glowing laser visor beam across the scene.
        if self.scan_sweep > 0.0:
            scan_y = int(
                self.lay.scene_y
                + 24
                + (1.0 - self.scan_sweep) * (self.desk_y - self.lay.scene_y - 16)
            )
            beam_x0 = wx + 8
            beam_w = self.card_chrono[0] - beam_x0 - 8
            fb.hline(beam_x0, scan_y, beam_w, LIME_GLOW)
            fb.hline(beam_x0, scan_y + 1, beam_w, EMERALD)

        # Draw floating pixel-art reaction emotes.
        for p in self.particles:
            em = self.sprites.emotes.get(p[4])
            if em is not None:
                em.draw_center(fb, int(p[0]), int(p[1]))

        # Draw the three live right-side holographic companion cards.
        self._draw_chrono_card(fb, st, full, touched & 17)
        self._draw_voice_card(fb, full, mood or touched & 2)
        if full or touched & 4:
            fb.text("BIT // ASSISTANT LOG", self.card_speech[0] + 8, self.card_speech[1] + 6, GOLD)
        if speech == SPEECH_ADD:
            self._type_speech(fb)
        elif speech == SPEECH_ALL:
            self._draw_speech_card(fb)
        if buttons:
            self._draw_action_buttons(fb)

    # Render Card 1: Lab Chrono, Solar Charge, and 7-bar Eco Telemetry.
    # The clock's text up to its hundredths changes once a second, so it's drawn then,
    # and the hundredths, whose background is a fixed source, every frame. touched
    # has bit 1 when something moved over the card and bit 16 when the second changed.
    def _draw_chrono_card(self, fb, st, full, touched=0):
        cx, cy, cw, ch = self.card_chrono
        compact = self.lay.compact
        if full or touched & 1:
            hdr = "LAB // CHRONO" if compact else "SOLARPUNK LAB // CHRONO"
            fb.text(hdr, cx + 8, cy + 6, AQUA_GLOW)
        secs = self.time_ms // 1000
        if full or touched:
            if secs != self._clock_s:
                self._clock_s = secs
                self._clock_text = "08:%02d:%02d." % (24 + ((secs // 60) % 35), secs % 60)
            if compact:
                fb.text(self._clock_text, cx + 8, cy + 18, WHITE)
            else:
                fb.text16(self._clock_text, cx + 8, cy + 20, WHITE)
            if st is not None:
                st.sig["clock"] = secs
        frames = TWO_DIGITS[(self.phase >> 2) % 60]
        if compact:
            fb.text(frames, cx + 80, cy + 18, WHITE)
        else:
            fb.text16(frames, cx + 80, cy + 20, WHITE)

        # Solar array charge indicator + animated mini bar chart on the right.
        bar_y = cy + ch - (14 if compact else 18)
        if full or touched & 1:
            fb.text("SOLAR 99%", cx + 8, bar_y, LIME_GLOW)
        bx0 = cx + cw - (64 if self.lay.compact else 84)
        for i in range(7):
            bh = 6 + (((isin(self.phase + i * 29) + 1024) * (ch - 26)) >> 12)
            bx = bx0 + i * (8 if self.lay.compact else 10)
            col = LIME_GLOW if (i & 1) == 0 else CYAN
            fb.fill_rect(bx, cy + ch - 7 - bh, 5 if self.lay.compact else 6, bh, col)

    # Render Card 2: Live Voice Synthesizer Waveform and Biometric Status.
    # The header and the mood label only when full or the mood changed, as the mood's
    # repaint is the only thing that paints over them.
    def _draw_voice_card(self, fb, full, mood):
        cx, cy, cw, ch = self.card_voice
        if full or mood:
            hdr = "VOICE SYNTH" if self.lay.compact else "VOICE SYNTH & MOOD"
            fb.text(hdr, cx + 8, cy + 6, LIME_GLOW)
        if full or mood:
            if self._mood_label[0] != self.mood:
                label = self.mood.upper() if self.lay.compact else f"MOOD:{self.mood.upper()}"
                self._mood_label = (self.mood, label)
            mood_label = self._mood_label[1]
            fb.text(mood_label, cx + cw - len(mood_label) * 8 - 8, cy + 6, GOLD)

        # Draw real-time voice waveform inside a dark scope well.
        wx = cx + 8
        wy = cy + 18
        ww = cw - 16
        wh = ch - 26
        fb.fill_rect(wx, wy, ww, wh, VOID)
        fb.rect(wx, wy, ww, wh, DEEP_TEAL)
        mid_y = wy + (wh >> 1)
        fb.hline(wx + 1, mid_y, ww - 2, DEEP_SLATE)

        samples = self.sound.scope_samples
        n = len(samples)
        prev_x = wx + 2
        prev_y = mid_y
        span_w = max(1, ww - 4)
        half_h = max(4, (wh >> 1) - 3)
        for i in range(n):
            sx = wx + 2 + (i * span_w) // (n - 1)
            sy_pt = mid_y - ((samples[i] * half_h) // 100)
            if i > 0:
                fb.line(prev_x, prev_y, sx, sy_pt, AQUA_GLOW)
            prev_x = sx
            prev_y = sy_pt

    # Render Card 3: Companion Typewriter Speech Bubble with Word Wrapping.
    def _draw_speech_card(self, fb):
        cx, cy, cw, ch = self.card_speech
        line_h = self._speech_line_h
        if self._wraps_simply():
            full = self.speech_full
            spans = self._spans
            for i in range(self._wrap(self.speech_chars, spans)):
                line = full[spans[2 * i] : spans[2 * i + 1]]
                fb.text(line, cx + 8, cy + 20 + i * line_h, CREAM)
            return
        visible = self.speech_full[: self.speech_chars]
        max_cols = self._speech_cols
        words = visible.split(" ")
        lines = []
        cur = ""
        for w in words:
            cand = w if not cur else cur + " " + w
            if len(cand) <= max_cols:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = w[:max_cols]
        if cur:
            lines.append(cur)

        for i, line in enumerate(lines[: self._speech_lines]):
            fb.text(line, cx + 8, cy + 20 + i * line_h, CREAM)

    # True when no word of the speech is wider than the card. Then each line is one
    # stretch of speech_full, which _wrap finds without making strings.
    def _wraps_simply(self):
        text = self.speech_full
        if self._simple_text is not text:
            self._simple_text = text
            self._simple = all(len(w) <= self._speech_cols for w in text.split(" "))
        return self._simple

    # Wrap the first n letters of the speech as the card shows them, a line breaking
    # before the word that won't fit. Line i is speech_full[spans[2i]:spans[2i + 1]].
    # Returns how many lines the card shows.
    def _wrap(self, n, spans):
        full = self.speech_full
        cols = self._speech_cols
        most = self._speech_lines
        count = 0
        start = end = 0
        word = 0
        while True:
            space = full.find(" ", word, n)
            word_end = n if space < 0 else space
            if end == start:
                start = word
                end = word_end
            elif word_end - start <= cols:
                end = word_end
            else:
                if count < most:
                    spans[2 * count] = start
                    spans[2 * count + 1] = end
                count += 1
                start = word
                end = word_end
            if space < 0:
                break
            word = space + 1
        if end > start:
            if count < most:
                spans[2 * count] = start
                spans[2 * count + 1] = end
            count += 1
        return min(count, most)

    # True when the speech, typed on from was_n letters, only adds letters to the ends
    # of the lines this buffer shows, so _type_speech can draw just those.
    def _speech_grew(self, was_n):
        if was_n is None or was_n > self.speech_chars or not self._wraps_simply():
            return False
        was = self._spans_was
        now = self._spans
        self._lines_was = self._wrap(was_n, was)
        self._lines = self._wrap(self.speech_chars, now)
        if self._lines_was > self._lines:
            return False
        for i in range(self._lines_was):
            if was[2 * i] != now[2 * i] or was[2 * i + 1] > now[2 * i + 1]:
                return False
        return True

    # Draw the letters typed since this buffer last showed the speech, from the spans
    # _speech_grew just worked out.
    def _type_speech(self, fb):
        cx, cy, _, _ = self.card_speech
        full = self.speech_full
        was = self._spans_was
        now = self._spans
        for i in range(self._lines):
            start = now[2 * i]
            end = now[2 * i + 1]
            a = was[2 * i + 1] if i < self._lines_was else start
            if end > a:
                fb.text(full[a:end], cx + 8 + (a - start) * 8, cy + 20 + i * self._speech_line_h, CREAM)

    # Render the 5 interactive companion reaction buttons along the bottom bar.
    def _draw_action_buttons(self, fb):
        for i, (bx, by, bw, bh) in enumerate(self.btn_rects):
            label, _, _, accent, _ = ACTIONS[i]
            active = i == self.active_btn
            bg = DEEP_TEAL if active else NIGHT
            border = accent if active else STEEL
            draw_pixel_panel(fb, bx, by, bw, bh, bg, border, WHITE if active else None)
            # Trim button label if needed on compact 480x320 screens.
            text = label if len(label) * 8 <= bw - 8 else label[2:]
            tx = bx + ((bw - len(text) * 8) >> 1)
            ty = by + ((bh - 8) >> 1)
            fb.text(text, tx, ty, WHITE if active else SILVER)
