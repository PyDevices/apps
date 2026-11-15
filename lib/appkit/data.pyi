# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Where apps keep their files: the data root, and a folder per app under it."""

from collections.abc import Callable

DESKTOPS: tuple[str, ...]

def desktop(platform: str | None = None, implementation: str | None = None) -> bool:
    """True on a desktop operating system, False on a board or in the browser."""
def default_root(
    platform: str | None = None, implementation: str | None = None, getenv: Callable[[str], str | None] | None = None
) -> str:
    """The data root this host uses when nothing sets one."""
def root() -> str:
    """The data root: what `set_root` set, else `default_root`."""
def set_root(path: str | None) -> None:
    """Move the data root for the whole program; None goes back to the default."""
def join(base: str, *parts: str) -> str:
    """`base` and `parts` joined with the separator `base` already uses."""
def makedirs(path: str) -> str:
    """Make folder `path` and any parents it needs; fine if it exists."""
def app_dir(name: str, base: str | None = None) -> str:
    """App `name`'s folder under `base` (default: the data root), made if missing."""
