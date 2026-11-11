# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Every relative import in the shared libraries and the apps names something
that exists. An import inside a function only fails when that function runs,
which on a board can be long after the app opened.

    python -m unittest tests.test_relative_imports
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEFT_OUT = ("__pycache__", "build", "docs", "tests")


def _exists(path):
    return os.path.isdir(path) or os.path.isfile(path + ".py")


def _bound(path):
    """The names *path* binds at its top level, besides what it imports from itself."""
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and not getattr(node, "level", 0):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _dangling(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    here = os.path.dirname(path)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        base = here
        for _ in range(node.level - 1):
            base = os.path.dirname(base)
        if node.module:
            if not _exists(os.path.join(base, *node.module.split("."))):
                found.append("%s:%d %s" % (path, node.lineno, node.module))
            continue
        bound = _bound(os.path.join(base, "__init__.py"))
        for alias in node.names:
            if not _exists(os.path.join(base, alias.name)) and alias.name not in bound:
                found.append("%s:%d %s" % (path, node.lineno, alias.name))
    return found


class RelativeImportsTest(unittest.TestCase):
    def test_every_relative_import_resolves(self):
        found = []
        for top in ("lib", "apps", "programs"):
            for path, dirs, files in os.walk(os.path.join(ROOT, top)):
                dirs[:] = [d for d in dirs if d not in _LEFT_OUT]
                for name in files:
                    if name.endswith(".py"):
                        found += _dangling(os.path.join(path, name))
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
