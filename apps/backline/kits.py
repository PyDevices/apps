# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's drum sounds: one interface over three kinds of kit.

- A drum machine from audioinstruments (`DrumMachineKit`): ``rhythm606``,
  ``rhythm78``, ``rhythm808``, ``rhythm909`` and ``electronic_drums5``.
- The drum kit of a SoundFont bank (`SoundFontKit`), through
  audioinstruments' ``soundfont_drums``. The bank is ``$SOUNDFONT``, else the
  first ``.sf2`` in ``~/soundfonts`` on a computer, or in the ``soundfonts``
  folder on the card, flash or data root of a board.
- A folder of WAV files and a ``kit.json`` (`SampleKit`), played by
  audiodsp's ``audiosampler.Sampler``::

      {"name": "Garage", "pads": {"36": "kick.wav", "38": {"file": "snare.wav", "level": 0.9}},
       "choke": [[42, 44, 46]]}

  A pad in a choke group stops the others in it, as a closed hi-hat stops
  the open one. Kit folders are in ``$BACKLINE_KITS``, else
  ``~/backline-kits`` on a computer, or the ``backline-kits`` folder on a
  board's card, flash or data root.

Every kit has ``name``, ``output`` (what the output plays),
``note_on(pitch, velocity, delay=0)`` with the delay in frames, ``fill()``,
``timed`` (True when it honours the delay) and ``close()``. `Bus` is the
output the app plays, so a kit can be swapped while the song runs.

A sample kit's pads can also come from somewhere other than a file:
`SampleKit.set_pad` takes the samples, and `SampleKit.save_pad` writes them
to the folder as a WAV and keeps them in ``kit.json``. A recorder hands its
take to those two.
"""

import json
import os
import struct
import sys

RATE = 48000
CHANNELS = 2
BLOCK = 256
MACHINES = ("rhythm808", "rhythm909", "rhythm606", "rhythm78", "electronic_drums5")
NAMES = {"rhythm808": "Rhythm 808", "rhythm909": "Rhythm 909", "rhythm606": "Rhythm 606",
         "rhythm78": "Rhythm 78", "electronic_drums5": "Electronic Drums 5"}
SOUNDFONT = "soundfont"
SAMPLES = "samples:"
VOICES = 16
DESKTOP = sys.implementation.name == "cpython" or sys.platform in (
    "linux", "darwin", "win32", "cygwin", "freebsd", "openbsd", "netbsd")


def getenv(name):
    fn = getattr(os, "getenv", None)
    return fn(name) if fn is not None else None


def home():
    return (getenv("USERPROFILE") or getenv("HOME") or "").replace("\\", "/")


def _folders(desktop_name, board_name):
    if DESKTOP:
        return [home() + "/" + desktop_name]
    from appkit import places

    return places.folders(board_name)


def _listdir(folder):
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def find_bank():
    """The SoundFont the SoundFont kit plays, or None when there is none."""
    env = getenv("SOUNDFONT")
    if env:
        return env
    for folder in _folders("soundfonts", "soundfonts"):
        for name in _listdir(folder):
            if name.lower().endswith(".sf2"):
                return folder + "/" + name
    return None


def kit_folders():
    """The sample kits on this device: folders holding a ``kit.json``."""
    env = getenv("BACKLINE_KITS")
    roots = [env] if env else _folders("backline-kits", "backline-kits")
    found = []
    for root in roots:
        for name in _listdir(root):
            path = root + "/" + name
            try:
                os.stat(path + "/kit.json")
            except OSError:
                continue
            found.append(path)
    return found


#: General MIDI's drum notes, for a kit that doesn't name its own.
GM_DRUMS = (
    (35, "Kick 2"), (36, "Kick"), (37, "Side Stick"), (38, "Snare"), (39, "Clap"), (40, "Snare 2"),
    (41, "Low Floor Tom"), (42, "Closed Hat"), (43, "Floor Tom"), (44, "Pedal Hat"), (45, "Low Tom"),
    (46, "Open Hat"), (47, "Low Mid Tom"), (48, "High Mid Tom"), (49, "Crash"), (50, "High Tom"),
    (51, "Ride"), (52, "China"), (53, "Ride Bell"), (54, "Tambourine"), (55, "Splash"), (56, "Cowbell"),
    (57, "Crash 2"), (59, "Ride 2"), (60, "High Bongo"), (61, "Low Bongo"), (62, "Mute Conga"),
    (63, "Open Conga"), (64, "Low Conga"), (69, "Cabasa"), (70, "Maracas"), (75, "Claves"),
)
SOURCES = (("machine", "Drum machines"), ("soundfont", "SoundFont"), ("samples", "Sample kits"))


def source(spec):
    """Which of the three kinds kit ``spec`` is: ``"machine"``, ``"soundfont"`` or ``"samples"``."""
    if spec.startswith(SAMPLES):
        return "samples"
    if spec == SOUNDFONT or spec.startswith(SOUNDFONT + ":"):
        return "soundfont"
    return "machine"


def title(spec):
    """What a screen calls kit ``spec``."""
    if spec in NAMES:
        return NAMES[spec]
    path = spec.split(":", 1)[1] if ":" in spec else (find_bank() or "")
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if name.lower().endswith(".sf2"):
        name = name[:-4]
    return name or spec


def describe(specs):
    """``[{"spec", "name", "source"}]`` for each kit spec, as panels list them."""
    return [{"spec": s, "name": title(s), "source": source(s)} for s in specs]


def available():
    """Every kit this device can play, as the specs `open_kit` takes."""
    specs = list(MACHINES)
    if find_bank() is not None:
        specs.append(SOUNDFONT)
    specs.extend(SAMPLES + f for f in kit_folders())
    return specs


def open_kit(spec, rate=RATE):
    """A kit from its spec: a drum machine's name, ``"soundfont"`` (or
    ``"soundfont:/path/bank.sf2"``) or ``"samples:/path/folder"``."""
    if spec in MACHINES:
        return DrumMachineKit(spec, rate)
    if spec == SOUNDFONT or spec.startswith(SOUNDFONT + ":"):
        bank = spec[len(SOUNDFONT) + 1:] or find_bank()
        if not bank:
            raise OSError("no SoundFont: put a .sf2 in %s, or set SOUNDFONT" % (
                "~/soundfonts" if DESKTOP else "a soundfonts folder"))
        return SoundFontKit(bank, rate)
    if spec.startswith(SAMPLES):
        return SampleKit(spec[len(SAMPLES):], rate)
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

    def __init__(self, bank, rate=RATE):
        import audioinstruments

        self.spec = SOUNDFONT + ":" + bank
        self.bank = bank
        name = bank.replace("\\", "/").rsplit("/", 1)[-1]
        self.name = name[:-4] if name.lower().endswith(".sf2") else name
        self.inst = audioinstruments.create("soundfont_drums", rate, CHANNELS, bank=bank)
        self.output = self.inst.output
        self._fill = getattr(self.inst, "fill", None)

    def voices(self):
        return [list(v) for v in GM_DRUMS]


def read_wav(path):
    """A WAV file's samples as mono signed 16-bit bytes, and its rate.
    Stereo is mixed to mono; only 16-bit PCM is read."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("%s isn't a WAV file" % path)
    pos = 12
    fmt = None
    pcm = None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            pcm = body
        pos += 8 + size + (size & 1)
    if fmt is None or pcm is None:
        raise ValueError("%s has no audio" % path)
    kind, channels, rate, _bps, _align, bits = fmt
    if kind != 1 or bits != 16:
        raise ValueError("%s: only 16-bit PCM WAV files play" % path)
    if channels == 1:
        return bytes(pcm), rate
    frames = len(pcm) // (2 * channels)
    out = bytearray(frames * 2)
    for i in range(frames):
        total = 0
        for c in range(channels):
            j = (i * channels + c) * 2
            v = pcm[j] | (pcm[j + 1] << 8)
            total += v - 65536 if v > 32767 else v
        v = total // channels
        out[2 * i] = v & 255
        out[2 * i + 1] = (v >> 8) & 255
    return bytes(out), rate


def write_wav(path, samples, rate):
    """Mono signed 16-bit ``samples`` (bytes) to a WAV file."""
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(samples)))
        f.write(samples)


class SampleKit:
    """A folder of WAV files, one per pad, on an ``audiosampler.Sampler``."""

    timed = True

    def __init__(self, folder, rate=RATE, voices=VOICES):
        import audiosampler

        self._audiosampler = audiosampler
        self.folder = folder.rstrip("/")
        self.spec = SAMPLES + self.folder
        self.rate = rate
        with open(self.folder + "/kit.json") as f:
            self.info = json.load(f)
        self.name = self.info.get("name") or self.folder.rsplit("/", 1)[-1]
        self.sampler = audiosampler.Sampler(voice_count=voices, channel_count=CHANNELS, sample_rate=rate)
        self.output = self.sampler
        self.pads = {}            # pitch -> (buffer, rate, level)
        self.playing = {}         # pitch -> voice index
        self.chokes = {}          # pitch -> the pitches it stops
        self._next = 0
        for group in self.info.get("choke", []):
            for p in group:
                self.chokes[int(p)] = [int(q) for q in group if q != p]
        for key, pad in self.info.get("pads", {}).items():
            if isinstance(pad, str):
                pad = {"file": pad}
            samples, srate = read_wav(self.folder + "/" + pad["file"])
            self.set_pad(int(key), samples, srate, pad.get("level", 1.0))

    def set_pad(self, pitch, samples, rate, level=1.0):
        """Play ``samples`` (mono signed 16-bit bytes at ``rate``) on ``pitch``."""
        buf = self._audiosampler.SampleBuffer(len(samples))
        memoryview(buf)[:] = samples
        self.pads[pitch] = (buf, rate, level)

    def save_pad(self, pitch, filename=None):
        """Write pad ``pitch`` to the kit's folder as a WAV and name it in ``kit.json``."""
        buf, rate, level = self.pads[pitch]
        filename = filename or "pad%d.wav" % pitch
        write_wav(self.folder + "/" + filename, bytes(buf), rate)
        self.info.setdefault("pads", {})[str(pitch)] = {"file": filename, "level": level}
        with open(self.folder + "/kit.json", "w") as f:
            json.dump(self.info, f)

    def voices(self):
        names = dict(GM_DRUMS)
        return [[p, names.get(p, "Pad %d" % p)] for p in sorted(self.pads)]

    def note_on(self, pitch, velocity, delay=0):
        pad = self.pads.get(pitch)
        if pad is None:
            return
        for other in self.chokes.get(pitch, ()):
            v = self.playing.pop(other, None)
            if v is not None:
                self.sampler.voice[v].stop()
        v = self._next
        self._next = (v + 1) % len(self.sampler.voice)
        buf, rate, level = pad
        self.sampler.voice[v].play(buf, rate=rate, level=level * velocity / 127.0, delay=delay / self.rate)
        self.playing[pitch] = v

    def fill(self):
        pass

    def close(self):
        if self.sampler is not None:
            self.sampler.stop()
            self.sampler.deinit()
            self.sampler = None
        for buf, _rate, _level in self.pads.values():
            buf.deinit()
        self.pads = {}


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
