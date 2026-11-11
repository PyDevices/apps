# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The song both of this repo's groovebox applications edit, and what carries it
to a front panel.

- `songmodel.model`: the project, plain JSON data changed only by ops that
  every side applies the same way. Imports on CPython, Pyodide and
  MicroPython.
- `songmodel.link`: the project as an ``hmilink`` model, so any screen can
  be a front panel (needs ``hmilink``, from pydevices).
- ``page.html``: the browser front panel a device serves on its hmilink port.

Ostinato (``programs/ostinato``) and Vamp (``programs/vamp``) both use it.
"""



def page():
    """The path of ``page.html``, beside this file."""
    here = __file__
    for sep in ("/", "\\"):
        if sep in here:
            return here.rsplit(sep, 1)[0] + sep + "page.html"
    return "page.html"
