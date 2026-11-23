# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.forecast: the place you've chosen and its weather, from Open-Meteo."""
from collections.abc import Callable
from typing import Any, Protocol

from . import localtime as localtime

class _Worker(Protocol):
    def submit(self, work: Callable[[], Any], done: Callable[[Any, Any], None] | None = None, *, key: str | None = None) -> Any: ...

class _AppScope(Protocol):
    worker: _Worker
    def every(self, ms: int, callback: Callable[..., None]) -> Any: ...
    def follow(self, kind: str, callback: Callable[[list[Any]], Any]) -> list[Any]: ...

MAX_AGE_S: int
RETRY_S: int
latest: dict[str, Any] | None
last_error: BaseException | None
ip_place: dict[str, Any] | None

def place() -> dict[str, Any] | None:
    """Return the saved place as a dict, or None before one is chosen."""
def current() -> dict[str, Any] | None:
    """Return the place the forecast is for: the chosen one, else the one from the board's IP address, else None."""
def choose(zip_code: str) -> dict[str, Any]:
    """Look up `zip_code` and make it the place. It blocks: call it from a worker."""
def set_units(units: str) -> None:
    """Show temperatures in `units`, `"F"` or `"C"`, from now on."""
def degrees(fahrenheit: float) -> int:
    """Return a Fahrenheit reading as whole degrees in the chosen units."""
def parse(reply: dict[str, Any]) -> dict[str, Any]:
    """Turn an Open-Meteo reply into the plain dict the apps show."""
def fetch() -> bool:
    """Get the forecast now, and keep the clock right. It blocks: call it from a worker."""
def is_stale() -> bool:
    """Return True when a fetch is due: the data is old and no try was recent."""
def network_moved() -> None:
    """Another network carries traffic now: the next check fetches, sets the clock and finds the place again."""
def keep_fresh(scope: _AppScope, on_update: Callable[[], None] | None = None) -> None:
    """Fetch whenever the forecast goes stale, for as long as `scope` is open."""
