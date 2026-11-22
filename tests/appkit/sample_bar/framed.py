# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An app under the Shell's bar, with an item of its own on it."""

import lvgl as lv
from appkit import bar

from . import seen


def main(scope):
    seen["framed"] = scope
    lv.label(scope.root).set_text("Framed")
    scope.bar.add(bar.Item("casting", lambda: ("cast", "Den")), scope)
