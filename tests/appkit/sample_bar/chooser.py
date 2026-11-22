# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An app that opens the picker and the on-screen keyboard while it runs."""

import lvgl as lv
from appkit import keys

from . import seen


def main(scope):
    seen["chooser"] = scope
    field = lv.textarea(scope.root)
    keys.attach(field)
    keys.show(field)
    scope.launcher.shell.open_picker("net")
