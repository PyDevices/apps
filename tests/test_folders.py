# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""The two top-level folders keep their promises: every folder in ``apps/`` has
an ``app.json``, and every folder in ``programs/`` has a README with a
``Runs on`` line.

    python -m unittest tests.test_folders
"""

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _folders(name):
    top = os.path.join(ROOT, name)
    return sorted(
        d for d in os.listdir(top)
        if os.path.isdir(os.path.join(top, d)) and d != "__pycache__" and not d.startswith(".")
    )


class FoldersTest(unittest.TestCase):
    def test_every_app_has_an_app_json(self):
        missing = [d for d in _folders("apps") if not os.path.isfile(os.path.join(ROOT, "apps", d, "app.json"))]
        self.assertEqual(missing, [], "apps/ holds Home apps only; a program goes in programs/")

    def test_every_program_has_a_readme_with_runs_on(self):
        bad = []
        for d in _folders("programs"):
            path = os.path.join(ROOT, "programs", d, "README.md")
            if not os.path.isfile(path):
                bad.append(d + " (no README.md)")
                continue
            with open(path) as f:
                if "runs on" not in f.read().lower():
                    bad.append(d + " (no Runs on line)")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
