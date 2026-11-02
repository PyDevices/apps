# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The midiEngine's MIDI file player: a library of .mid files, played
into whatever takes raw MIDI bytes (``gm.Module.feed``).

The library is a folder. With a ``catalog.json`` at its root (``{"version":
1, "files": [{"path": "Classical/Pachelbel - Canon in D.mid", "title":
"Canon in D", "composer": "Johann Pachelbel", "genre": "Classical",
"seconds": 245, ...}, ...]}``) each piece has a title, a composer, a genre
and a length, in the catalog's order. Without one the folder is scanned,
subfolders and all, in path order: the title is the file's name, the genre
the subfolder it sits in. ``entries`` are the pieces, ``files`` their paths
relative to the folder, ``genres()`` the genres with their counts.

``Player`` parses a file with ``umidiparser``, streaming each track
through a small buffer, and releases every channel message and SysEx at
its time: ``service()`` is called from a timer every few milliseconds,
compares the clock with the next event's due time (the sum of the
parser's ``delta_us``, which already follows the file's tempo changes)
and feeds what is due, for at most ``budget_ms`` a call, the rest on the
next. No sleeping, so the UI thread stays free, and
due times are measured from the start of the file, so nothing drifts.
``play()`` feeds nothing itself: it is called from a tap, and the first
events make the parts, so they go on the next ``service()``.

``stop()`` sends All Notes Off on all sixteen channels through the same
path. At the end of a file the player repeats it when ``loop`` is set,
else goes on to the next, wrapping at the last. ``next()`` and ``prev()``
wrap too, and all three stay within the current piece's genre when
``scope`` is ``GENRE`` rather than ``ALL``. With no folder, or no .mid
file in it, ``message`` says where to put them.

No LVGL here, and the clock is injectable, so a test can run it on
CPython or MicroPython with a fake sink and a fake clock.
"""


def _umidiparser_without_native():
    """umidiparser compiled without its ``@micropython.native`` lines, for a
    MicroPython built with no native emitter (the Windows port's pydevices
    variant raises SyntaxError at the first decorator). The same code, run
    as bytecode; a board never comes here."""
    import sys

    here = __file__.replace("\\", "/")
    path = here[: here.rfind("/") + 1] + "umidiparser.py"
    with open(path) as f:
        src = "".join(ln for ln in f if ln.strip() != "@micropython.native")
    names = {"__name__": "umidiparser"}
    exec(compile(src, path, "exec"), names)

    class Module:  # MicroPython can't make a module object: this holds the names
        pass

    mod = Module()
    for key in names:
        setattr(mod, key, names[key])
    sys.modules["umidiparser"] = mod
    return mod


try:
    from . import umidiparser
except SyntaxError:  # no native emitter in this interpreter
    umidiparser = _umidiparser_without_native()
except ImportError:  # a test with the app's folder on sys.path
    import umidiparser

try:
    from multimer import ticks_diff, ticks_ms
except ImportError:
    try:
        from time import ticks_diff, ticks_ms  # MicroPython without multimer
    except ImportError:
        import time

        def ticks_ms():
            return int(time.monotonic() * 1000)

        def ticks_diff(a, b):
            return a - b

import os

EXT = ".mid"
CATALOG = "catalog.json"
BUFFER = 256  # bytes read from the file per track at a time
BUDGET_MS = 20  # the most one service() call feeds for; what is left goes on the next
CC_ALL_NOTES_OFF = 123
ALL = "all"  # scope: next and prev walk the whole library
GENRE = "genre"  # scope: they stay in the current piece's genre
DIR_MODE = 0x4000  # S_IFDIR, in os.stat's mode on every interpreter


def _entry(path, title=None, composer="", genre=None, seconds=0):
    """One piece: what the face shows and what the player plays."""
    name = path.rsplit("/", 1)[-1]
    if name.lower().endswith(EXT):
        name = name[:-len(EXT)]
    if genre is None:
        genre = path.rsplit("/", 1)[0] if "/" in path else ""
    return {"path": path, "title": title or name, "composer": composer or "", "genre": genre or "",
            "seconds": int(seconds or 0)}


def _is_dir(path):
    try:
        return bool(os.stat(path)[0] & DIR_MODE)
    except OSError:
        return False


def _walk(folder, prefix=""):
    """The .mid files under ``folder``, as paths relative to it, in path order."""
    found = []
    for name in sorted(os.listdir(folder)):
        full = folder + "/" + name
        rel = prefix + name
        if _is_dir(full):
            found.extend(_walk(full, rel + "/"))
        elif name.lower().endswith(EXT):
            found.append(rel)
    return found


class Player:
    def __init__(self, folder, sink, now=ticks_ms, loop=False, buffer_size=BUFFER, scope=ALL,
                 budget_ms=BUDGET_MS):
        self.folder = folder
        self.budget_ms = budget_ms  # of real time, whatever clock ``now`` is
        self.sink = sink
        self.now = now
        self.loop = loop
        self.scope = scope
        self.buffer_size = buffer_size
        self.entries = []  # the pieces, each as _entry() makes it
        self.files = []  # their paths, relative to the folder, in the same order
        self.catalog = False  # True when catalog.json described the library
        self.message = None  # why there is nothing to play, else None
        self.index = 0
        self.playing = False
        self.length_ms = 0
        self._events = None
        self._pending = None  # (due_us, bytes), (due_us, None) at the end
        self._due_us = 0
        self._started = 0
        self.scan()

    # -- the folder -----------------------------------------------------------------

    def scan(self):
        """Read the library again (the catalog, else the folder); the
        current file keeps playing, and stays the current one if it is
        still there."""
        current = self.files[self.index % len(self.files)] if self.files else None
        try:
            entries = self._read_catalog()
        except OSError as e:  # a catalog that isn't JSON: say so, play nothing
            self.entries, self.files = [], []
            self.message = str(e)
            return
        self.catalog = entries is not None
        if entries is None:
            try:
                entries = [_entry(p) for p in _walk(self.folder)]
            except OSError:
                self.entries, self.files = [], []
                self.message = "No MIDI folder %s. Make it and put .mid files in it." % (self.folder,)
                return
        self.entries = entries
        self.files = [e["path"] for e in entries]
        self.message = None if self.files else "No .mid files in %s. Put some there." % (self.folder,)
        if current in self.files:
            self.index = self.files.index(current)
        elif self.files:
            self.index %= len(self.files)

    def _read_catalog(self):
        """The catalog's entries, or None when there is no catalog.json."""
        try:
            # bytes, decoded as UTF-8: a desktop's text mode would use its
            # locale's codepage (cp1252 on Windows) and fail on the titles
            with open(self.folder + "/" + CATALOG, "rb") as f:
                import json

                data = json.loads(f.read().decode("utf-8"))
        except OSError:
            return None
        except ValueError as e:
            raise OSError("%s/%s is not JSON: %s" % (self.folder, CATALOG, e))
        entries = []
        for item in data.get("files", ()):
            path = item.get("path")
            if path and path.lower().endswith(EXT):
                entries.append(_entry(path, item.get("title"), item.get("composer"), item.get("genre"),
                                      item.get("seconds")))
        return entries

    @property
    def entry(self):
        """The current piece, or an empty one."""
        if not self.entries:
            return _entry("")
        return self.entries[self.index % len(self.entries)]

    @property
    def name(self):
        """The current file's name without its extension, or ''."""
        if not self.files:
            return ""
        name = self.files[self.index % len(self.files)].rsplit("/", 1)[-1]
        return name[:-len(EXT)]

    @property
    def title(self):
        return self.entry["title"]

    @property
    def composer(self):
        return self.entry["composer"]

    @property
    def genre(self):
        return self.entry["genre"]

    def genres(self):
        """``[(genre, count), ...]`` in name order; a genre of "" (files at
        the library's root) comes last."""
        counts = {}
        for e in self.entries:
            counts[e["genre"]] = counts.get(e["genre"], 0) + 1
        return sorted(counts.items(), key=lambda kv: (kv[0] == "", kv[0]))

    def indices(self, genre=None):
        """The indices of the pieces in ``genre``, or of all of them."""
        if genre is None:
            return list(range(len(self.entries)))
        return [i for i, e in enumerate(self.entries) if e["genre"] == genre]

    def step(self, d):
        """The index ``d`` pieces on from the current one, wrapping, within
        the current genre when the scope is GENRE."""
        if not self.files:
            return 0
        if self.scope == GENRE:
            siblings = self.indices(self.genre)
            at = siblings.index(self.index % len(self.files))
            return siblings[(at + d) % len(siblings)]
        return (self.index + d) % len(self.files)

    def path(self, i=None):
        i = self.index if i is None else i
        return self.folder + "/" + self.files[i % len(self.files)]

    # -- transport ------------------------------------------------------------------

    def play(self, i=None):
        """Play file ``i`` (wrapping; default the current one) from its start."""
        if not self.files:
            return False
        if i is not None:
            self.index = i % len(self.files)
        if self.playing:
            self._silence()
        f = umidiparser.MidiFile(self.path(), buffer_size=self.buffer_size, reuse_event_object=True)
        # The catalog's length when it has one: working it out reads the whole
        # file a second time, on the thread that also feeds the audio, and a
        # dense piece takes long enough to empty the output's lookahead.
        seconds = self.entry["seconds"]
        self.length_ms = seconds * 1000 if seconds else f.length_us() // 1000
        self._events = iter(f)
        self._due_us = 0
        self._pending = None
        self._started = self.now()
        self.playing = True
        self._advance()
        # Nothing is fed here. The first program changes and notes make
        # parts and read samples, and play() is called from a tap: the
        # next service() releases what is due at time 0, on the timer.
        return True

    def stop(self):
        """Stop, and release every note on every channel."""
        if self.playing:
            self._silence()
        self.playing = False
        self._events = None
        self._pending = None

    def toggle(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def next(self):
        return self.play(self.step(1))

    def prev(self):
        return self.play(self.step(-1))

    @property
    def elapsed_ms(self):
        if not self.playing:
            return 0
        return min(ticks_diff(self.now(), self._started), self.length_ms)

    # -- the events -----------------------------------------------------------------

    def service(self):
        """Feed the events that are due; the number fed. Call it every few ms.

        A call feeds for at most ``budget_ms`` and leaves the rest, already
        due, to the next: a note that reads a sample from the card can take
        tens of milliseconds, and a backlog fed in one go would hold the
        timer, the screen and the REPL for seconds."""
        if not self.playing:
            return 0
        began = ticks_ms()
        elapsed = ticks_diff(self.now(), self._started)
        n = 0
        ended = False
        while self._pending is not None and self._pending[0] // 1000 <= elapsed:
            due, data = self._pending
            if data is None:  # the end of the file, at its time
                if ended:  # a second end in one call: a file with no length, looping
                    return n
                ended = True
                self._ended()
                if not self.playing:
                    return n
                elapsed = ticks_diff(self.now(), self._started)  # the next one's start is due now
                continue
            self.sink(data)
            n += 1
            self._advance()
            if ticks_diff(ticks_ms(), began) >= self.budget_ms:
                break
        return n

    def _advance(self):
        """The next event worth sending into ``_pending``: a channel message
        or a SysEx with its due time, or the end of track with its."""
        events = self._events
        while True:
            try:
                ev = next(events)
            except StopIteration:
                self._pending = (self._due_us, None)
                return
            self._due_us += ev.delta_us
            status = ev.status
            if ev.is_channel() or status == umidiparser.SYSEX:
                self._pending = (self._due_us, ev.to_midi())
                return
            if status == umidiparser.END_OF_TRACK:
                self._pending = (self._due_us, None)
                return
            # Meta events (the parser has already applied the tempo) and escapes.

    def _ended(self):
        if self._due_us == 0:  # a file with nothing in it: don't chase the next one
            self.stop()
        elif self.loop:
            self.play()
        else:
            self.play(self.step(1))

    def _silence(self):
        for ch in range(16):
            self.sink(bytes((0xB0 | ch, CC_ALL_NOTES_OFF, 0)))
