# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Keys: one keyboard input for every keyboard, and one on-screen keyboard."""

from typing import Any

KEYBOARD_PCT: int

def hid_char(usage: int, modifiers: int = 0) -> str | int | None:
    """What a HID keyboard `usage` types: a character, an LVGL key code, or None."""
def indev() -> Any:
    """The keypad input that `push` feeds, made the first time."""
def push(key: str | int) -> None:
    """Type `key` into whatever has focus; a real keyboard typing closes the on-screen one."""
def hid_key(usage: int, modifiers: int = 0) -> str | int | None:
    """`push` what a HID keyboard's key down types; returns it, or None."""
def focus(group: Any) -> None:
    """Send every keypad and encoder to `group` until `release` gives it up."""
def release(group: Any) -> None:
    """Give the keypads and encoders up: to the overlay below, or back to their own groups."""
def focused_group() -> Any:
    """The group keys go to now: the newest `focus`, or LVGL's default."""
def keyboard() -> Any:
    """The on-screen keyboard on `lv.layer_top()`, made hidden the first time."""
def is_shown() -> bool: ...
def show(field: Any) -> None:
    """Open the on-screen keyboard on `field`, an `lv.textarea`."""
def hide() -> None:
    """Close the on-screen keyboard, if it's open."""
def attach(field: Any) -> Any:
    """Open the on-screen keyboard when `field` is focused or tapped; returns `field`."""
