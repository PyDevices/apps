# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's drum sounds: one interface over two kinds of kit.

- The drum kit of a SoundFont bank (`SoundFontKit`), through
  audioinstruments' ``soundfont_drums``. The ``soundfont`` kit, the one
  Backline starts on, plays ``$SOUNDFONT`` when that is set, and otherwise
  Backline's own bank, `DEFAULT_BANK`: a small General MIDI drum kit made from
  the FreePats synthesizer percussion (CC0). Installing Backline on a board
  with omip puts the bank in the app's ``soundfonts`` folder; with pip, or in a
  frozen firmware, Backline fetches it on its first start (`fetch_default`).
  Every other ``.sf2`` in a ``soundfonts`` folder is a kit of its own:
  ``~/soundfonts`` on a computer, or the card's, flash's or the data root's
  on a board.
- A drum machine from audioinstruments (`DrumMachineKit`): ``rhythm606``,
  ``rhythm78``, ``rhythm808``, ``rhythm909`` and ``electronic_drums5``.

Every kit has ``name``, ``output`` (what the output plays),
``note_on(pitch, velocity, delay=0)`` with the delay in frames, ``fill()``,
``timed`` (True when it honours the delay) and ``close()``. `Bus` is the
output the app plays, so a kit can be swapped while the song runs.
"""

import os
import sys

try:
    import hashlib
except ImportError:  # pragma: no cover - every port Backline runs on has it
    hashlib = None

RATE = 48000
CHANNELS = 2
BLOCK = 256
MACHINES = ("rhythm808", "rhythm909", "rhythm606", "rhythm78", "electronic_drums5")
NAMES = {"rhythm808": "Rhythm 808", "rhythm909": "Rhythm 909", "rhythm606": "Rhythm 606",
         "rhythm78": "Rhythm 78", "electronic_drums5": "Electronic Drums 5"}
SOUNDFONT = "soundfont"
#: The kit Backline plays when nothing names one.
DEFAULT = SOUNDFONT
#: Backline's own bank, which the ``soundfont`` kit plays unless ``$SOUNDFONT``
#: names another. ``tools/backline/make_drums.py`` makes it; it is published
#: at `DEFAULT_URL` and checked against `DEFAULT_SHA256` when fetched.
DEFAULT_BANK = "backline-drums.sf2"
DEFAULT_TITLE = "Backline Drums"
DEFAULT_URL = "https://github.com/PyDevices/lib/releases/download/backline-drums-1/" + DEFAULT_BANK
DEFAULT_SHA256 = "6f719656ecfa2b5ae8946402bb64c532086d682bad75816d7c6d58741b1ae095"
DEFAULT_BYTES = 1657008
#: Backline's data folder, which the app sets from its scope; a computer keeps
#: the fetched bank there. Leaving the import of appkit to the app keeps this
#: module, and the box, free of LVGL.
data_folder = None
DESKTOP = sys.implementation.name == "cpython" or sys.platform in (
    "linux", "darwin", "win32", "cygwin", "freebsd", "openbsd", "netbsd")


def getenv(name):
    fn = getattr(os, "getenv", None)
    return fn(name) if fn is not None else None


def home():
    return (getenv("USERPROFILE") or getenv("HOME") or "").replace("\\", "/")


def _here():
    """This app's folder, where omip puts the bank, or None in a frozen firmware."""
    path = globals().get("__file__", "").replace("\\", "/")
    return path.rsplit("/", 1)[0] if "/" in path else None


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _listdir(folder):
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def bank_folders():
    """Where other SoundFonts are found: ``~/soundfonts`` on a computer, the
    ``soundfonts`` folder on the card, flash and data root of a board."""
    if DESKTOP:
        return [home() + "/soundfonts"]
    from appkit import places

    return places.folders("soundfonts")


def default_folders():
    """Where `DEFAULT_BANK` is looked for, in order: the app's own
    ``soundfonts`` folder (omip's install), then `data_folder` on a computer,
    or the board's ``soundfonts`` folders (`fetch_default`'s)."""
    here = _here()
    found = [here + "/soundfonts"] if here else []
    if DESKTOP:
        return found + ([data_folder] if data_folder else [])
    return found + bank_folders()


def default_bank():
    """Where Backline's own bank is, or None before it has been fetched."""
    for folder in default_folders():
        if _exists(folder + "/" + DEFAULT_BANK):
            return folder + "/" + DEFAULT_BANK
    return None


def where():
    """Where to put `DEFAULT_BANK` by hand, for a message."""
    folders = default_folders()
    return folders[-1] if folders else "a soundfonts folder"


def find_bank():
    """The bank the ``soundfont`` kit plays: ``$SOUNDFONT``, else `default_bank`."""
    return getenv("SOUNDFONT") or default_bank()


def other_banks():
    """Every other ``.sf2`` in `bank_folders`, each a kit of its own."""
    found = []
    for folder in bank_folders():
        for name in _listdir(folder):
            if name.lower().endswith(".sf2") and name != DEFAULT_BANK:
                found.append(folder + "/" + name)
    return found


def _fetch_folder():
    if DESKTOP:
        if not data_folder:
            raise OSError("Backline has no data folder to fetch its bank into")
        return data_folder
    from appkit import places

    return places.write_folder("soundfonts")


def _http_get(url, write):
    """Stream ``url`` into ``write``, following redirects; the HTTP status."""
    from appkit import net

    r = net.requests().get(url, timeout=30)
    try:
        if r.status_code == 200:
            if hasattr(r, "iter_content"):  # requests on a computer, adafruit_requests
                for chunk in r.iter_content(4096):
                    write(chunk)
            else:  # MicroPython's requests: the socket
                while True:
                    chunk = r.raw.read(1024)
                    if not chunk:
                        break
                    write(chunk)
        return r.status_code
    finally:
        r.close()


def _verify(got, sha256, url):
    if got != sha256:
        raise OSError("%s is not Backline's bank: its SHA-256 is %s" % (url, got))


def fetch_default(folder=None, url=None, sha256=None, get=None):
    """Download Backline's bank once, check it, and return where it is.

    It goes to ``folder``: by default `data_folder` on a computer, or
    the first ``soundfonts`` folder that takes a file on a board (the card's,
    when one is in). The file takes its name only once its SHA-256 matches, so
    a failed or tampered download leaves nothing behind.

    Args:
        folder (str): Where to put it.
        url (str): Where to fetch it from; `DEFAULT_URL` by default.
        sha256 (str): The hex digest it must have; `DEFAULT_SHA256` by default.
        get: ``get(url, write)`` streams the body into ``write`` and returns
            the HTTP status; by default urllib on CPython, requests on a board.

    Raises:
        OSError: no network, an HTTP error, or the wrong bytes.
    """
    folder = folder or _fetch_folder()
    url = url or DEFAULT_URL
    sha256 = sha256 or DEFAULT_SHA256
    path = folder + "/" + DEFAULT_BANK
    part = path + ".part"
    digest = hashlib.sha256()
    try:
        with open(part, "wb") as f:

            def write(chunk):
                digest.update(chunk)
                f.write(chunk)

            status = (get or _http_get)(url, write)
        if status != 200:
            raise OSError("HTTP %s from %s" % (status, url))
        _verify("".join("%02x" % b for b in digest.digest()), sha256, url)
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(part, path)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return path


#: General MIDI's drum notes, for a kit that doesn't name its own.
GM_DRUMS = (
    (35, "Kick 2"), (36, "Kick"), (37, "Side Stick"), (38, "Snare"), (39, "Clap"), (40, "Snare 2"),
    (41, "Low Floor Tom"), (42, "Closed Hat"), (43, "Floor Tom"), (44, "Pedal Hat"), (45, "Low Tom"),
    (46, "Open Hat"), (47, "Low Mid Tom"), (48, "High Mid Tom"), (49, "Crash"), (50, "High Tom"),
    (51, "Ride"), (52, "China"), (53, "Ride Bell"), (54, "Tambourine"), (55, "Splash"), (56, "Cowbell"),
    (57, "Crash 2"), (59, "Ride 2"), (60, "High Bongo"), (61, "Low Bongo"), (62, "Mute Conga"),
    (63, "Open Conga"), (64, "Low Conga"), (69, "Cabasa"), (70, "Maracas"), (75, "Claves"),
)
SOURCES = (("soundfont", "SoundFont"), ("machine", "Drum machines"))


def source(spec):
    """Which kind kit ``spec`` is: ``"soundfont"`` or ``"machine"``."""
    if spec == SOUNDFONT or spec.startswith(SOUNDFONT + ":"):
        return "soundfont"
    return "machine"


def title(spec):
    """What a screen calls kit ``spec``."""
    if spec in NAMES:
        return NAMES[spec]
    if spec == SOUNDFONT and not getenv("SOUNDFONT"):
        return DEFAULT_TITLE
    path = spec.split(":", 1)[1] if ":" in spec else (find_bank() or "")
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if name.lower().endswith(".sf2"):
        name = name[:-4]
    return name or spec


def describe(specs):
    """``[{"spec", "name", "source"}]`` for each kit spec, as panels list them."""
    return [{"spec": s, "name": title(s), "source": source(s)} for s in specs]


def available():
    """Every kit this device can play, as the specs `open_kit` takes: the
    ``soundfont`` kit first, then the drum machines, then the other banks."""
    return [SOUNDFONT] + list(MACHINES) + [SOUNDFONT + ":" + b for b in other_banks()]


def open_kit(spec, rate=RATE):
    """A kit from its spec: ``"soundfont"``, ``"soundfont:/path/bank.sf2"``
    or a drum machine's name."""
    if spec in MACHINES:
        return DrumMachineKit(spec, rate)
    if spec == SOUNDFONT:
        bank = find_bank()
        if not bank:
            raise OSError("%s isn't here yet: it is fetched from %s, or put it in %s" % (
                DEFAULT_BANK, DEFAULT_URL, where()))
        return SoundFontKit(bank, rate, spec)
    if spec.startswith(SOUNDFONT + ":"):
        return SoundFontKit(spec[len(SOUNDFONT) + 1:], rate, spec)
    raise ValueError("no kit %r" % (spec,))


class DrumMachineKit:
    """One of audioinstruments' drum machines."""

    timed = False

    def __init__(self, machine, rate=RATE):
        import audioinstruments

        self.spec = machine
        self.name = NAMES.get(machine, machine)
        self.inst = audioinstruments.create(machine, rate, CHANNELS)
        self.output = self.inst.output
        self._fill = getattr(self.inst, "fill", None)

    def voices(self):
        """``[(pitch, name)]``: the drum notes this kit plays."""
        import audioinstruments

        mod = getattr(audioinstruments, self.spec, None)
        if mod is None:
            try:
                mod = __import__("audioinstruments." + self.spec, None, None, ["NOTE_MAP"])
            except ImportError:
                mod = None
        table = getattr(mod, "NOTE_MAP", None)
        return [list(v) for v in table] if table else [list(v) for v in GM_DRUMS]

    def note_on(self, pitch, velocity, delay=0):
        self.inst.note_on(pitch, velocity)

    def fill(self):
        if self._fill is not None:
            self._fill()

    def close(self):
        if self.inst is not None:
            self.inst.deinit()
            self.inst = None


class SoundFontKit(DrumMachineKit):
    """The standard drum kit of a SoundFont bank."""

    def __init__(self, bank, rate=RATE, spec=None):
        import audioinstruments

        self.spec = spec or SOUNDFONT + ":" + bank
        self.bank = bank
        name = bank.replace("\\", "/").rsplit("/", 1)[-1]
        if name == DEFAULT_BANK:
            self.name = DEFAULT_TITLE
        else:
            self.name = name[:-4] if name.lower().endswith(".sf2") else name
        self.inst = audioinstruments.create("soundfont_drums", rate, CHANNELS, bank=bank)
        self.output = self.inst.output
        self._fill = getattr(self.inst, "fill", None)

    def voices(self):
        return [list(v) for v in GM_DRUMS]


class Bus:
    """What the output plays: one mixer voice, whatever kit is on it."""

    def __init__(self, rate=RATE, level=0.9):
        import audiomixer

        self.mixer = audiomixer.Mixer(voice_count=1, sample_rate=rate, channel_count=CHANNELS,
                                      bits_per_sample=16, samples_signed=True, buffer_size=BLOCK * 4)
        self.mixer.voice[0].level = level
        self.output = self.mixer
        self.kit = None

    def attach(self, kit):
        """Play ``kit`` from now on; the one before is closed."""
        old = self.kit
        self.kit = kit
        self.mixer.voice[0].play(kit.output, loop=True)
        if old is not None and old is not kit:
            old.close()

    def detach(self):
        """Play nothing, and close the kit that played."""
        old, self.kit = self.kit, None
        if old is not None:
            self.mixer.voice[0].stop()
            old.close()

    def fill(self):
        if self.kit is not None:
            self.kit.fill()

    def level(self, level):
        """The whole kit's level, 0 to 1."""
        self.mixer.voice[0].level = max(0.0, min(1.0, level))

    def close(self):
        self.mixer.voice[0].stop()
        if self.kit is not None:
            self.kit.close()
            self.kit = None
