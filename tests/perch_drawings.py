# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch draws every still as it did when the golden file was written.

    micropython -X heapsize=128M tests/perch_drawings.py

Every still in ``perch/tools/stills.py``, each place and a set of the
chameleon's poses among them, is built, and svgio expands its records to SVG
text. The sha256 of that text must match its line in
``perch_drawings.golden``. On MicroPython the still is also drawn 320 pixels
wide, and the sha256 of its pixels and coverage must match too; on CPython,
svgio's stand-in draws with another rasteriser, so only the text is compared.

Where svgio swaps colours as it draws, a pose in one scheme drawn with its
colours swapped for another's must be, byte for byte, the pose built in the
other: that is how the stage changes colours without parsing again.

When a drawing is meant to change, write the file again on MicroPython with
``PERCH_RECORD=1``, and say in the commit which stills changed and why.

``PERCH_PLANT=nudged`` draws every circle a hundredth bigger, and
``half_table`` swaps only some of a pose's colours; each must fail, and
test_perch.py runs them.
"""

import binascii
import hashlib
import os
import sys

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path[:0] = [_HERE + "/../apps"]

import svgio

from perch import huey, vec
from perch import stage as stagemod
from perch.tools import stills

GOLDEN = _HERE + "/perch_drawings.golden"
PLANT = os.getenv("PERCH_PLANT")
if PLANT not in (None, "nudged", "half_table"):
    raise SystemExit("no such plant: %r" % PLANT)
RECORD = os.getenv("PERCH_RECORD") == "1"
PIXELS = sys.implementation.name == "micropython"
if RECORD and not PIXELS:
    raise SystemExit("write the golden file on MicroPython: it holds svgio's pixels")


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)


def sha(*parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
    return str(binascii.hexlify(h.digest()), "ascii")


if PLANT == "nudged":
    _circle = vec.circle

    def _nudged(cx, cy, r, *args, **kwargs):
        return _circle(cx, cy, r * 1.01, *args, **kwargs)

    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("perch") and getattr(module, "circle", None) is _circle:
            module.circle = _nudged

sources = []
_source = vec.Doc.source


def _keep(self, view):
    sources.append(_source(self, view))
    return sources[-1]


vec.Doc.source = _keep
lines = []
for name, build, width in stills.STILLS:
    build()
    drawing = sources.pop()
    check(drawing[:4] == b"\x01SVG", "%s is svgio's compact form" % name)
    line = name + " " + sha(bytes(svgio.expand(drawing)))
    if PIXELS:
        decoder = svgio.SvgDecoder()
        w, h = decoder.open(drawing, width=320)
        pixels, alpha = bytearray(w * h * 2), bytearray(w * h)
        decoder.decode(pixels, alpha)
        decoder.close()
        check(max(alpha) == 255, "%s drew something" % name)
        line += " %dx%d %s" % (w, h, sha(pixels, alpha))
    lines.append(line)
vec.Doc.source = _source
check(len(lines) >= 50, "every still was built")

if RECORD:
    with open(GOLDEN, "w") as f:
        f.write("# still, sha256 of its SVG text, its size and the sha256 of its pixels drawn 320 wide\n")
        for line in lines:
            f.write(line + "\n")
    print("wrote %d stills to %s" % (len(lines), GOLDEN))
else:
    with open(GOLDEN) as f:
        golden = [line.rstrip("\n") for line in f if not line.startswith("#")]
    check(len(golden) == len(lines), "the golden file has %d stills, perch draws %d" % (len(golden), len(lines)))
    for line, want in zip(lines, golden):
        if not PIXELS:
            want = " ".join(want.split()[:2])
        check(line == want, "%s isn't what it was: %s, golden %s" % (line.split()[0], line, want))
    print("%d stills as golden, %s" % (len(lines), "text and pixels" if PIXELS else "text only"))

# Colours swapped at decode against the pose built in the other scheme.
POSES = (("stand", 0, 0), ("walk", 3), ("tongue", 1), ("work", 1, 0), ("hold", "mug", 1), ("front", 1, 0), ("sleep",))
schemes = sorted(huey.COLORS)
check(len(schemes) >= 8, "the season's schemes are there with the four the chameleon wears")


def built(spec, scheme):
    """A pose as svgio opens it, and every colour drawn in it, in order."""
    huey._kept_text.clear()
    noted = vec.colours()
    doc = vec.Doc()
    body, view = stagemod._pose(doc, spec, scheme)
    vec.colours(False)
    doc.add(body)
    return doc.source(view), noted


probe = svgio.SvgDecoder()
swapped = 0
for n, spec in enumerate(POSES):
    for m, old in enumerate(schemes):
        new = schemes[(m + 1 + n) % len(schemes)]
        if new == old:
            continue
        (source, was), (wanted, now) = built(spec, old), built(spec, new)
        check(len(was) == len(now) > 20, "%r draws as many colours in %s as in %s" % (spec, old, new))
        table = {}
        for a, b in zip(was, now):
            check(table.setdefault(a, b) == b, "%r: each colour of %s has one counterpart in %s (%06x)" % (spec, old, new, a))
        if PLANT == "half_table":
            for a in sorted(table)[::2]:
                del table[a]
        w, h = probe.open(source, width=300)
        pixels, alpha = bytearray(w * h * 2), bytearray(w * h)
        probe.decode(pixels, alpha, colors=table)
        check(probe.open(wanted, width=300) == (w, h), "%r is one size in every scheme" % (spec,))
        pixels2, alpha2 = bytearray(w * h * 2), bytearray(w * h)
        probe.decode(pixels2, alpha2)
        check(pixels == pixels2 and alpha == alpha2, "%r in %s with its colours swapped is the pose built in %s" % (spec, old, new))
        swapped += 1
probe.close()
print("%d poses drawn in one scheme as another" % swapped)
print("ok")
