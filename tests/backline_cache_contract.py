# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's picture cache (`backline.art.Cache`): a picture drawn once is
read back from its file the next time, pixel for pixel.

A picture read back holds exactly what drawing it gave, with and without
alpha. An SVG that changes at the same size is drawn again, never served
from the old one's file. A file that is short, long or whose pixels don't
match their CRC is said on the console, drawn again over a clean buffer,
and written again, so the next read is right. Where the flash would be
left with less than the cache's reserve, nothing is written, and that is
said once. The app keeps its cache on the SD card when one is in, takes a
file and has room, and otherwise in ``cache`` in its data folder, saying
why when a card is in but not used; it never makes ``/sd`` with no card.
A folder under ``--tmp`` stands in for the card.

    python tests/backline_cache_contract.py [--plant=NAME] [--tmp FOLDER]

Needs LVGL and svgio. ``--plant=NAME`` breaks the cache one way
(``PLANTS``) and a check must then fail.
"""

import os
import sys

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import _headless  # noqa: E402
from backline import art  # noqa: E402

PLANTS = ("stale-key", "trust-short", "no-crc", "quiet-rebuild", "no-clear", "fill-flash",
          "ignore-card", "skip-card-room", "make-sd", "quiet-fallback")
RESULTS = [0, 0]
SAID = []


def check(name, ok, detail=""):
    if ok:
        RESULTS[0] += 1
        print("ok   " + name)
    else:
        RESULTS[1] += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "stale-key":
        # Named for the size and format alone, so a new SVG finds the old file.
        def path(self, svg, width, height, alpha):
            return self.folder + "/%dx%d-%d.px" % (width, height, alpha)
        art.Cache.path = path
    elif name in ("trust-short", "no-crc", "quiet-rebuild"):
        def load(self, path, buf):
            try:
                f = open(path, "rb")
            except OSError:
                self.misses += 1
                return False
            with f:
                got = f.readinto(buf) or 0
                tail = f.read(5)
            if name == "trust-short" and got:
                self.hits += 1
                return True
            if name == "no-crc" and got == len(buf):
                self.hits += 1
                return True
            if got == len(buf) and len(tail) == 4 and art.crc32(buf) == int.from_bytes(tail, "little"):
                self.hits += 1
                return True
            self.rebuilt += 1
            art._clear(buf)
            return False          # quiet-rebuild: and says nothing
        art.Cache.load = load
    elif name == "no-clear":
        art._clear = lambda buf: None
    elif name == "fill-flash":
        art.Cache._room = lambda self, need: True
    elif name == "ignore-card":
        from backline import app
        app._card_cache = lambda scope: None
    elif name == "skip-card-room":
        from backline import app
        app.CARD_ROOM = -(1 << 62)
    elif name in ("make-sd", "quiet-fallback"):
        from appkit import places
        from backline import app
        card_cache = app._card_cache

        def wrapped(scope):
            # make-sd: takes the card as in without asking, so with none in
            # it makes /sd. quiet-fallback: says nothing when it isn't used.
            hold, log = places.hold_card, art.log
            if name == "make-sd":
                places.hold_card = lambda scope, write=False: True
            else:
                art.log = lambda message: None
            try:
                return card_cache(scope)
            finally:
                places.hold_card, art.log = hold, log
        app._card_cache = wrapped
    else:
        raise SystemExit("no such plant: %r" % name)


def empty_folder(path):
    try:
        os.mkdir(path)
    except OSError:
        pass
    for name in os.listdir(path):
        try:
            os.remove(path + "/" + name)
        except OSError:           # a folder: the app's cache
            empty_folder(path + "/" + name)
            os.rmdir(path + "/" + name)
    return path


def fresh(svg, w, h, alpha):
    """``svg`` drawn with no cache."""
    kept = art.cache
    art.cache = None
    try:
        return bytes(art.Picture(None, svg, w, h, alpha=alpha).data)
    finally:
        art.cache = kept


def heard(before, words):
    return any(words in line for line in SAID[before:])


def run(tmp):
    folder = empty_folder(tmp + "/backline-cache-contract")
    kept = art.use_cache(folder)
    lay = art.Layout(800, 480)
    glow = art.glow_svg(30, 0xFFB703)
    other = art.glow_svg(30, 0x4CC9F0)

    # Read back as drawn, with alpha and without.
    for alpha in (True, False):
        what = "with alpha" if alpha else "RGB565"
        first = art.Picture(None, glow, 60, 60, alpha=alpha)
        hits = kept.hits
        second = art.Picture(None, glow, 60, 60, alpha=alpha)
        check("a picture %s is read back the second time" % what, kept.hits == hits + 1)
        check("a picture %s read back holds what drawing it gave" % what,
              bytes(second.data) == bytes(first.data) == fresh(glow, 60, 60, alpha))

    # A different SVG at the same size is its own picture.
    pic = art.Picture(None, other, 60, 60)
    check("an SVG that changed at the same size is drawn as it is now, not read from the old one's file",
          bytes(pic.data) == fresh(other, 60, 60, True))
    old = art.Picture(None, art.panel_svg(lay, 4, 1), 800, 480, alpha=False)
    new = art.Picture(None, art.panel_svg(lay, 3, 1), 800, 480, alpha=False)
    check("the panel for a new meter is drawn for it, not read from the old meter's file",
          bytes(new.data) == fresh(art.panel_svg(lay, 3, 1), 800, 480, False) and bytes(new.data) != bytes(old.data))
    old = new = None

    # Files that are wrong: drawn again, said, and written again.
    for alpha in (True, False):
        what = "with alpha" if alpha else "RGB565"
        want = fresh(glow, 60, 60, alpha)
        path = kept.path(glow, 60, 60, alpha)
        for how in ("short", "long", "flipped"):
            with open(path, "rb") as f:
                good = f.read()
            if how == "short":
                bad = good[: len(good) // 3]
            elif how == "long":
                bad = good + b"\0" * 8
            else:
                bad = bytearray(good)
                bad[len(bad) // 2] ^= 0x5A
            with open(path, "wb") as f:
                f.write(bad)
            said = len(SAID)
            rebuilt = kept.rebuilt
            pic = art.Picture(None, glow, 60, 60, alpha=alpha)
            check("a %s file %s is drawn again, right" % (how, what), bytes(pic.data) == want)
            check("a %s file %s is said on the console" % (how, what),
                  kept.rebuilt == rebuilt + 1 and heard(said, "is wrong"), "%r" % (SAID[said:],))
            hits = kept.hits
            pic = art.Picture(None, glow, 60, 60, alpha=alpha)
            check("a %s file %s is written again and read back right next time" % (how, what),
                  kept.hits == hits + 1 and bytes(pic.data) == want)

    # A full flash: nothing written, said once, and the pictures still right.
    full = art.Cache(empty_folder(tmp + "/backline-cache-full"), reserve=1 << 62)
    art.cache = full
    said = len(SAID)
    a = art.Picture(None, glow, 60, 60)
    b = art.Picture(None, other, 60, 60)
    check("a cache with no room left writes nothing", os.listdir(full.folder) == [], "%r" % (os.listdir(full.folder),))
    check("a cache with no room left says so, once",
          len([line for line in SAID[said:] if "no room" in line]) == 1, "%r" % (SAID[said:],))
    check("a cache with no room left still draws the pictures right",
          bytes(a.data) == fresh(glow, 60, 60, True) and bytes(b.data) == fresh(other, 60, 60, True))

    # Out of room, files this start hasn't used go first.
    roomy = art.Cache(folder)
    art.cache = roomy
    art.Picture(None, glow, 60, 60)
    roomy.reserve = roomy._free() - 1
    art.Picture(None, art.glow_svg(30, 0xFF4D6D), 60, 60)
    names = os.listdir(folder)
    check("out of room, the files this start hasn't used are cleared out for new ones",
          len(names) == 2 and len(roomy.used) == 2, "%d files, %d used" % (len(names), len(roomy.used)))

    # The app's own cache, in its data folder.
    from backline import app

    data = empty_folder(tmp + "/backline-cache-data")
    app._art_cache(data)
    check("the app keeps its pictures in cache in its data folder",
          art.cache is not None and art.cache.folder.replace("\\", "/") == data + "/cache")
    art.use_cache(None)
    card(tmp, glow)


class Scope:
    """An app's scope, as far as the cache uses it."""

    def __init__(self):
        self.closers = []

    def on_close(self, fn):
        self.closers.append(fn)

    def close(self):
        for fn in self.closers:
            fn()


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def card(tmp, glow):
    """The SD card: a folder stands in for ``/sd``; it is "in" while it exists."""
    from appkit import places
    from backline import app

    base = empty_folder(tmp + "/backline-cache-card")
    sd = base + "/sd"
    data = empty_folder(base + "/data")
    kept_sd, kept_hold, kept_free = places.SD, places.hold_card, art.free
    places.SD = sd
    places.hold_card = lambda scope, write=False: exists(sd)
    room = [None]                 # the card's free bytes, or None for what it has
    art.free = lambda folder: room[0] if room[0] is not None and folder.startswith(sd) else kept_free(folder)
    try:
        # No card in: the data folder, and no /sd made.
        scope = Scope()
        app._art_cache(data, scope)
        check("with no card in, the app keeps its pictures in its data folder",
              art.cache is not None and art.cache.folder == data + "/cache", art.cache and art.cache.folder)
        check("with no card in, no /sd folder is made", not exists(sd))
        scope.close()
        check("closing the app lets its cache go", art.cache is None)

        # A card in with room: the pictures go on it, none on the flash.
        os.mkdir(sd)
        scope = Scope()
        app._art_cache(data, scope)
        folder = sd + "/" + app.CARD_CACHE
        check("with a card in, the app keeps its pictures on the card",
              art.cache is not None and art.cache.folder == folder, art.cache and art.cache.folder)
        empty_folder(data + "/cache")
        art.Picture(None, glow, 60, 60)
        check("a picture drawn with a card in is written to the card, not the flash",
              exists(folder) and len(os.listdir(folder)) == 1 and os.listdir(data + "/cache") == [],
              "card %r, flash %r" % (os.listdir(folder) if exists(folder) else None, os.listdir(data + "/cache")))

        # A cache on the card keeps its reserve on the card.
        art.cache.reserve = 1 << 20
        room[0] = (1 << 20) - 1
        said = len(SAID)
        art.Picture(None, art.glow_svg(30, 0x80FFDB), 60, 60)
        check("a cache on the card keeps its reserve on the card, and says so",
              len(os.listdir(folder)) == 1 and heard(said, "no room on " + folder), "%r" % (SAID[said:],))
        scope.close()

        # A card with too little room: the flash, said.
        room[0] = art.CACHE_RESERVE + (1 << 20)   # 1 MB past the reserve
        said = len(SAID)
        scope = Scope()
        app._art_cache(data, scope)
        check("a card with too little room isn't used: the pictures go in the data folder",
              art.cache is not None and art.cache.folder == data + "/cache", art.cache and art.cache.folder)
        check("a card with too little room is said on the console", heard(said, "KB free"), "%r" % (SAID[said:],))
        scope.close()
        room[0] = None

        # A card that won't take a file: the flash, said.
        empty_folder(folder)
        os.rmdir(folder)
        with open(folder, "wb") as f:   # a file where the folder would be
            f.write(b"x")
        said = len(SAID)
        scope = Scope()
        app._art_cache(data, scope)
        check("a card that won't take a file isn't used: the pictures go in the data folder",
              art.cache is not None and art.cache.folder == data + "/cache", art.cache and art.cache.folder)
        check("a card that won't take a file is said on the console", heard(said, "won't keep"), "%r" % (SAID[said:],))
        scope.close()
        os.remove(folder)
    finally:
        places.SD, places.hold_card, art.free = kept_sd, kept_hold, kept_free
        art.use_cache(None)


def main():
    p = None
    tmp = "/tmp"
    argv = sys.argv[1:]
    while argv:
        a = argv.pop(0)
        if a.startswith("--plant="):
            p = a[len("--plant="):]
        elif a == "--tmp":
            tmp = argv.pop(0)
    plant(p)
    art.log = SAID.append
    _headless.display(64, 64)
    print("on " + sys.implementation.name)
    run(tmp)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
