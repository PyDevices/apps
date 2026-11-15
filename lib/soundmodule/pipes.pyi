# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""MIDI through two files, for an interpreter that can't open the MIDI port itself."""

from typing import Any

IN: str
OUT: str

class FileIn:
    """The bytes appended to a file, as a MIDI input port."""

    def __init__(self, path: str, size: int = 256) -> None: ...
    def any(self) -> int:
        """Bytes read ahead and not yet taken."""
    def readinto(self, buf: bytearray | memoryview, nbytes: int | None = None) -> int | None: ...
    def read(self, nbytes: int | None = None) -> bytes | None: ...
    def close(self) -> None: ...
    def deinit(self) -> None: ...

class FileOut:
    """A MIDI output port that appends to a file."""

    def __init__(self, path: str) -> None: ...
    def write(self, buf: bytes | bytearray | memoryview, nbytes: int | None = None) -> int: ...
    def close(self) -> None: ...
    def deinit(self) -> None: ...

def ports(folder: str) -> tuple[FileIn, FileOut]:
    """`(midi_in, midi_out)` through `folder`'s two files."""
