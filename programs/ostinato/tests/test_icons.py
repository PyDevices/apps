# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

import importlib.util
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT.parent.parent / "lib"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(ROOT / "app" / "ui"))

import iconkit  # noqa: E402


def _make_icons():
    spec = importlib.util.spec_from_file_location("ostinato_make_icons", ROOT / "scripts" / "make_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IconTests(unittest.TestCase):
    def test_every_icon_exists_at_every_size(self):
        """Shared iconkit sets and Ostinato's own modules together hold each icon
        at each size the theme draws, and iconkit.add() accepts the modules."""
        make = _make_icons()
        for size in make.SIZES:
            own = sorted(make.own_names(size))
            if own:
                module = __import__("_icons_%d" % size, None, None, ("NAMES",))
                self.assertEqual(list(module.NAMES), own)
                iconkit.add(module)
            for name in make.ICONS:
                data, w, h = iconkit.mask(name, size)
                self.assertEqual((w, h, len(data)), (size, size, size * size))
                self.assertTrue(any(data), "%s at %d px is blank" % (name, size))

    def test_missing_icon_is_an_error(self):
        with self.assertRaises(ValueError):
            iconkit.mask("not_an_icon", 24)

    def test_page_loads_iconkit_and_the_icon_modules(self):
        cfg = json.loads((ROOT / "app" / "boot_config.js").read_text().split("export default", 1)[1].rstrip().rstrip(";"))
        files = cfg["ui"]["files"]
        for src in ("lib/iconkit/__init__.py", "lib/iconkit/lvicons.py", "lib/iconkit/_a8_24.py", "lib/iconkit/_a8_48.py"):
            self.assertIn(src, files)
        for size in (18, 24, 36, 48):
            self.assertIn("app/ui/_icons_%d.py" % size, files)

    def test_no_icon_fonts_left(self):
        self.assertEqual(list((ROOT / "assets").glob("icons_*")), [])
        self.assertFalse((ROOT / "app" / "ui" / "icons.py").exists())


if __name__ == "__main__":
    unittest.main()
