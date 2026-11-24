# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Read the files an app keeps beside its code, whether it's installed or frozen."""

PACKAGE: str

def read(path: str, binary: bool = False) -> str | bytes:
    """The contents of the file at `path`: text, or bytes with `binary`."""
def listdir(folder: str) -> list[str]:
    """The names in `folder`, sorted: on the filesystem, or frozen."""
