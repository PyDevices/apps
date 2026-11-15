# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The main-thread loop, for work too heavy for a timer."""

from collections.abc import Callable
from typing import Any, Protocol

class _Scope(Protocol):
    @property
    def closed(self) -> bool: ...
    def every(self, ms: int, callback: Callable[[Any], Any], *, name: str | None = None) -> Any: ...

class _App(Protocol):
    @property
    def quit_requested(self) -> bool: ...

STEP_MS: int
IDLE_MS: int

def set_function(scope: _Scope, fn: Callable[[], Any] | None, steps: bool = True) -> bool:
    """Make `fn` the foreground function, owned by `scope`; None clears `scope`'s.

    Returns True when `fn` runs now, False when it waits for `serve`.
    """
def clear(scope: _Scope | None = None) -> None:
    """Clear the foreground function, if `scope` (default: anyone) set it."""
def calling(scope: _Scope) -> bool:
    """True while `scope`'s foreground function is in a call now."""
def after_calls(fn: Callable[..., Any], *args: Any) -> None:
    """Call `fn(*args)` once no call of the foreground function is in progress."""
def current() -> Callable[[], Any] | None:
    """The foreground function, or None."""
def owner() -> _Scope | None:
    """The scope that set the foreground function, or None."""
def serving() -> bool:
    """True while `serve` is running the loop."""
def next_turn(fn: Callable[[Any], Any], arg: Any) -> bool:
    """Call `fn(arg)` from `serve`'s loop at its next turn; False when nothing runs the loop."""
def stop() -> None:
    """Have `serve` return after the call it's in."""
def serve(app: _App | None = None) -> None:
    """Run the foreground function over and over until the program quits."""
def recover() -> None:
    """After a Ctrl-C: put multimer's wake and LVGL's timer back before the REPL takes over."""
