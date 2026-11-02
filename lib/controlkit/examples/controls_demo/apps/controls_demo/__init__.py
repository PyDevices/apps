# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The panel as an appkit app: the instrument panel over the mock adapter.

appkit calls ``main(scope)``. It needs audioinstruments on the
path, which lays out the panel from the shared controls.
"""

from audioinstruments import panel_view
from controlkit.mock import MockAdapter


def main(scope):
    """Run the panel as an appkit app, against ``mock.MockAdapter``.

    On a desktop the mouse's two wheels split the work: the main wheel moves
    between the controls and the tilt (or thumb) wheel turns the one that has
    focus. The usual mapping comes back when the app closes.
    """
    import sys

    two_wheels = False
    if getattr(sys, "platform", "") in ("linux", "darwin", "win32"):
        # Only the display_driver that opened this window: importing it here
        # would open another.
        display_driver = sys.modules.get("display_driver")
        if display_driver is not None and hasattr(display_driver, "set_wheel_mapping"):
            # Scrolling down moves to the next control; tilting right turns it up.
            display_driver.set_wheel_mapping(adjust_axis="h", adjust_sign=1, navigate=True, navigate_sign=-1)
            scope.on_close(
                lambda: display_driver.set_wheel_mapping(adjust_axis="v", adjust_sign=1, navigate=False, navigate_sign=1)
            )
            two_wheels = True

    adapter = MockAdapter()
    panel = panel_view.build(adapter, screen=scope.root, two_wheels=two_wheels)
    scope.adopt(panel)
    return panel
