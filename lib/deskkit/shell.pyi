# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from . import localtime as localtime
from _typeshed import Incomplete
from appkit import Shell

def is_awake(hour, weekday, awake, weekends): ...
def tune_touch(indev) -> None: ...

class DeskShell(Shell):
    apps: Incomplete
    awake: Incomplete
    weekends: Incomplete
    idle_ms: Incomplete
    def __init__(self, launcher, apps, *, awake, weekends, idle_ms) -> None: ...
    def make_root(self, scope): ...
