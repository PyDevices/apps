# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Every still tools/still.py can draw: each a name, a function that returns SVG text, and a width."""

from wander.tools import stills_chameleon_props
from wander.tools import stills_chameleon_shift
from wander.tools import stills_chameleon_views
from wander.tools import stills_mascot_chameleon
from wander.tools import stills_scene_bench
from wander.tools import stills_scene_coast
from wander.tools import stills_scene_desk

STILLS = (
    stills_mascot_chameleon.STILLS
    + stills_chameleon_views.STILLS
    + stills_chameleon_props.STILLS
    + stills_chameleon_shift.STILLS
    + stills_scene_coast.STILLS
    + stills_scene_bench.STILLS
    + stills_scene_desk.STILLS
)
