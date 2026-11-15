# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Find and save an app's files on the SD card, then flash, then the data root."""

from typing import Any

from . import data as data
from .scope import AppScope

SD: str
DIR_MODE: int

def flash_root(platform: str | None = None) -> str:
    """The top of flash: `""`, or `/flash` on an STM32."""
def folders(name: str) -> list[str]:
    """The folders a kind of file lives in, in the order they're looked at."""
def where_text(name: str) -> str:
    """The folders, for a message: `/sd/music, /music or /data/music`."""
def find(name: str, filename: str) -> str | None:
    """The first `<folder>/<filename>` that exists, or None."""
def files(name: str, extensions: tuple[str, ...], deep: bool = False) -> list[str]:
    """Every file of a kind, from all its folders, as full paths."""
def write_folder(name: str) -> str:
    """The first folder a file of this kind can be written in, made if missing.

    Raises:
        OSError: none of them takes a file.
    """
def mount_card(write: bool = False) -> Any:
    """Mount the SD card at `SD`.

    Returns the card to pass to `unmount_card`; True when something else already
    has it mounted; False when there's no card.
    """
def unmount_card(card: Any) -> None:
    """Undo `mount_card`; a mount that wasn't ours is left alone."""
def hold_card(scope: AppScope, write: bool = False) -> Any:
    """Mount the card while `scope`'s app is open; returns what `mount_card` did."""
