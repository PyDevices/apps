# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The song a groovebox edits, and the link that carries it to a front panel."""

from collections.abc import Callable

def page() -> Callable[[], bytes]:
    """The front panel page, as `hmilink.tcp.serve(port, page=...)` takes it."""
