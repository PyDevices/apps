# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch's drawings reach svgio the same whichever way they go.

    micropython -X heapsize=128M tests/perch_drawings.py

Every still, each place and a set of the chameleon's poses among them, is
built once as records of svgio's compact form. The SVG text `vec.expand`
makes of the records in Python must be, character for character, the text
svgio makes of them, since that text is what an svgio that can't read the
records is given. Every fourth one is then drawn both ways, from the records
and from the text, and the pixels compared.

``PERCH_PLANT=loose_number`` writes numbers in Python to four figures, not
five, which must fail; test_perch.py runs it. An svgio that doesn't read the
compact form has nothing to compare: the script says so and passes.
"""

import os
import sys

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path[:0] = [_HERE + "/../apps"]

import svgio
from perch import vec
from perch.tools import stills

PLANT = os.getenv("PERCH_PLANT")
if PLANT == "loose_number":
    vec._n = lambda v: "%.4g" % v
elif PLANT is not None:
    raise SystemExit("no such plant: %r" % PLANT)

if not vec.COMPACT:
    print("this svgio doesn't read the compact form: nothing to compare")
    print("ok")
    sys.exit(0)

# what a still's builder hands to Doc.svg is what the app hands to svgio
records = []
_svg = vec.Doc.svg


def _keep(self, view):
    records.append(self.compact(view))
    return _svg(self, view)


vec.Doc.svg = _keep


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)


drawn = 0
for count, (name, build, width) in enumerate(stills.STILLS):
    text = build().encode()
    drawing = records.pop()
    check(not records, "%s is one drawing" % name)
    check(svgio.expand(drawing) == text, "%s: svgio and vec.expand write the same SVG text" % name)
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
check(count >= 50 and drawn >= 12, "every still was compared")
print("%d drawings, %d of them drawn both ways" % (count + 1, drawn))
print("ok")
