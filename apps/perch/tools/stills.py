# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Every still tools/still.py can draw: each a name, a function that returns SVG text, and a width."""

from perch.tools import stills_hue_props
from perch.tools import stills_hue_shift
from perch.tools import stills_hue_views
from perch.tools import stills_hue
from perch.tools import stills_scene_bench
from perch.tools import stills_scene_coast
from perch.tools import stills_scene_desk

STILLS = (
    stills_hue.STILLS
    + stills_hue_views.STILLS
    + stills_hue_props.STILLS
    + stills_hue_shift.STILLS
    + stills_scene_coast.STILLS
    + stills_scene_bench.STILLS
    + stills_scene_desk.STILLS
)
