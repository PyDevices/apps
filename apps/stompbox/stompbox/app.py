"""The app: the engine, the screen, and what joins them.

    python run.py [--clips DIR] [--clip NAME] [--effect NAME]
                  [--play] [--record OUT.wav] [--turn T:key=value ...]
                  [--quit-after SECONDS] [--size WxH]
                  [--live [IN_ID]] [--out OUT_ID] [--clock auto|same|two]
                  [--target FRAMES]

--turn moves a knob T seconds after start, through the same path a hand
takes, so a run can prove the knobs change the sound. --record writes what
goes to the output. --live plays a capture device through the effect instead
of a clip, and --out picks the speaker; both take a WASAPI endpoint ID, and
either one puts the output on the pump's own WASAPI speaker.

A live input and a speaker on the same device share a clock and pass straight
through. On different devices a drift resampler holds a ring between them at
--target frames (1024, 21 ms, by default). --clock says which case it is when Windows
can't tell (auto asks Windows: the default).

While live, the window shows the latency: what the software path holds plus
the Windows engine's period on each side, updated four times a second.
"""

import os
import sys
import time

from . import effects, engine, inputs, outputs

DEFAULT_CLIPS = "clips"


def ticks():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else a - b


def is_dir(path):
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def find_clips(folder):
    """Every WAV in the folder and the folders under it, by name."""
    found = []
    stack = [folder]
    while stack:
        d = stack.pop()
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            p = d + "/" + n
            if is_dir(p):
                stack.append(p)
            elif n.lower().endswith(".wav"):
                found.append(p)
    found.sort(key=lambda p: p.lower())
    return found


def parse(argv):
    opts = {"clips": DEFAULT_CLIPS, "clip": None, "effect": None,
            "play": False, "record": None, "turns": [], "quit_after": None,
            "size": (960, 600), "live": None, "out": None,
            "clock": "auto", "target": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        v = argv[i + 1] if i + 1 < len(argv) else None
        if a == "--clips":
            opts["clips"] = v.replace("\\", "/"); i += 1
        elif a == "--clip":
            opts["clip"] = v.replace("\\", "/"); i += 1
        elif a == "--effect":
            opts["effect"] = v; i += 1
        elif a == "--live":
            # The default capture device, or the endpoint ID that follows.
            if v is not None and not v.startswith("--"):
                opts["live"] = v; i += 1
            else:
                opts["live"] = ""
        elif a == "--out":
            opts["out"] = v; i += 1
        elif a == "--clock":
            if v not in ("auto", "same", "two"):
                raise SystemExit("--clock takes auto, same or two")
            opts["clock"] = v; i += 1
        elif a == "--target":
            opts["target"] = int(v); i += 1
        elif a == "--play":
            opts["play"] = True
        elif a == "--record":
            opts["record"] = v; i += 1
        elif a == "--turn":
            t, kv = v.split(":", 1)
            k, val = kv.split("=", 1)
            opts["turns"].append((float(t), k, float(val))); i += 1
        elif a == "--quit-after":
            opts["quit_after"] = float(v); i += 1
        elif a == "--size":
            w, h = v.lower().split("x")
            opts["size"] = (int(w), int(h)); i += 1
        else:
            raise SystemExit("unknown option " + a)
        i += 1
    opts["turns"].sort()
    return opts


class App:
    def __init__(self, opts):
        self.opts = opts
        self.clips = find_clips(opts["clips"])
        clip = opts["clip"]
        if clip and clip not in self.clips:
            # A bare name means the one in the clips folder.
            inside = opts["clips"].rstrip("/") + "/" + clip
            if inside in self.clips:
                opts["clip"] = inside
        if opts["clip"] and opts["clip"] not in self.clips:
            self.clips.insert(0, opts["clip"])
        self.all_effects = effects.Airwindows.names()
        carried = set(self.all_effects)
        self.guitar = [n for _, n in effects.guitar_set() if n in carried]
        self.show_all = not self.guitar
        self.effects = self.all_effects if self.show_all else list(self.guitar)
        self.effect_name = None
        # A live input wants the pump-driven speaker: through audiodev's
        # player it would sit behind two Python-fed queues.
        if (opts["live"] is not None or opts["out"]) \
                and outputs.WasapiOutput.available():
            self.output = outputs.WasapiOutput(opts["out"] or None)
        else:
            self.output = outputs.DefaultOutput()
        self.engine = engine.Engine(self.output)
        self.screen = None
        self._t0 = ticks()
        self._play_t = None
        self._lat = []          # the last second of latency samples
        # None, not 0: ticks_diff against 0 is meaningless where ticks_ms
        # starts near the top of its range (the Windows port does).
        self._lat_t = None
        self._lat_print = None

    # -- names for the screen ------------------------------------------------

    def clip_names(self):
        root = self.opts["clips"].rstrip("/") + "/"
        return [p[len(root):] if p.startswith(root) else p for p in self.clips]

    def effect_names(self):
        return self.effects

    # -- what the screen asks for --------------------------------------------

    def pick_clip(self, index):
        if not (0 <= index < len(self.clips)):
            return
        path = self.clips[index]
        try:
            inp = inputs.ClipInput(path)
        except (OSError, ValueError) as e:
            self.status("Can't play that clip: %s" % e)
            return
        self.engine.set_input(inp)
        if self.engine.playing:
            self._play_t = ticks()
        self.status("%s, %d Hz, %.1f s" % (inp.name(), inp.file_rate, inp.seconds))

    def go_live(self, device=None):
        """The capture device through the effect, from now on."""
        try:
            inp = inputs.LiveInput(device, speaker=self.opts["out"] or None,
                                   clock=self.opts["clock"],
                                   target=self.opts["target"])
        except (OSError, ImportError, ValueError, TypeError) as e:
            self.status("Can't open the live input: %s" % e)
            return
        self.engine.set_input(inp)
        self.engine.play()
        out = getattr(self.output, "name", "the output")
        if inp.clocks == 1:
            clock = "One clock (same device): straight through"
        else:
            clock = ("Two clocks: a drift resampler holds %.0f ms between them"
                     % (inp.target * 1000 / inp.sample_rate))
        route = "%s  %s  %s" % (inp.name_in, lv_arrow(), out)
        print("live:", route, "|", clock)
        if self.screen is not None:
            self.screen.show_live(route, clock)
        self.status("Live input, %d Hz" % inp.sample_rate, good=True)

    def pick_effect(self, index):
        if not (0 <= index < len(self.effects)):
            return
        self.effect_name = self.effects[index]
        fx = self.engine.set_effect("airwindows", self.effect_name)
        if self.screen is not None:
            self.screen.show_effect(fx, index)

    def set_show_all(self, on):
        """Every plug-in, or the guitar set. The effect playing stays, and
        stays in the list even when the guitar set doesn't hold it."""
        self.show_all = on or not self.guitar
        if self.show_all:
            names = self.all_effects
        else:
            names = list(self.guitar)
            if self.effect_name and self.effect_name not in names:
                names.insert(0, self.effect_name)
        self.effects = names
        if self.screen is not None:
            self.screen.show_effect_list(names, self.effects.index(self.effect_name)
                                         if self.effect_name in names else 0,
                                         self.show_all)

    def toggle_play(self):
        if self.engine.playing:
            self.engine.stop()
            self._play_t = None
        else:
            self.engine.play()
            self._play_t = ticks()
        if self.screen is not None:
            self.screen.show_playing(self.engine.playing)

    def set_loop(self, on):
        self.engine.set_loop(on)
        if self.engine.playing:
            self._play_t = ticks()
        if self.screen is not None:
            self.screen.show_loop(on)

    def turn(self, key, value):
        if self.engine.effect is not None:
            self.engine.effect.set(key, value)

    def set_master(self, level):
        self.engine.set_master(level)
        if self.screen is not None:
            self.screen.show_master(level)

    def status(self, text, good=False):
        print(text)
        if self.screen is not None:
            self.screen.show_status(text, good)

    # -- the loop --------------------------------------------------------------

    def tick(self):
        try:
            self._tick()
        except Exception as e:  # noqa: BLE001 - LVGL swallows a timer's errors
            if not getattr(self, "_tick_err", False):
                self._tick_err = True
                print("tick failed:", repr(e))
                import sys
                sys.print_exception(e) if hasattr(sys, "print_exception") else None

    def _tick(self):
        self.engine.service()
        try:
            self._latency()
        except Exception as e:  # noqa: BLE001 - a readout never stops the app
            if not getattr(self, "_lat_err", False):
                self._lat_err = True
                print("latency readout failed:", repr(e))
        s = self.screen
        if s is not None:
            if not self.engine.playing and self._play_t is not None:
                self._play_t = None
                s.show_playing(False)
            inp = self.engine.input
            if self._play_t is not None and inp is not None:
                at = ticks_diff(ticks(), self._play_t) / 1000
                if self.engine.loop and inp.seconds:
                    at = at % inp.seconds
                s.show_position("%s / %s" % (_clock(at), _clock(inp.seconds)))
            elif inp is not None:
                s.show_position("-- / %s" % _clock(inp.seconds))
        self._script()

    def _latency(self):
        """Sample the latency four times a second and show the last second's
        mean, so the figure moves with the path but doesn't flicker."""
        now = ticks()
        if self._lat_t is not None and ticks_diff(now, self._lat_t) < 250:
            return
        self._lat_t = now
        got = self.engine.latency() if self.engine.input is not None \
            and self.engine.input.kind == "live" else None
        if got is None:
            return
        self._lat.append(got)
        if len(self._lat) > 4:
            self._lat.pop(0)
        n = len(self._lat)
        total = sum(x[0] for x in self._lat) / n
        held = sum(x[1] for x in self._lat) / n
        periods = sum(x[2] for x in self._lat) / n
        inp = self.engine.input
        extra = ""
        if inp.drift is not None:
            extra = ", %+.0f ppm, %d underruns" % (inp.drift.ppm,
                                                   inp.drift.underruns)
        if self.screen is not None:
            self.screen.show_latency(total, held, periods, extra)
        if self._lat_print is None or ticks_diff(now, self._lat_print) >= 5000:
            self._lat_print = now
            print("latency %.1f ms = held %.1f + periods %.1f%s"
                  % (total, held, periods, extra))

    def _script(self):
        elapsed = ticks_diff(ticks(), self._t0) / 1000
        turns = self.opts["turns"]
        while turns and turns[0][0] <= elapsed:
            _, key, value = turns.pop(0)
            knob = self.screen.knobs.get(key) if self.screen else None
            if knob is not None:
                knob.turn(value)
            else:
                self.turn(key, value)
            print("%.2f s: %s = %.3f" % (elapsed, key, value))
        q = self.opts["quit_after"]
        if q is not None and elapsed >= q:
            self.quit()

    def quit(self):
        n = self.engine.stop_recording()
        if n is not None:
            print("recorded %d frames to %s" % (n, self.opts["record"]))
        self.engine.close()
        import display_driver

        display_driver.app.request_quit()

    # -- start -----------------------------------------------------------------

    def start(self):
        import lvgl as lv

        from . import ui

        w, h = self.opts["size"]
        self.screen = ui.Screen(self, w, h)
        self.screen.out_label.set_text("Output: %s" % self.output.describe())
        name = self.opts["effect"]
        if name and name not in self.effects and name in self.all_effects:
            self.effect_name = name
            self.set_show_all(False)
        index = self.effects.index(name) if name in self.effects else 0
        self.pick_effect(index)
        self.screen.show_effect_list(self.effects, index, self.show_all)
        if self.opts["clip"] in self.clips:
            ci = self.clips.index(self.opts["clip"])
        else:
            ci = 0
        if self.clips:
            self.screen.clip_dd.set_selected(ci)
            self.pick_clip(ci)
        else:
            self.status("No WAV files in %s" % self.opts["clips"])
        self.set_loop(True)
        if self.opts["live"] is not None:
            self.go_live(self.opts["live"] or None)
        self.set_master(self.engine.master)
        if self.opts["record"]:
            self.engine.record(self.opts["record"])
        if self.opts["play"] and self.clips:
            self.toggle_play()
        # Kept on self: an unreferenced timer and callback can be collected.
        self._tick_cb = lambda t: self.tick()
        self._timer = lv.timer_create(self._tick_cb, 10, None)


def lv_arrow():
    try:
        import lvgl as lv

        return lv.SYMBOL.RIGHT
    except (ImportError, AttributeError):
        return "->"


def _clock(seconds):
    s = int(seconds)
    return "%d:%02d" % (s // 60, s % 60)


def set_title(title):
    """The window's title, where the host has one to set."""
    try:
        import display_driver

        drv = display_driver.display_drv
        hwnd = getattr(drv, "_hwnd", None) or getattr(getattr(drv, "_display", None), "_hwnd", None)
        if hwnd is None:
            return
        import uwin32 as win

        win.SetWindowTextW(hwnd, title)
    except Exception:  # noqa: BLE001 - a title is never worth failing over
        pass


def main(argv=None):
    opts = parse(sys.argv[1:] if argv is None else argv)
    w, h = opts["size"]
    from boarddev import env_set

    env_set("PYDEVICES_WIDTH", w)
    env_set("PYDEVICES_HEIGHT", h)
    env_set("PYDEVICES_SCALE", 1)
    import display_driver

    app = App(opts)
    app.start()
    set_title("Stompbox")
    display_driver.app.run()
