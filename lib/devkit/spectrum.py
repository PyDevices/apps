# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""devkit.spectrum -- gallery's spectrum analyzer in an app's area,
sharing the panel with LVGL.

The analyzer draws straight into the panel's framebuffer, so it gets the
rows LVGL leaves alone: an app puts nothing on ``scope.root`` where the
meter is. It needs the analyzer's folder from gallery
(``lib/examples/spectrum``) on the board, in ``/lib/examples/spectrum``.
"""

import sys

FOLDERS = ("/lib/examples/spectrum", "/lib/spectrum")


def path():
    """Put the analyzer's folder on ``sys.path``; ImportError without one."""
    import os

    for folder in FOLDERS:
        try:
            os.stat(folder + "/analyzer.py")
        except OSError:
            continue
        if folder not in sys.path:
            sys.path.append(folder)
        return folder
    raise ImportError("no spectrum analyzer: copy gallery's lib/examples/spectrum to /lib/examples/spectrum")


def meter(scope, source, top, x=0, width=None, height=None, bands=None, report=False):
    """A ``Spectrum`` (not started) in *scope*'s area, from its row *top* to
    the bottom, or the rectangle *x*, *top*, *width*, *height* there."""
    path()
    from analyzer import Spectrum
    from board_config import display_drv

    rx, ry, rw, rh = scope.rect
    return Spectrum(
        display_drv,
        source,
        height=height or rh - top,
        y=ry + top,
        x=rx + x,
        width=width,
        bands=bands,
        report=report,
    )


def pump_tap(rate, channels):
    """A level source for whatever the audio pump plays (a push stream too)."""
    path()

    def source(bands):
        from pump_levels import TapLevels

        return TapLevels(bands, rate=rate, channels=channels)

    return source


def start(m, scope, above=()):
    """Start *m* on *scope*'s timer without clearing the rest of the panel.

    ``Spectrum.start`` clears the whole panel when the meter is shorter than
    it, which wipes LVGL's widgets above the meter (and LVGL doesn't know to
    redraw them). Hiding ``fill_rect`` for that one call keeps them; the meter
    paints its own rows. *above* are objects to have LVGL redraw anyway.
    """
    from . import shell

    d = m.display_drv
    d.fill_rect = None  # an instance attribute shadowing the method
    try:
        m.start(scope)
    finally:
        try:
            del d.fill_rect
        except AttributeError:
            pass
    for obj in above:
        obj.invalidate()
    shell.redraw_home_button()


def stop(m):
    if m is None:
        return
    m.stop()
    close = getattr(m.source, "close", None)
    if close is not None:
        close()
