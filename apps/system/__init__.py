# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""System is Info now: this stands in for it, off Home's pages.

A board that had System installed keeps its folder when the apps are installed
again; this one replaces it, so the old app's tile goes and ``apps.system``
still answers. Use ``apps.info`` in new code.
"""

from ..info import main, stats  # noqa: F401
