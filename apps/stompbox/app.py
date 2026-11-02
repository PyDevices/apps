"""The app: the engine, the screen, and what joins them.

A computer can set these in its environment; a board needs none of them:

    STOMPBOX_CLIPS    the folder of WAV clips
    STOMPBOX_INPUT    the capture endpoint ID Live opens (Windows)
    STOMPBOX_OUT      the speaker's endpoint ID (Windows)
    STOMPBOX_LIVE     set to anything: open on Live
    STOMPBOX_CLOCK    auto, same or two: whether input and speaker share a clock
    STOMPBOX_TARGET   the frames a drift resampler holds between two clocks

A live input and a speaker on one device share a clock and pass straight
through. On different devices a drift resampler holds a ring between them.
While live on Windows the screen shows the latency: what the software path
holds plus the device engine's period on each side, four times a second.
"""

import os

from appkit import data as appdata
from multimer import ticks_diff, ticks_ms

from . import SAMPLE_RATE, effects, engine, inputs, outputs, ui

try:
    import audiopump
except ImportError:
    audiopump = None

MOUNT = "/sd"
FOLDER = "guitar-clips"

# A board carries plug-ins it can't run in real time: the ones that stay in
# double precision on an FPU without it reach 2% on an ESP32-P4. Nothing fails,
# the sound just arrives in fragments, so the app measures and says so.
WATCH_MS = 1000
KEEPS_UP = 0.9

current = None  # the running App, for the console


def _env(name):
    fn = getattr(os, "getenv", None)
    return (fn(name) or None) if fn is not None else None


def _home():
    return (_env("USERPROFILE") or _env("HOME") or "").replace("\\", "/")


def clips_folder():
    """``$STOMPBOX_CLIPS`` or ``~/music/guitar-clips`` on a computer, the SD card on a board."""
    if appdata.desktop():
        return (_env("STOMPBOX_CLIPS") or _home() + "/music/" + FOLDER).replace("\\", "/")
    return MOUNT + "/" + FOLDER


def _mount(scope):
    """The card, read-only and while the app is open. No card just means no clips."""
    try:
        os.listdir(MOUNT)
        return  # someone else's mount: leave it
    except OSError:
        pass
    try:
        import board_peripherals as bp

        card = bp.sdcard()
        os.mount(card, MOUNT, readonly=True)
    except Exception as e:  # noqa: BLE001 - the app still plays a live input
        print("no SD card:", repr(e))
        return

    def unmount():
        try:
            os.umount(MOUNT)
        finally:
            card.deinit()

    scope.on_close(unmount)


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


class App:
    def __init__(self, scope):
        self.scope = scope
        self.folder = clips_folder()
        self.clips = find_clips(self.folder)
        self.all_effects = effects.Airwindows.names()
        carried = set(self.all_effects)
        self.guitar = [n for _, n in effects.guitar_set() if n in carried]
        self.show_all = not self.guitar
        self.effects = self.all_effects if self.show_all else list(self.guitar)
        self.effect_name = None
        self.can_go_live = inputs.live_available()
        self.speaker = _env("STOMPBOX_OUT")
        # A live input wants the pump-driven speaker: through audiodev's
        # player it would sit behind two Python-fed queues.
        if outputs.WasapiOutput.available():
            self.output = outputs.WasapiOutput(self.speaker)
        else:
            self.output = outputs.DefaultOutput()
        self.engine = engine.Engine(self.output)
        self.screen = None
        self._clip = None       # the clip Live took over from
        self._play_t = None
        self._lat = []          # the last second of latency samples
        # None, not 0: ticks_diff against 0 is meaningless where ticks_ms
        # starts near the top of its range (the Windows port does).
        self._lat_t = None
        self._lat_print = None
        # Boards only, and only while the app is still choosing what to open on.
        self._watching = audiopump is not None and not appdata.desktop()
        self._opening = self._watching
        self._watch_t = None
        self._watch_frames = 0

    # -- names for the screen ------------------------------------------------

    def clip_names(self):
        root = self.folder.rstrip("/") + "/"
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
        except (OSError, ValueError, MemoryError) as e:
            self.status("Can't play that clip: %s" % e)
            return
        self.engine.set_input(inp)
        if self.engine.playing:
            self._play_t = ticks_ms()
        self.status("%s, %d Hz, %.1f s" % (inp.name(), inp.file_rate, inp.seconds))

    def go_live(self):
        """The input through the effect, from now on."""
        self._clip = self.engine.input if self.engine.input is not None \
            and self.engine.input.kind == "clip" else self._clip
        target = _env("STOMPBOX_TARGET")
        try:
            inp = inputs.open_live(_env("STOMPBOX_INPUT"), self.speaker,
                                   _env("STOMPBOX_CLOCK") or "auto",
                                   int(target) if target else None)
        except (OSError, ImportError, ValueError, TypeError, RuntimeError) as e:
            self.status("Can't open the live input: %s" % e)
            if self.screen is not None:
                self.screen.show_live_button(False)
            return
        self._play_t = None
        self.engine.set_input(inp)
        self.engine.play()
        out = getattr(self.output, "name", "the output")
        if inp.clocks == 1:
            clock = "One clock: straight through"
        else:
            clock = ("Two clocks: a drift resampler holds %.0f ms between them"
                     % (inp.target * 1000 / inp.sample_rate))
        route = "%s  %s  %s" % (inp.name_in, ui.lv.SYMBOL.RIGHT, out)
        print("live:", route, "|", clock)
        if self.screen is not None:
            self.screen.show_live(route, clock)
        self.status("Live, %d Hz" % inp.sample_rate, good=True)

    def go_clips(self):
        """Back to the clip Live took over from, stopped."""
        self.engine.stop()
        self.engine.set_input(self._clip)
        self._lat = []
        if self.screen is not None:
            self.screen.show_clips()
            self.screen.show_playing(False)
        self.status("Live is off")

    def set_live(self, on):
        if on:
            self.go_live()
        else:
            self.go_clips()

    def pick_effect(self, index):
        if not (0 <= index < len(self.effects)):
            return
        self.effect_name = self.effects[index]
        fx = self.engine.set_effect("airwindows", self.effect_name)
        if self.screen is not None:
            self.screen.show_effect(fx, index)
        self._watch_t = None

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
            self._play_t = ticks_ms()
        if self.screen is not None:
            self.screen.show_playing(self.engine.playing)

    def set_loop(self, on):
        self.engine.set_loop(on)
        if self.engine.playing:
            self._play_t = ticks_ms()
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

    def _tick(self):
        self.engine.service()
        if self._watching:
            self._watch()
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
                at = ticks_diff(ticks_ms(), self._play_t) / 1000
                if self.engine.loop and inp.seconds:
                    at = at % inp.seconds
                s.show_position("%s / %s" % (_clock(at), _clock(inp.seconds)))
            elif inp is not None and inp.kind == "clip":
                s.show_position("-- / %s" % _clock(inp.seconds))

    def _watch(self):
        """Measure the effect against the clock. On opening, a plug-in that
        can't keep up gives way to the next; after that the choice is the
        player's, and the screen says what it costs."""
        now = ticks_ms()
        if self._watch_t is None:
            self._watch_t = now
            self._watch_frames = audiopump.now()
            return
        ms = ticks_diff(now, self._watch_t)
        if ms < WATCH_MS:
            return
        speed = (audiopump.now() - self._watch_frames) * 1000 / (ms * SAMPLE_RATE)
        self._watch_t = None
        if speed >= KEEPS_UP:
            self._opening = False
            return
        if self._opening:
            at = self.effects.index(self.effect_name)
            if at + 1 < len(self.effects):
                print("%s runs at %d%% here, trying the next" % (self.effect_name, speed * 100))
                self.pick_effect(at + 1)
                return
            self._opening = False
        self.status("%s runs at %d%% of real time here: pick another"
                    % (self.effect_name, speed * 100))

    def _latency(self):
        """Sample the latency four times a second and show the last second's
        mean, so the figure moves with the path but doesn't flicker."""
        now = ticks_ms()
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

    # -- start and stop --------------------------------------------------------

    def close(self):
        global current
        current = None
        self.engine.close()

    def begin(self):
        self.screen = ui.Screen(self, self.scope)
        self.screen.out_label.set_text(self.output.describe())
        self.pick_effect(0)
        self.screen.show_effect_list(self.effects, 0, self.show_all)
        if self.clips:
            self.screen.clip_dd.set_selected(0)
            self.pick_clip(0)
        else:
            self.status("No WAV files in %s" % self.folder)
        self.set_loop(True)
        self.set_master(self.engine.master)
        if self.can_go_live and _env("STOMPBOX_LIVE"):
            self.screen.show_live_button(True)
            self.go_live()
        self.scope.every(10, lambda t: self.tick())


def _clock(seconds):
    s = int(seconds)
    return "%d:%02d" % (s // 60, s % 60)


def start(scope):
    global current
    if not appdata.desktop():
        _mount(scope)
    current = App(scope)
    scope.on_close(current.close)
    current.begin()
