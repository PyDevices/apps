# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build the app index a frozen build reads beside the apps folder."""

from collections.abc import Callable
from typing import Any

MODULE: str
FILES_MODULE: str
PACKAGE: str
SKIP_DIRS: tuple[str, ...]
SKIP_FILES: tuple[str, ...]
INIT_TEXT: str

def check_icon(entry: str, info: dict[str, Any], path: str) -> None:
    """Raise `ValueError` when app `entry` shows a tile and has no valid `"icon"` in its app.json."""
def collect(folder: str) -> list[tuple[str, dict[str, Any]]]:
    """`[(entry, app.json contents), ...]` for every app in `folder`, sorted."""
def render(apps: list[tuple[str, dict[str, Any]]], source: str | None = None) -> str:
    """The `_appkit_apps` module's text for `apps` (see `collect`)."""
def write(folder: str, out: str | None = None) -> str:
    """Write the index of `folder` to `out`; returns the file's path."""
def sibling_apps(folder: str) -> set[str]:
    """The other apps the app in `folder` imports from (`from ..perch import stage`)."""
def choose(folder: str, names: str | list[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    """The apps in `folder` to freeze: every one, or `names` and the apps they import from."""
def render_files(files: dict[str, bytes]) -> str:
    """The `_appkit_files` module's text for `files`, by path."""
def freeze_apps(
    folder: str,
    module: Callable[..., Any],
    package: Callable[..., Any],
    out_dir: str | None = None,
    names: str | list[str] | None = None,
    native: bool = True,
) -> str:
    """From a MicroPython manifest: freeze the apps in `folder` (or those in `names`) and their index.

    `module` and `package` are the manifest's own functions. Returns the folder
    the index was written to.
    """
def main(argv: list[str] | None = None) -> int:
    """`python -m appkit.index APPS [-o OUT]`: write `_appkit_apps.py`."""
