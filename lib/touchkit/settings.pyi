# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What one board has that another doesn't, kept in JSON."""

from typing import Any

from appkit.scope import AppScope

DEFAULTS: dict[str, Any]

def get(key: str, default: Any = None) -> Any:
    """A set-wide setting: `settings.json`'s, else the default."""
def config(scope: AppScope, defaults: dict[str, Any]) -> dict[str, Any]:
    """App `scope`'s settings: `defaults`, overridden by `config.json` in its `data_dir`."""
def move_hostname() -> str | None:
    """Make an older set's `"hostname"` setting the board's name, once; the name moved, or None."""
