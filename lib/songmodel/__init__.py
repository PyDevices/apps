# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The song a groovebox edits, and the link that carries it to a front panel.

- `songmodel.model`: the project, plain JSON data changed only by ops that
  every side applies the same way. Imports on CPython, Pyodide and
  MicroPython.
- `songmodel.link`: the project as an ``hmilink`` model, so any screen can
  be a front panel (needs ``hmilink``, from omnipython).
- ``page.html``: the browser front panel a device serves on its hmilink port,
  and ``page_data``, the same page as a module (`page`); tools/songmodel_page.py
  writes the one from the other.

Both of this repo's grooveboxes, Ostinato (``programs/ostinato``) and Vamp
(``programs/vamp``), edit it.
"""



def page():
    """What ``hmilink.tcp.serve(port, page=...)`` takes to answer ``GET /``: the front panel page.

    It comes from ``page_data``, a module, so a ``mip`` install and a frozen
    build carry it with the Python.
    """
    from songmodel import page_data

    return lambda: page_data.HTML.encode()
