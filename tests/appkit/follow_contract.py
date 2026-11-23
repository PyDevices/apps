# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Apps that follow their kinds: `AppScope.follow`, the apps that move with a choice, and Bit World's pick.

`AppScope.follow` calls an app back when the endpoints in use for a kind
change and stops when the app closes. Then each app that plays, casts or
connects is run against endpointkit with stand-in providers, and a choice
made while it runs has to reach it: the MP3 player, Synth Station and
midiEngine reopen their sound on the chosen device, Synth Station reads the
chosen MIDI inputs, Weather and Clock fetch again when the network moves,
Cast moves to the chosen Roku, and Bit World's script picks an output by name.

    APPKIT_DATA=/tmp/follow python tests/appkit/follow_contract.py
    micropython tests/appkit/follow_contract.py

``FOLLOW_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks
must then fail. The apps' screens need LVGL and icons (which draws with
ttfio): without them those checks are skipped, said in a line starting
SKIPPED, and the rest still run. Exits 1 if a check fails, 2 if endpointkit isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
# lib first: tests/appkit would hide the real appkit. The repository's root
# holds the apps package, and Bit World's folder its modules by name.
sys.path[:0] = [_join(_ROOT, "lib"), _ROOT, _join(_ROOT, "apps", "bit_world"), _HERE, _TESTS,
                _join(_OMNI, "packages", "endpointkit"),
                _join(_OMNI, "packages", "midiports"),
                _join(_OMNI, "packages", "icons"),
                _join(_OMNI, "packages", "iconkit", "lib"), _LIB]
if sys.implementation.name != "micropython":
    sys.path.append(_join(_OMNI, "utils"))  # hostnet, and ttfio over freetype-py; a board has ttfio built in

try:
    import endpointkit
except ImportError as e:
    print("can't run the follow checks:", e)
    sys.exit(2)

try:
    import icons  # noqa: F401
    NO_ICONS = None
except ImportError as e:
    # appkit draws its buttons with icons, which needs ttfio. Nothing before
    # the apps' screens draws, so they run with icons stood in, and the
    # screens are skipped.
    NO_ICONS = str(e)

    class _Icons:
        lvgl = None

    sys.modules["icons"] = _Icons
    print("SKIPPED: the apps' screens, since icons won't load here:", e)

from appkit import connections  # noqa: E402

from endpointkit.fake import FakeProvider  # noqa: E402

import boarddev  # noqa: E402
from appdev import App  # noqa: E402
from appkit import scope as S  # noqa: E402
from appkit.scope import AppScope  # noqa: E402

PLANT = os.getenv("FOLLOW_PLANT")
#: Each breaks one thing, and must make a check fail.
PLANTS = (
    "forgets_to_unfollow",  # close() leaves the subscription behind
    "every_event",  # follow calls back on news that changes nothing in use
    "synth_deaf",  # Synth Station's output ignores a new audio.out
    "midi_deaf",  # Synth Station keeps reading its own MIDI ports
    "weather_deaf",  # Weather and Clock don't fetch when the network moves
    "pick_ignored",  # Bit World lists the outputs but picks none
    "mp3_deaf",  # the MP3 player ignores a new audio.out
    "midiengine_deaf",  # midiEngine ignores a new audio.out
    "cast_deaf",  # Cast ignores the chosen receiver
    "cast_finds_nothing",  # Cast leaves the Rokus unlisted on a board
    "cast_keeps_searching",  # Cast's close leaves the Roku search running on a board
    "cast_finds_once",  # Cast's second open leaves the Rokus unlisted
    "cast_drops_desktop",  # Cast's close takes a computer's Rokus off the picker
)

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


def ids(endpoints):
    return [ep.id for ep in endpoints]


def deaf(scope):
    """Make *scope*'s app hear nothing: its follow subscribes to nothing."""
    scope.follow = lambda kind, callback, registry=None: []


if PLANT == "forgets_to_unfollow":
    _follow = AppScope.follow

    def _forgetful(self, kind, callback, registry=None):
        now = _follow(self, kind, callback, registry)
        self._follows = []
        return now

    AppScope.follow = _forgetful
elif PLANT == "every_event":
    S._in_use = lambda endpoints: object()


# -- the stand-ins ---------------------------------------------------------------


class Devices(endpointkit.Provider):
    """A computer's sound devices as audiodev lists them: the device's name in caps."""

    def __init__(self, kind, name, found):
        endpointkit.Provider.__init__(self, kind, name)
        self.found = found

    def scan(self):
        return [self.endpoint(local, label, caps=caps) for local, label, caps in self.found]


class Player:
    """What a board config's ``audio_out`` returns, recording where it plays."""

    def __init__(self, fmt, kwargs):
        self.format = fmt
        self.device = kwargs.get("device")
        self.sample = None
        self.closed = False
        self.pumped = False
        self.paused = False

    def attach(self, scope):
        pass

    def detach(self):
        pass

    def set_volume(self, percent):
        pass

    def play(self, sample, loop=False):
        self.sample = sample

    def stop(self):
        self.sample = None

    def close(self):
        self.closed = True

    def service(self):
        pass


class Peripherals:
    """A ``board_peripherals`` with an ``audio_out`` role and no I2S of its own."""

    PERIPHERALS = ("audio_out",)

    def __init__(self):
        self.opened = []

    def audio_out(self, fmt=None, **kwargs):
        player = Player(fmt, kwargs)
        self.opened.append(player)
        return player


class Instrument:
    output = "the instrument's output"


bp = Peripherals()
sys.modules["board_peripherals"] = bp
# No pump and no I2S driver: every player here is the board config's audio_out.
sys.modules["audiopump"] = None
sys.modules["_audioif"] = None

TEST_DIR = os.getenv("APPKIT_TEST_DIR") or "."


def _mkdir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass
    return path


def _touch(path):
    with open(path, "wb") as f:
        f.write(b"\x00" * 16)
    return path


# -- AppScope.follow, on a registry of its own ----------------------------------

reg = endpointkit.Registry()
speakers = FakeProvider("audio.out", "fake", [("a", "A"), ("b", "B")])
reg.register(speakers)
app = App()
scope = AppScope(app, "follower")
heard = []
now = scope.follow("audio.out", lambda eps: heard.append(ids(eps)), registry=reg)
check(now == [], "nothing is in use before a choice: %r" % (now,))
reg.select("audio.out", "fake:a")
check(heard == [["fake:a"]], "a choice reaches the app: %r" % (heard,))
reg.select("audio.out", "fake:a")
check(len(heard) == 1, "the same choice again isn't news: %r" % (heard,))
speakers.add("c", "C")
reg.poll()
check(len(heard) == 1, "an endpoint nobody chose isn't news: %r" % (heard,))
speakers.set_state("a", endpointkit.CONNECTED)
reg.poll()
check(len(heard) == 2 and heard[-1] == ["fake:a"], "a change of state in what's in use is news: %r" % (heard,))
reg.pin("audio.out", "fake:b", "other app")
check(heard[-1] == ["fake:b"], "another app's pin moves what's in use: %r" % (heard,))
reg.unpin("other app")
check(heard[-1] == ["fake:a"], "lifting the pin moves it back: %r" % (heard,))
told = len(heard)
problems = scope.close()
check(problems == [], "close released everything: %r" % (problems,))
reg.select("audio.out", "fake:c")
check(len(heard) == told, "a closed app hears nothing: %r" % (heard[told:],))
check(not reg._subs, "close unsubscribed from the registry: %d left" % len(reg._subs))
try:
    scope.follow("audio.out", lambda eps: None, registry=reg)
    check(False, "a closed scope refuses to follow")
except RuntimeError:
    pass

# Without endpointkit nothing is ever chosen.
saved = sys.modules.pop("endpointkit")
saved_path = sys.path[:]
if sys.implementation.name == "cpython":
    sys.modules["endpointkit"] = None  # an import of it then fails, wherever it's installed
else:
    sys.path[:] = [p for p in sys.path if not p.endswith("/endpointkit")]
bare = AppScope(app, "bare")
try:
    import endpointkit as _frozen  # noqa: F401
except ImportError:
    _frozen = None
if _frozen is None:
    check(bare.follow("audio.out", lambda eps: None) == [], "without endpointkit follow returns []")
else:
    print("SKIPPED: this interpreter has endpointkit frozen in, so the check without it can't run")
bare.close()
sys.path[:] = saved_path
sys.modules["endpointkit"] = saved

# connections.device: the name a computer opens, None for a board's endpoint.
check(connections.device([]) is None, "nothing chosen is the default device")

# -- the apps, against the device's own registry ---------------------------------

R = endpointkit.registry
outs = Devices("audio.out", "host-out", [
    ("default", "System default", {"device": None}),
    ("spk", "Speakers", {"device": "Speakers"}),
    ("usb", "USB Headset", {"device": "USB Headset"}),
])
R.register(outs)


def app_scope(name):
    s = AppScope(App(), name)
    if PLANT == name + "_deaf":
        deaf(s)
    return s


# Synth Station's output: a computer's player reopens on the chosen device and
# the instrument plays on.
if PLANT == "synth_deaf":
    from apps.synthstation import audio as _synth_audio

    _synth_audio.Output._moved = lambda self, endpoints: None
from apps.synthstation.audio import Output  # noqa: E402

synth_scope = AppScope(App(), "synthstation")
out = Output(synth_scope)
inst = Instrument()
out.start(inst)
first = bp.opened[-1]
check(first.device is None and first.sample is inst.output, "Synth Station plays to the default first")
R.select("audio.out", "host-out:usb")
moved_to = bp.opened[-1]
check(moved_to is not first and moved_to.device == "USB Headset", "Synth Station reopens on the chosen device: %r" % (moved_to.device,))
check(first.closed, "Synth Station closes the output it left")
check(moved_to.sample is inst.output, "the same instrument plays on there, not restarted")
synth_scope.close()
R.select("audio.out", "host-out:spk")
check(bp.opened[-1] is moved_to, "a closed Synth Station doesn't follow")
R.select("audio.out", None)

# Synth Station's MIDI: chosen inputs are read through midiports.endpoints,
# which opened them; with none chosen it opens its own again.
import midiports  # noqa: E402
from midiports import endpoints as midi_endpoints  # noqa: E402


class Port:
    def __init__(self, name):
        self.name = name
        self.waiting = bytearray()
        self.closed = False

    def any(self):
        return len(self.waiting)

    def readinto(self, buf, nbytes=None):
        n = min(len(self.waiting), len(buf))
        if not n:
            return None
        buf[:n] = self.waiting[:n]
        self.waiting = self.waiting[n:]
        return n

    def close(self):
        self.closed = True


class Info:
    def __init__(self, name):
        self.name = name
        self.direction = midiports.IN


class fakemidi:  # noqa: N801 - named as a backend module is: the provider's name comes from it
    """A computer's MIDI backend, where a port has one reader at a time."""

    __name__ = "fakemidi"
    held = []
    ports = {}

    @staticmethod
    def available():
        return [Info("Keys"), Info("Pads")]

    @staticmethod
    def open_port(info):
        if info.name in fakemidi.held:
            raise OSError("%s is open in another program" % info.name)
        port = fakemidi.ports[info.name] = Port(info.name)
        return port


midi_endpoints.register(R, backend=fakemidi)
from apps.synthstation import midi as synth_midi  # noqa: E402


class Notes:
    """A parser's sink, counting notes."""

    def __init__(self):
        self.on = []

    def note_on(self, note, velocity, channel):
        self.on.append(note)

    def note_off(self, note, channel):
        pass

    def control(self, controller, value, channel):
        pass

    def bend(self, value, channel):
        pass

    def program(self, number, channel):
        pass


if PLANT == "midi_deaf":
    synth_midi.Inputs._open_chosen = lambda self: False


class Held:
    """Synth Station's own inputs, holding Keys the way its open of every port does."""

    kind = "desktop"

    def close(self):
        fakemidi.held[:] = []


try:
    from apps.synthstation.station import Station
except ImportError as e:
    Station = None
    print("SKIPPED: Synth Station's MIDI move needs LVGL:", e)
if Station is not None:
    class Stub:
        shown = 0

        def _show_midi(self):
            self.shown += 1

    stub = Stub()
    stub.inputs = Held()
    fakemidi.held[:] = ["Keys"]
    midi_scope = AppScope(App(), "synthstation-midi")
    midi_scope.follow("midi.in", lambda eps: Station._midi_moved(stub, eps))
    R.select("midi.in", "fakemidi-midi-in:Keys")
    check("Keys" in fakemidi.ports, "the chosen input opens once the app lets go of it")
    inputs = stub.inputs
    check(inputs is not None and inputs.names() == ["Keys"], "Synth Station reads the chosen input: %r" % (inputs and inputs.names(),))
    if "Keys" in fakemidi.ports and inputs is not None:
        fakemidi.ports["Keys"].waiting = bytearray(b"\x90\x3c\x40")
        sink = Notes()
        inputs.poll(synth_midi.Parser(sink))
        check(sink.on == [60], "a note on the chosen input plays: %r" % (sink.on,))
    midi_scope.close()
    R.select("midi.in", None)

# Weather and Clock: when another network connects, the forecast and the clock
# are asked for again at once.
from deskkit import forecast, localtime  # noqa: E402

nets = FakeProvider("net", "wifi", [("Home", "Home", endpointkit.CONNECTED), ("Cafe", "Cafe", endpointkit.CONNECTED)])
R.register(nets)
R.select("net", "wifi:Home")


class Worker:
    def __init__(self):
        self.jobs = []

    def submit(self, work, done=None, key=None, release=None):
        self.jobs.append(work)


forecast.ip_place = {"name": "Here", "lat": 1.0, "lon": 2.0, "units": "C", "from_ip": True}
forecast._got_at = forecast._tried_at = forecast.time.time()  # fresh: nothing to fetch
localtime._synced_at = 1
weather_scope = app_scope("weather")
weather_scope.worker = Worker()
forecast.keep_fresh(weather_scope)
check(weather_scope.worker.jobs == [], "a fresh forecast isn't fetched")
R.select("net", "wifi:Cafe")
check(forecast.fetch in weather_scope.worker.jobs, "a new network fetches the forecast at once")
check(localtime._synced_at is None, "and sets the clock again over it")
weather_scope.close()

# Bit World's script: it lists the outputs and picks one by a word of its name.
from bit_output import pick_audio_out  # noqa: E402

if PLANT == "pick_ignored":
    boarddev.env_set("BIT_WORLD_AUDIO", "")
else:
    boarddev.env_set("BIT_WORLD_AUDIO", "headset")
R.select("audio.out", None)
device = pick_audio_out()
check(R.selection("audio.out") == ["host-out:usb"], "Bit World's pick reaches the registry: %r" % (R.selection("audio.out"),))
check(device == "USB Headset", "and its music opens there: %r" % (device,))
R.select("audio.out", None)

# -- the apps on a screen ----------------------------------------------------------

lv = None
if NO_ICONS is None:
    try:
        import lvgl as lv
        import _headless
    except ImportError as e:
        print("SKIPPED: the MP3 player, midiEngine and Cast need LVGL here:", e)

if lv is not None:
    W, H = 800, 480
    _headless.display(W, H)

    def screen_scope(name):
        s = app_scope(name)
        s.root = lv.obj(lv.screen_active())
        s.root.set_size(W, H)
        s.size = (W, H)
        s.rect = (0, 0, W, H)
        # Timers run when the check says: one-shots at once, the rest never.
        s.after = lambda ms, callback=None, name=None: callback(None)
        s.every = lambda ms=None, callback=None, period=None, name=None: None
        return s

    # The MP3 player: a playing song moves to the chosen device.
    class Decoder:
        sample_rate = 44100
        channel_count = 2

        def __init__(self, f):
            self.file = f

    class MP3:
        MP3Decoder = Decoder

    sys.modules["audiomp3"] = MP3
    music = _mkdir(_join(TEST_DIR, "music"))
    _touch(_join(music, "song.mp3"))
    boarddev.env_set("MP3_DIR", music)
    from apps import mp3  # noqa: E402

    mp3_scope = screen_scope("mp3")
    mp3.main(mp3_scope)
    first = mp3.state["out"]
    check(first is not None and first.device is None and first.sample is not None, "the MP3 player plays to the default first")
    R.select("audio.out", "host-out:spk")
    now_out = mp3.state["out"]
    check(now_out is not first and now_out is not None and now_out.device == "Speakers",
          "the MP3 player reopens on the chosen device: %r" % (now_out and now_out.device,))
    check(first.closed, "the MP3 player closes the output it left")
    check(now_out is not None and now_out.sample is not None and mp3.state["playing"], "the song plays on there")
    mp3_scope.close()
    R.select("audio.out", None)

    # midiEngine: the sound module plays on through the chosen device.
    class Part:
        inst = None
        program = 0
        bank_msb = bank_lsb = 0
        volume = 100
        pan = 64
        bend = 8192
        drums = False
        notes = 0
        last = None

    class Module:
        reverb_level = chorus_level = master_level = 100

        def __init__(self, rate, channels, bank=None):
            self.output = "the module's output"
            self.parts = [Part() for _ in range(16)]

        def name(self, channel):
            return "Piano"

        def prepare(self):
            pass

        def set_master(self, v):
            pass

        def close(self):
            pass

    class Deferred:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class Engine:
        DEFAULT_MASTER = 100
        DEFAULT_VOLUME = 100
        DEFAULT_PAN = 64
        DEFAULT_REVERB = 40
        DEFAULT_CHORUS = 0
        BEND_CENTER = 8192
        Module = Module

        @staticmethod
        def deferred(module):
            return Deferred()

    class SoundModule:
        engine = Engine

    class Sampler:
        pass

    sys.modules["soundmodule"] = SoundModule
    sys.modules["audioinstruments"] = Sampler
    sys.modules["audioinstruments.soundfont"] = Sampler
    Sampler.soundfont = Sampler
    boarddev.env_set("SOUNDFONT", _touch(_join(TEST_DIR, "bank.sf2")))
    boarddev.env_set("MIDI_DIR", _mkdir(_join(TEST_DIR, "midi")))
    try:
        from apps import midiengine
    except ImportError as e:
        midiengine = None
        print("SKIPPED: midiEngine:", e)
    if midiengine is not None:
        me_scope = screen_scope("midiengine")
        midiengine.main(me_scope)
        first = midiengine.state["out"]
        check(first is not None and first.device is None, "midiEngine plays to the default first: %r" % (midiengine.state["error"],))
        R.select("audio.out", "host-out:usb")
        now_out = midiengine.state["out"]
        check(now_out is not first and now_out is not None and now_out.device == "USB Headset",
              "midiEngine reopens on the chosen device: %r" % (now_out and now_out.device,))
        check(now_out is not None and now_out.sample == "the module's output", "the same sound module plays on there")
        me_scope.close()
        R.select("audio.out", None)

    # Cast: the Roku chosen for cast.target is picked, and a running cast moves to it.
    sys.modules["castif"] = Sampler
    rokus = Devices("cast.target", "tv", [("YN1", "Roku: Den", {"host": "10.0.0.7", "type": "roku"})])
    R.register(rokus)
    from apps import cast  # noqa: E402
    from touchkit import net as touch_net  # noqa: E402

    class FoundRokus:
        """castdisplay's endpoints: one Roku finder, registered on first use."""

        cached = []

        @staticmethod
        def register(registry=None):
            if not FoundRokus.cached:
                FoundRokus.cached.append((registry or R).register(Devices("cast.target", "rokus", [])))
            return FoundRokus.cached[0]

    class Castdisplay:
        endpoints = FoundRokus

    real_castdisplay = sys.modules.get("castdisplay")
    sys.modules["castdisplay"] = Castdisplay

    def finds_rokus():
        return [p for p in R.providers("cast.target") if p.name == "rokus"]

    def keeps_searching(scope):
        FoundRokus.register()

    def finds_once(scope):
        there = R.providers("cast.target")
        rokus = FoundRokus.register()
        if rokus not in there:
            scope.on_close(lambda: R.unregister(rokus))

    def drops_desktop(scope):
        rokus = FoundRokus.register()
        if rokus not in R.providers("cast.target"):
            R.register(rokus)
        scope.on_close(lambda: R.unregister(rokus))

    cast._find_rokus = {
        "cast_finds_nothing": lambda scope: None,
        "cast_keeps_searching": keeps_searching,
        "cast_finds_once": finds_once,
        "cast_drops_desktop": drops_desktop,
    }.get(PLANT, cast._find_rokus)
    touch_net.up = lambda: False  # no looking round the network here
    cast._encoder_room = lambda: (0, 1)  # a cast that starts stops at once, saying why
    cast_scope = screen_scope("cast")
    cast.main(cast_scope)
    st = cast.state
    # A board's connections leave the Rokus to Cast, so opening it lists them.
    check(finds_rokus(), "opening Cast registers castdisplay")

    class Sink:
        closed = False

        def close(self):
            Sink.closed = True

    st["sink"] = Sink()
    R.select("cast.target", "tv:YN1")
    shown = st.get("shown") or []
    check(any(r["host"] == "10.0.0.7" for r in shown), "Cast lists the chosen Roku: %r" % (shown,))
    check(cast_scope.store().get("host") == "10.0.0.7", "Cast picks the chosen Roku: %r" % (cast_scope.store(),))
    check(Sink.closed, "a running cast stops to move to it")
    cast_scope.close()
    check(not finds_rokus(), "closing Cast on a board stops the Roku search")
    cast_scope = screen_scope("cast")
    cast.main(cast_scope)
    check(finds_rokus(), "opening Cast again finds the Rokus again")
    cast_scope.close()
    # A computer's connections registered the Rokus, and they outlive Cast.
    rokus = FoundRokus.register()
    if rokus not in R.providers("cast.target"):
        R.register(rokus)
    cast_scope = screen_scope("cast")
    cast.main(cast_scope)
    cast_scope.close()
    check(finds_rokus(), "closing Cast on a computer leaves the Rokus listed")
    for rokus in finds_rokus():
        R.unregister(rokus)
    if real_castdisplay is None:
        del sys.modules["castdisplay"]
    else:
        sys.modules["castdisplay"] = real_castdisplay

if PLANT and PLANT not in PLANTS:
    print("unknown plant:", PLANT)
    sys.exit(2)
print("follow: %d checks, %d failed, on %s%s" % (checks[0], len(failures), sys.implementation.name,
                                                  " with " + PLANT if PLANT else ""))
sys.exit(1 if failures else 0)
