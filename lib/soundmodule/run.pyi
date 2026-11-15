# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Run the sound module headless: MIDI in from a port, sound out to a WAV file."""

from typing import Any, Callable, Protocol

from .engine import Module

class _MidiIn(Protocol):
    def readinto(self, buf: bytearray, nbytes: int | None = None) -> int | None: ...

_Buf = bytes | bytearray | memoryview

RATE: int
CHANNELS: int

def ticks_ms() -> int: ...
def ticks_diff(a: int, b: int) -> int: ...

class Wav:
    """A 16-bit PCM WAV file written as it goes; `close` fixes the sizes."""

    f: Any
    rate: int
    channels: int
    bytes: int
    def __init__(self, path: str, rate: int = 48000, channels: int = 2) -> None: ...
    def write(self, data: _Buf) -> None: ...
    def close(self) -> None: ...

def serve(
    module: Module,
    midi_in: _MidiIn | None,
    wav: Wav | None = None,
    seconds: float = 600,
    idle: float | None = None,
    wait: float | None = None,
    tail: float = 2.0,
    out: Any = None,
    log: Callable[[str], Any] = ...,
) -> tuple[int, list[int]]:
    """Feed `midi_in` to `module` and render its output by the clock into `wav`.

    Returns the bytes of MIDI and the most the render fell behind in ms, before the first note and after it.
    """
def report(module: Module, total: int, worst: list[int], log: Callable[[str], Any] = ...) -> None:
    """Say what came in and what played."""
def main(argv: list[str] | None = None) -> None: ...
