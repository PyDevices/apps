# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build the app index a frozen build reads in place of the apps folder."""

from collections.abc import Callable
from typing import Any

MODULE: str
PACKAGE: str
INIT_TEXT: str

def check_icon(entry: str, info: dict[str, Any], path: str) -> None:
    """Raise `ValueError` when app `entry` shows a tile and has no valid `"icon"` in its app.json."""
def collect(folder: str) -> list[tuple[str, dict[str, Any]]]:
    """`[(entry, app.json contents), ...]` for every app in `folder`, sorted."""
def render(apps: list[tuple[str, dict[str, Any]]], source: str | None = None) -> str:
    """The `_appkit_apps` module's text for `apps` (see `collect`)."""
def write(folder: str, out: str | None = None) -> str:
    """Write the index of `folder` to `out`; returns the file's path."""
def freeze_apps(
    folder: str, module: Callable[..., Any], package: Callable[..., Any], out_dir: str | None = None
) -> str:
    """From a MicroPython manifest: freeze every app in `folder` and its index.

    `module` and `package` are the manifest's own functions. Returns the folder
    the index was written to.
    """
def main(argv: list[str] | None = None) -> int:
    """`python -m appkit.index APPS [-o OUT]`: write `_appkit_apps.py`."""
