# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch's drawings reach svgio the same whichever way they go.

    micropython -X heapsize=128M tests/perch_drawings.py

`perch.vec` draws with one of two sets of helpers: records of svgio's compact
form where svgio reads them, SVG text where it doesn't. Every still, each
place and a set of the chameleon's poses among them, is built both ways here.
The text svgio makes of the records must be, character for character, the
text the other helpers wrote. Every fourth one is then drawn both ways, from
the records and from the text, and the pixels compared.

``PERCH_PLANT=loose_number`` writes the text's numbers to four figures, not
five, which must fail; test_perch.py runs it. An svgio that doesn't read the
compact form has nothing to compare: the script says so and passes.
"""

import os
import sys

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path[:0] = [_HERE + "/../apps"]

import svgio

PLANT = os.getenv("PERCH_PLANT")
if PLANT not in (None, "loose_number"):
    raise SystemExit("no such plant: %r" % PLANT)

if not hasattr(svgio, "expand"):
    print("this svgio doesn't read the compact form: nothing to compare")
    print("ok")
    sys.exit(0)


class _TextOnly:
    """svgio as a firmware without the compact form has it."""

    SvgDecoder = svgio.SvgDecoder


def drawings(module):
    """Every still's ``(name, source)``, drawn by perch with *module* as its svgio."""
    for name in [n for n in sys.modules if n == "perch" or n.startswith("perch.")]:
        del sys.modules[name]
    sys.modules["svgio"] = module
    from perch import vec
    from perch.tools import stills

    if PLANT and not vec.COMPACT:
        vec._n = lambda v: "%.4g" % v
    sources = []
    source = vec.Doc.source

    def keep(self, view):
        sources.append(source(self, view))
        return sources[-1]

    vec.Doc.source = keep
    out = []
    for name, build, width in stills.STILLS:
        build()
        out.append((name, sources.pop()))
    sys.modules["svgio"] = svgio
    return vec.COMPACT, out


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)

compact, as_text = drawings(_TextOnly)
check(not compact, "without expand(), perch writes text")
compact, as_records = drawings(svgio)
check(compact, "with expand(), perch packs records")
check(len(as_text) == len(as_records) >= 50, "every still was built both ways")
drawn = 0
for count, ((name, text), (_, drawing)) in enumerate(zip(as_text, as_records)):
    check(drawing[:4] == b"\x01SVG" and text[:4] == b"<svg", "%s is records one way and text the other" % name)
    check(bytes(svgio.expand(drawing)) == text, "%s: svgio makes of the records the text perch writes" % name)
    if count % 4 == 0:
        by_text, by_records = svgio.SvgDecoder(), svgio.SvgDecoder()
        w, h = by_text.open(text, width=320)
        check(by_records.open(drawing, width=320) == (w, h), "%s is the same size both ways" % name)
        pixels, alpha = bytearray(w * h * 2), bytearray(w * h)
        pixels2, alpha2 = bytearray(w * h * 2), bytearray(w * h)
        by_text.decode(pixels, alpha)
        by_records.decode(pixels2, alpha2)
        check(pixels == pixels2 and alpha == alpha2, "%s is the same pixels both ways" % name)
        check(max(alpha) == 255, "%s drew something" % name)
        drawn += 1
check(drawn >= 12, "enough were drawn")
print("%d drawings, %d of them drawn both ways" % (count + 1, drawn))
print("ok")
