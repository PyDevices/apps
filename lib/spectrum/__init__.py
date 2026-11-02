# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""spectrum -- the spectrum analyzer in an app's area,
sharing the panel with LVGL.

The analyzer draws straight into the panel's framebuffer, so it gets the
rows LVGL leaves alone: an app puts nothing on ``scope.root`` where the
meter is. The analyzer's modules are in this package beside this file.
"""

def meter(scope, source, top, x=0, width=None, height=None, bands=None, report=False):
    """A ``Spectrum`` (not started) in *scope*'s area, from its row *top* to
    the bottom, or the rectangle *x*, *top*, *width*, *height* there."""
    from .analyzer import Spectrum
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

    def source(bands):
        from .pump_levels import TapLevels

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
