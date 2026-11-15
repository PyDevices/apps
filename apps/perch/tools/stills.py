# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Every still tools/still.py can draw: each a name, a function that returns SVG text, and a width."""

from perch.tools import stills_huey_props
from perch.tools import stills_huey_shift
from perch.tools import stills_huey_views
from perch.tools import stills_huey
from perch.tools import stills_scene_bench
from perch.tools import stills_scene_coast
from perch.tools import stills_scene_desk

STILLS = (
    stills_huey.STILLS
    + stills_huey_views.STILLS
    + stills_huey_props.STILLS
    + stills_huey_shift.STILLS
    + stills_scene_coast.STILLS
    + stills_scene_bench.STILLS
    + stills_scene_desk.STILLS
)
