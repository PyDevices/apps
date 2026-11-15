# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from . import engine as engine
from _typeshed import Incomplete

RATE: int
CHANNELS: int
ticks_ms: Incomplete
ticks_diff: Incomplete

class Wav:
    f: Incomplete
    rate: Incomplete
    channels: Incomplete
    bytes: int
    def __init__(self, path, rate=..., channels=...) -> None: ...
    def write(self, data) -> None: ...
    def close(self) -> None: ...

def serve(module, midi_in, wav=None, seconds: int = 600, idle=None, wait=None, tail: float = 2.0, out=None, log=...): ...
def report(module, total, worst, log=...) -> None: ...
def main(argv=None) -> None: ...
