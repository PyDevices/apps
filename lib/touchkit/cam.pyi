# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the camera apps share: opening the CSI camera, its settings, and where photos go."""

from typing import Any

from appkit.scope import AppScope

FORMAT: str
BRIGHT: int
LIGHT: tuple[tuple[str, int], ...]
PHOTOS: str
TAGS: tuple[str, ...]

class NoCameraPort(OSError):
    """The board has no CSI camera port at all, as opposed to a port with no camera on it."""

def no_camera_text(err: BaseException, app: str) -> str:
    """What `app` shows when `open_camera` raised `err`."""
def options(scope: AppScope) -> dict[str, Any]:
    """The camera settings the camera apps share: the Camera app's store."""
def open_camera(opts: dict[str, Any]) -> Any:
    """The CSI camera, turned as `opts` say, with its colour order right."""
def apply_controls(c: Any, opts: dict[str, Any]) -> None:
    """Brightness and the light level (the AE target, the gain ceiling)."""
def preview_size(cam: Any, longest: int) -> tuple[int, int]:
    """The preview's `(width, height)`, its longer side `longest`."""
def mount_sd(readonly: bool = True) -> Any:
    """Mount the SD card at `/sd`."""
def unmount_sd(card: Any) -> None: ...
def photos(scope: AppScope | None = None) -> list[tuple[str, str]]:
    """`[(key, path)]` of every photo, newest name first."""
def next_name(scope: AppScope | None = None) -> str:
    """A new photo's path, numbered after the highest `IMG_` anywhere."""
def aligned(n: int) -> memoryview:
    """A writable `n`-byte memoryview that starts on a 64-byte boundary."""

class Preview:
    """The camera's picture in a box: straight into the panel's framebuffer, or an LVGL image on a panel with none."""

    buf: memoryview | None
    fb: memoryview | None
    image: Any
    x: int
    y: int
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        w: int,
        h: int,
        origin: tuple[int, int] = (0, 0),
        own: bool = False,
        display: Any = None,
    ) -> None: ...
    def capture(self, c: Any, timeout: int = 200) -> bool:
        """The next frame from camera `c` into the preview; False when none came."""
    def show(self) -> None:
        """Redraw the picture after a frame went into `buf` (a panel with no framebuffer)."""
