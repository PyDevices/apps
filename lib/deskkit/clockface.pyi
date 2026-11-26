# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An analog clock face in LVGL that fits any screen, in skins you can add to."""
from collections.abc import Callable, Mapping
from typing import Any

BUILTIN_SKINS: dict[str, dict[str, Any]]
BUILTIN_SKIN_ORDER: tuple[str, ...]

class GlassShimmer:
    """Subtle specular layers drawn above the dial to suggest curved glass."""
    def __init__(self, parent: Any, width: int, height: int, radius: int, light: int, dark: int) -> None: ...

class AnalogClock:
    """Responsive analog clock widget with a validated, extensible skin registry."""
    skins: dict[str, dict[str, Any]]
    skin: dict[str, Any]
    parent: Any
    @classmethod
    def register_skin(cls, name: str, mapping: Mapping[str, Any]) -> None: ...
    @classmethod
    def register_skins(cls, mappings: Mapping[str, Mapping[str, Any]]) -> None: ...
    @classmethod
    def skin_names(cls) -> tuple[str, ...]: ...
    def __init__(
        self,
        parent: Any,
        size: tuple[int, int],
        read_time: Callable[[], tuple[int, int, int]],
        skin: str | Mapping[str, Any] = ...,
    ) -> None: ...
    def update_time(self) -> None: ...
