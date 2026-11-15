# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A stand-in adapter: an instrument with patches and macros, and no sound."""
from collections.abc import Callable

MACRO_LABELS: tuple[str, ...]

class MockAdapter:
    """An adapter with `patch_count` patches and `macro_count` labelled macros."""

    script_name: str
    macro_labels: list[str]
    macro_count: int
    patches: list[str]
    patch_index: int
    macro_values: list[int]
    bypass: bool
    engine_ready: bool
    engine_error: int
    echo: bool
    edits: list[tuple[str, int, int | bool]]
    reloads: int
    def __init__(self, name: str = 'Demo Synth', patch_count: int = 40, macro_count: int = 16, echo: bool = True) -> None: ...
    def on_external_change(self, callback: Callable[[str, int, int], None]) -> None: ...
    def set_macro(self, index: int, value: int) -> None: ...
    def set_patch(self, index: int) -> None: ...
    def set_bypass(self, enabled: object) -> None: ...
    def request_reload(self) -> None: ...
    def tick(self) -> None: ...
    def close_all(self) -> None: ...
    def host_program(self, index: int) -> None:
        """A host or sequencer picks patch `index`: patch first, then macros."""
    def host_parameter(self, index: int, value: int) -> None:
        """A host's automation moves macro `index` to `value`."""
