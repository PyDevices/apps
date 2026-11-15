# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""One background thread for blocking calls, shared by every app."""

from collections.abc import Callable
from typing import Any

STACK: int

_Done = Callable[[Any, BaseException | None], Any]

class _Base:
    busy: bool
    ran: int
    errors: int
    def __init__(self) -> None: ...
    def queued(self, owner: Any = None) -> int:
        """How many jobs are waiting, or `owner`'s."""

class Worker(_Base):
    """Runs jobs one at a time on a background thread."""

    def __init__(self, stack: int | None = None) -> None: ...
    def submit(
        self,
        work: Callable[[], Any],
        done: _Done | None = None,
        key: Any = None,
        owner: Any = None,
        release: Callable[[], Any] | None = None,
    ) -> None:
        """Run `work()` on the thread, then `done(value, error)` on the main thread."""
    def pending(self, key: Any, owner: Any = None) -> bool:
        """True while a job with `key` is waiting or running."""
    def cancel(self, owner: Any) -> None:
        """Drop everything `owner` queued that hasn't started."""

class TimerWorker(_Base):
    """Runs jobs one per timer tick, where there are no threads."""

    def __init__(self) -> None: ...
    def submit(
        self,
        work: Callable[[], Any],
        done: _Done | None = None,
        key: Any = None,
        owner: Any = None,
        release: Callable[[], Any] | None = None,
    ) -> None:
        """Queue `work()`, then `done(value, error)` once it has run."""
    def pending(self, key: Any, owner: Any = None) -> bool:
        """True while a job with `key` is waiting or running."""
    def cancel(self, owner: Any) -> None:
        """Drop everything `owner` queued that hasn't started."""

class ScopedWorker:
    """A worker as one app's scope sees it."""

    worker: Worker | TimerWorker
    owner: Any
    def __init__(self, worker: Worker | TimerWorker, owner: Any) -> None: ...
    @property
    def busy(self) -> bool: ...
    def submit(
        self,
        work: Callable[[], Any],
        done: _Done | None = None,
        key: Any = None,
        release: Callable[[], Any] | None = None,
    ) -> None:
        """Run `work()` in the background, then `done(value, error)` on the main thread."""
    def pending(self, key: Any) -> bool:
        """True while this app has a job with `key` waiting or running."""
    def queued(self) -> int:
        """How many of this app's jobs are waiting."""
    def cancel(self) -> None:
        """Drop every job this app queued that hasn't started."""

def threads() -> bool:
    """True where this interpreter can start a thread."""
def shared() -> Worker | TimerWorker:
    """The program's one worker, started on first use."""
