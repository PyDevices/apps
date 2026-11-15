# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Launcher: start switchable apps by name, and switch between them."""

from collections.abc import Mapping
from typing import Any, Literal

from . import data as data, foreground as foreground
from .data import DESKTOPS as DESKTOPS
from .scope import AppScope as AppScope, mem_free as mem_free
from .shell import Shell

RESTART_EXIT_CODE: int
PROBE_LIMIT: int
MICROPYTHON: bool

def largest_free_block(limit: int | None = None) -> int | None:
    """The largest bytearray that can be allocated now, in bytes; None where the heap can't be read."""
def lacks(needs: list[str] | tuple[str, ...] | None) -> str | None:
    """The first of `needs` this interpreter doesn't have, or None."""

INIT_TEXT: str

def host() -> Literal['board', 'desktop', 'cpython', 'browser', 'circuitpython']:
    """Which restart path this interpreter takes."""

SCRIPT: str

def save_next(name: str, count: int = 1, path: str | None = None) -> None:
    """Keep `name` (and how many restarts in a row led here) for the next boot."""
def take_next() -> tuple[str, int] | None:
    """The `(name, count)` a restart left for this boot, cleared once read, or None."""
def read_next(clear: bool = False) -> tuple[str, int, str | None] | None:
    """The `(name, count, path)` a restart left for this boot, or None."""
def restart_into(name: str | None, count: int = 1, path: str | None = None) -> None:
    """Restart the program straight into app `name`, the host's way."""
def run_pending_script(data_root: str | None = None) -> bool:
    """Run the script a launcher restarted into, if there is one."""

class Launcher:
    """Owns the long-lived App, starts apps by name and switches between them."""

    app: Any
    home: str | None
    shell: Shell | None
    info: dict[str, dict[str, Any]]
    min_free: int | None
    min_block: int | None
    max_restarts: int
    current: str | None
    scope: AppScope | None
    restarts: int
    switches: int
    problems: list[str]
    baseline: tuple[int | None, int | None] | None
    last: tuple[str, int | None, int | None] | None
    def __init__(
        self,
        app: Any = None,
        apps: Mapping[str, str] | None = None,
        *,
        home: str | None = None,
        shell: Shell | None = None,
        min_free: int | None = None,
        min_block: int | None = None,
        max_restarts: int = 3,
    ) -> None: ...
    def add(self, name: str, module: str | None = None) -> None:
        """Register app `name`, whose `main(scope)` is in `module` (default `name`)."""
    def add_script(self, name: str, module: str | None = None, path: str | None = None) -> None:
        """Register `name` as a plain script that builds its own `App` when imported."""
    def is_script(self, name: str) -> bool:
        """True when `name` is a plain script rather than an app."""
    def scan(self, folder: str = 'apps') -> dict[str, dict[str, Any]]:
        """Register every app in `folder`; returns the apps' `app.json` contents, by name."""
    @property
    def names(self) -> tuple[str, ...]:
        """Every app's and script's name, in the order they were added."""
    def heap(self) -> tuple[int | None, int | None]:
        """`(free, largest_free_block)` now, or `(None, None)` on CPython."""
    def boot(self, default: str | None = None) -> str:
        """Start the app a restart asked for, else `default`, else `home`; returns its name."""
    def start(self, name: str) -> None:
        """Start app `name`; the same as `switch`."""
    def request(self, name: str) -> None:
        """Switch to `name` at the next safe point, after the current callback."""
    def switch(self, name: str) -> Literal['start', 'switch', 'restart']:
        """Close the running app and start app `name`."""
    def stop(self) -> list[str]:
        """Close the running app and cancel a pending switch."""

def supervise(cmd: list[str] | tuple[str, ...]) -> int:
    """Run `cmd`, and again each time it exits asking for a restart; returns its final exit code."""
def main(argv: list[str] | None = None) -> int:
    """`python -m appkit.launcher [--] <command>`: run a launcher program, restarting it whenever it asks."""
