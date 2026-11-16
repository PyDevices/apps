# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Find the folder that holds the ``iconkit`` package.

iconkit lives in the omnipython repository, at ``packages/iconkit/lib``. It is
the folder named by ``ICONKIT_LIB``, else that path in the omnipython checkout
``OMNIPYTHON_LIB`` belongs to, else in a ``omnipython`` checkout beside the apps
repo. Nothing found is an error that says how to fix it.

    python tools/iconkit_lib.py        # prints the folder
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def find():
    """The folder that holds ``iconkit/``. Raises FileNotFoundError when there is none."""
    explicit = os.environ.get("ICONKIT_LIB")
    if explicit:
        lib = pathlib.Path(explicit)
        if not (lib / "iconkit").is_dir():
            raise FileNotFoundError("ICONKIT_LIB=%s has no iconkit/ folder in it" % explicit)
        return lib
    omnipython_lib = os.environ.get("OMNIPYTHON_LIB")
    checkouts = [pathlib.Path(omnipython_lib).parent] if omnipython_lib else []
    checkouts.append(ROOT.parents[2] / "omnipython")  # the checkout beside the apps repo
    for checkout in checkouts:
        lib = checkout / "packages" / "iconkit" / "lib"
        if (lib / "iconkit").is_dir():
            return lib
    raise FileNotFoundError(
        "iconkit isn't here. Check out https://github.com/PyDevices/omnipython beside the apps repo, or set "
        "OMNIPYTHON_LIB to its lib/ folder, or ICONKIT_LIB to the folder that holds iconkit/ "
        "(packages/iconkit/lib in that checkout)."
    )


if __name__ == "__main__":
    try:
        print(find())
    except FileNotFoundError as e:
        sys.exit(str(e))
