# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The song both of this repo's groovebox applications edit, and what carries it to a front panel."""

from collections.abc import Callable

def page() -> Callable[[], bytes]:
    """The front panel page, as `hmilink.tcp.serve(port, page=...)` takes it."""
