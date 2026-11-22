# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An app that takes the whole screen: its app.json says "bar": "none"."""

import lvgl as lv

from . import seen


def main(scope):
    seen["whole"] = scope
    lv.label(scope.root).set_text("Whole")
