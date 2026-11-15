# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""songmodel's front panel page arrives with a ``mip`` install and is served from it.

A ``mip`` or ``omip`` install and a frozen build carry a package's ``.py``
files only. So the test copies just those into an empty folder, as an install
does, and serves ``GET /`` from there over hmilink's TCP listener, on CPython
and on unix MicroPython. The body has to be ``page.html`` exactly.

    python -m unittest tests.test_songmodel_page

hmilink is found as ``test_vamp.py`` finds it; ``VAMP_REQUIRE=1`` turns a
missing piece into a failure.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT / "tools"))

import songmodel_page  # noqa: E402
from test_engine import _find  # noqa: E402
from test_vamp import _hmilink  # noqa: E402

SERVE = '''
import socket, sys
from hmilink import tcp
import songmodel

listener = tcp.serve(int(sys.argv[1]), bind="127.0.0.1", page=songmodel.page())
client = socket.socket()
client.connect(socket.getaddrinfo("127.0.0.1", int(sys.argv[1]))[0][-1])
client.send(b"GET / HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n")
client.setblocking(False)
link = None
got = b""
for _ in range(2000):
    link = link or listener.accept()
    if link:
        link.recv()
    try:
        data = client.recv(4096)
    except OSError:
        data = None
    if data == b"":
        break
    if data:
        got += data
head, _, body = got.partition(b"\\r\\n\\r\\n")
print(head.split(b"\\r\\n")[0].decode())
with open(sys.argv[2], "wb") as f:
    f.write(body)
'''


def _install(target):
    """What a mip install puts in a lib folder: songmodel's .py files, nothing else."""
    package = target / "songmodel"
    package.mkdir(parents=True)
    for source in (ROOT / "lib" / "songmodel").glob("*.py"):
        shutil.copy(source, package / source.name)
    return package


class SongmodelPage(unittest.TestCase):
    def test_page_data_is_current(self):
        songmodel_page.main(["--check"])

    def test_a_mip_install_carries_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = _install(Path(tmp) / "lib")
            self.assertEqual(sorted(p.name for p in package.iterdir()),
                             ["__init__.py", "link.py", "model.py", "page_data.py"])

    def _serve(self, interpreter, port):
        hmilink = _hmilink()
        if hmilink is None or interpreter is None:
            if os.environ.get("VAMP_REQUIRE"):
                self.fail("no hmilink or no interpreter: the page was NOT served")
            self.skipTest("no hmilink or no interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "lib"
            _install(lib)
            script = Path(tmp) / "serve.py"
            script.write_text(SERVE)
            out = Path(tmp) / "body.html"
            env = dict(os.environ)
            # Only the install and hmilink are on the path: not this checkout's lib.
            path = os.pathsep.join([str(lib), hmilink])
            env["PYTHONPATH"] = env["MICROPYPATH"] = path
            run = subprocess.run([interpreter, str(script), str(port), str(out)], capture_output=True,
                                 text=True, timeout=60, env=env, cwd=tmp)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.strip(), "HTTP/1.1 200 OK")
            self.assertEqual(out.read_bytes(), (ROOT / "lib" / "songmodel" / "page.html").read_bytes())

    def test_cpython_serves_it(self):
        self._serve(sys.executable, 9561)

    def test_micropython_serves_it(self):
        self._serve(_find("PYDEVICES_MICROPYTHON", "micropython"), 9562)


if __name__ == "__main__":
    unittest.main()
