# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's hostkeys: `hostkeys_contract.py` on CPython and MicroPython,
and each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_hostkeys.py

It runs omnipython's real ``usb.core``, ``usb.host.endpoints`` and
``usb.host.hid``, from ``$OMNIPYTHON_DIR`` or the checkout ``OMNIPYTHON_LIB``
belongs to, and endpointkit from the same checkout. Without them, or without
LVGL on the interpreter, it skips.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from _harness import OMNIPYTHON_LIB, TESTS, need_micropython, run

CONTRACT = TESTS / "hostkeys_contract.py"
PLANTS = ("drops_keys", "keyboard_stays", "always_reading", "ignores_choice", "unplug_raises", "stall_swallowed",
          "replug_missed", "s3_takes_the_port", "never_looks")


def _omnipython():
    explicit = os.environ.get("OMNIPYTHON_DIR")
    if explicit:
        return Path(explicit)
    return OMNIPYTHON_LIB.parent if OMNIPYTHON_LIB is not None else None


# usb.core and usb.host.* live in packages that each hold a usb/ folder, and
# MicroPython has no namespace packages: one tree holds the three modules.
_PARTS = (("usb-core", "usb/core.py"), ("usb-core", "usb/util.py"), ("usb-host-endpoints", "usb/host/endpoints.py"),
          ("usb-host-hid", "usb/host/hid.py"))


def setUpModule():
    global _tree, _env
    omni = _omnipython()
    usb = omni / "packages" / "usb" if omni else None
    if usb is None or not all((usb / pkg / path).is_file() for pkg, path in _PARTS):
        raise unittest.SkipTest("no omnipython checkout with packages/usb: set OMNIPYTHON_DIR")
    _tree = tempfile.TemporaryDirectory()
    for pkg, path in _PARTS:
        dst = Path(_tree.name) / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(usb / pkg / path, dst)
    _env = {"HOSTKEYS_USB_TREE": _tree.name, "HOSTKEYS_ENDPOINTKIT": str(omni / "packages" / "endpointkit")}


def tearDownModule():
    _tree.cleanup()


def _run(case, interpreter, plant=None):
    extra = dict(_env)
    if plant:
        extra["HOSTKEYS_PLANT"] = plant
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class HostKeysCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class HostKeysMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [need_micropython(self), "-X", "heapsize=16M"], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
