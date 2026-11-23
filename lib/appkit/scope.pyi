# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Everything an app makes through its scope, released when the app closes."""

import types
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, overload

_F = TypeVar('_F', bound=Callable[..., Any])
_T = TypeVar('_T')

class _Timer(Protocol):
    @property
    def running(self) -> bool: ...
    def deinit(self) -> None: ...

class _App(Protocol):
    @property
    def displays(self) -> Any: ...
    @property
    def primary(self) -> Any: ...
    def on(self, event_type: Any, callback: Callable[..., Any]) -> Any: ...
    def off(self, event_type: Any, callback: Callable[..., Any]) -> Any: ...
    def register(self, dev: Any) -> Any: ...
    def unregister(self, dev: Any) -> Any: ...

def keep(obj: Any) -> Any:
    """Mark *obj* on a top layer as the program's: closing the running app leaves it."""
def unkeep(obj: Any) -> None:
    """Undo `keep`."""
def open_scopes(app: _App | None = None) -> list[AppScope]:
    """Every scope not yet closed, oldest first; only `app`'s when given."""
def mem_free() -> int | None:
    """Free GC heap in bytes after a collection, or None where it can't be read."""

class AppScope:
    """What one app made, through its scope; `close()` releases it."""

    app: _App
    name: str | None
    launcher: Any
    root: Any
    bar: Any
    size: tuple[int, int] | None
    rect: tuple[int, int, int, int] | None
    problems: list[str]
    retained: int | None
    free_after_close: int | None
    def __init__(self, app: _App, name: str | None = None, *, modules: tuple[str, ...] | list[str] = ()) -> None: ...
    @property
    def displays(self) -> Any:
        """The app's displays."""
    @property
    def primary(self) -> Any:
        """The app's primary display."""
    @property
    def closed(self) -> bool: ...
    @property
    def timers(self) -> tuple[_Timer, ...]:
        """This app's timers that are still armed."""
    @property
    def worker(self) -> Any:
        """The shared background thread, as this app sees it."""
    @worker.setter
    def worker(self, value: Any) -> None: ...
    @property
    def data_dir(self) -> str:
        """A folder for this app's own files, made on first use."""
    @data_dir.setter
    def data_dir(self, value: str | None) -> None: ...
    def data_dir_of(self, name: str) -> str:
        """App `name`'s folder, made on first use."""
    def store(self, name: str | None = None) -> dict[str, Any]:
        """A dict in RAM that outlives this app's close: its own, or app `name`'s."""
    @overload
    def every(self, ms: int | None, callback: Callable[[Any], Any], *, period: None = None, name: str | None = None) -> _Timer: ...
    @overload
    def every(self, ms: Callable[[Any], Any], callback: None = None, *, period: None = None, name: str | None = None) -> _Timer: ...
    @overload
    def every(self, ms: None = None, *, callback: Callable[[Any], Any], period: int | None = None, name: str | None = None) -> _Timer: ...
    @overload
    def every(self, ms: int | None = None, callback: None = None, *, period: None = None, name: str | None = None) -> Callable[[_F], _F]: ...
    @overload
    def after(self, ms: int, callback: Callable[[Any], Any], *, name: str | None = None) -> _Timer: ...
    @overload
    def after(self, ms: int, callback: None = None, *, name: str | None = None) -> Callable[[_F], _F]: ...
    def stop_timers(self) -> None:
        """Cancel every timer this app made."""
    @overload
    def on(self, event_type_or_list: Any, callback: _F) -> _F: ...
    @overload
    def on(self, event_type_or_list: Any, callback: None = None) -> Callable[[_F], _F]: ...
    def off(self, event_type_or_list: Any, callback: Callable[..., Any]) -> None:
        """Unsubscribe from App events."""
    def subscribe(self, device: Any, callback: _F, event_types: Any = None) -> _F:
        """`device.subscribe(callback)` on a shared device; unsubscribed at close."""
    def follow(self, kind: str, callback: Callable[[list[Any]], Any], registry: Any = None) -> list[Any]:
        """Call `callback(endpoints)` when what's in use for endpointkit `kind` changes, until close; returns what's in use now."""
    def register(self, dev: _T) -> _T:
        """Register a device with the App; unregistered at close."""
    def unregister(self, dev: Any) -> None:
        """Unregister a device."""
    def adopt(self, obj: _T, close: Callable[[_T], Any] | None = None) -> _T:
        """Own `obj` until close: then `close(obj)`, or its `delete()`, `deinit()` or `close()`."""
    def on_close(self, fn: _F) -> _F:
        """Call `fn()` first thing in close(). Usable as a decorator."""
    def foreground(self, fn: Callable[[], Any] | None, *, steps: bool = True) -> bool:
        """Have the program's main-thread loop call `fn()` over and over until this app closes."""
    def switch(self, name: str) -> None:
        """Ask the launcher to switch to app `name`, after this callback returns."""
    def screen(self, load: bool = True) -> Any:
        """A new LVGL screen for this app, loaded unless `load` is False."""
    def close(self) -> list[str]:
        """Release everything this app made; return what couldn't be released."""
    def __enter__(self) -> AppScope: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: types.TracebackType | None) -> bool: ...
