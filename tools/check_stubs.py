#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Check the type stubs under lib/ against each other and against the code.

From the repository root:

    python tools/check_stubs.py              # every stub
    python tools/check_stubs.py events keys  # mypy over all, stubtest on these

First it copies every `.pyi` into a scratch folder, which is how a wheel carries
them, and runs mypy over the copy, so a stub that doesn't parse or contradicts
itself fails. Then it runs mypy's `stubtest` on each module in
`tools/stubs/stubtest.txt`: it imports the module under CPython and fails when
the stub and the code disagree about a name or a signature.

The two lists, `tools/stubs/stubtest.txt` and `tools/stubs/mypy-only.txt`, must
between them name every module that has a stub. A module whose import fails or
blocks under CPython (a platform backend) goes in `mypy-only.txt`. Each stubtest
run is its own process with a hard timeout, because one blocked import once hung
a whole-package run.

`tools/stubs/allowlist.txt` holds stubtest's accepted differences, one regular
expression a line.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib"
LISTS = ROOT / "tools" / "stubs"
TIMEOUT = 120  # seconds, per module


def read_list(name):
    path = LISTS / name
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line]


def stub_modules():
    """Dotted names of every module under lib/ that has a stub."""
    names = []
    for path in sorted(LIB.rglob("*.pyi")):
        parts = list(path.relative_to(LIB).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        names.append(".".join(parts))
    return names


def stage(destination):
    for path in LIB.rglob("*.pyi"):
        target = destination / path.relative_to(LIB)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def run(command, env=None):
    try:
        return subprocess.run(command, env=env, timeout=TIMEOUT + 30, check=False).returncode
    except subprocess.TimeoutExpired:
        print("timed out: " + " ".join(command))
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("modules", nargs="*", help="run stubtest on these modules only")
    args = parser.parse_args()

    listed = read_list("stubtest.txt")
    mypy_only = read_list("mypy-only.txt")
    status = 0
    known = set(listed) | set(mypy_only)
    for name in stub_modules():
        if name not in known:
            print("%s has a stub but is in neither tools/stubs/stubtest.txt nor mypy-only.txt" % name)
            status = 1
    for name in sorted(known - set(stub_modules())):
        print("%s is listed in tools/stubs but has no stub" % name)
        status = 1

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        stage(scratch)
        files = sorted(str(path) for path in scratch.rglob("*.pyi"))
        print("== mypy over %d stubs" % len(files))
        status |= run([sys.executable, "-m", "mypy", "--no-incremental", "--no-site-packages", *files])

        env = dict(os.environ, MYPYPATH=str(scratch), PYTHONPATH=str(LIB))
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("SDL_AUDIODRIVER", "dummy")
        allowlist = LISTS / "allowlist.txt"
        for name in args.modules or listed:
            print("== stubtest %s" % name)
            command = ["timeout", "-s", "KILL", str(TIMEOUT), sys.executable, "-m", "mypy.stubtest"]
            command += ["--allowlist", str(allowlist), "--ignore-unused-allowlist", name]
            status |= run(command, env)
    return status


if __name__ == "__main__":
    sys.exit(main())
