# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Patch, note and controller names a DAW can read, for the sound module."""

from typing import Any

_Catalog = dict[str, Any]
_Entry = dict[str, Any]

MANUFACTURER: str
MODEL: str
CONTROLS: tuple[tuple[int, str], ...]
SENDS: tuple[tuple[int, str], ...]

def load(path: str) -> _Catalog:
    """A catalog read from `path`."""
def installed(package: str) -> _Catalog:
    """The catalog that the installed `package` carries."""
def parts(instruments: _Catalog) -> list[tuple[int, int, _Entry]]:
    """`(bank MSB, program, entry)` for each instrument the module plays."""
def controls(effects: _Catalog, macros: list[dict[str, Any]] | None = None) -> list[tuple[int, str]]:
    """`(cc, name)` for every controller."""
def midnam(instruments: _Catalog, effects: _Catalog) -> str:
    """The MIDNAM document, as text."""
def cakewalk_ins(instruments: _Catalog, effects: _Catalog) -> str:
    """The Cakewalk instrument definition file, as text."""
def reabank(instruments: _Catalog) -> str:
    """The REAPER bank/program file, as text."""
def main(argv: list[str]) -> int: ...
