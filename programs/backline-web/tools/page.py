# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Serve Backline's web page from a checkout, or build it as a folder to host.

    python programs/backline-web/tools/page.py serve [--port 8930]
    python programs/backline-web/tools/page.py build OUT

The page needs three things beside this repository: an OmniPython checkout
(``--omnipython DIR``, ``$OMNIPYTHON_DIR``, or an ``omnipython`` folder beside
this checkout or above it) for hmilink and the icons, and MicroPython's
WebAssembly build (``--wasm DIR``, ``$BACKLINE_WASM``, or a ``bin`` folder
above this checkout holding ``micropython.mjs`` and ``micropython.wasm``),
built with LVGL, audiodsp and audioinstruments in it, as OmniPython's
release builds are.

``serve`` answers on http://localhost:PORT/; a browser on this computer may
open WebSerial and Web Bluetooth from it, since localhost counts as secure.
``build`` writes the same files to OUT, for any static host that serves
HTTPS.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent
REPO = PAGE.parent.parent
TYPES = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".py": "text/plain",
         ".json": "application/json", ".ttf": "font/ttf"}


def find_omnipython(given: str | None) -> Path:
    """The OmniPython checkout the page takes hmilink and the icons from."""
    given = given or os.environ.get("OMNIPYTHON_DIR")
    candidates = [Path(given)] if given else [p / "omnipython" for p in REPO.parents]
    for path in candidates:
        if (path / "packages" / "hmilink" / "web-page" / "hmilink.js").is_file():
            return path.resolve()
    raise SystemExit(f"no OmniPython checkout with hmilink's web page at {', '.join(map(str, candidates[:2]))}: "
                     "pass --omnipython DIR or set OMNIPYTHON_DIR")


def find_wasm(given: str | None) -> Path:
    """The folder holding MicroPython's WebAssembly build."""
    given = given or os.environ.get("BACKLINE_WASM")
    candidates = [Path(given)] if given else [p / "bin" for p in REPO.parents]
    for path in candidates:
        if (path / "micropython.mjs").is_file() and (path / "micropython.wasm").is_file():
            return path.resolve()
    raise SystemExit("no micropython.mjs and micropython.wasm found: pass --wasm DIR or set BACKLINE_WASM")


def _python(root: Path, folder: str, url: str, dest: str, suffixes=(".py",)) -> list[list[str]]:
    out = []
    base = root / folder
    for path in sorted(base.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file() or path.suffix not in suffixes:
            continue
        if path.name == "package.json":
            continue
        rel = path.relative_to(base).as_posix()
        out.append([f"{url}/{folder}/{rel}" if url else f"{folder}/{rel}", f"{dest}/{rel}"])
    return out


def files() -> list[list[str]]:
    """``[url, path]`` for every file the page puts in MicroPython's file
    system: Backline, the libraries it uses, and the page's own modules."""
    out = _python(REPO, "apps/backline", "repo", "/lib/backline", (".py", ".json"))
    out += _python(REPO, "lib/songmodel", "repo", "/lib/songmodel")
    out += _python(REPO, "lib/appkit", "repo", "/lib/appkit")
    out += _python(PAGE, "backline_web", "", "/lib/backline_web")
    for entry in out:
        if entry[1] == "/lib/backline_web/ttfio.py":
            entry[1] = "/lib/ttfio.py"     # in place of the ttfio the build hasn't got
    return out


def omnipython_files(omni: Path) -> list[list[str]]:
    """``[url, path]`` for hmilink and the icons, from the OmniPython checkout."""
    out = _python(omni, "packages/hmilink/hmilink", "omnipython", "/lib/hmilink")
    for name in ("__init__.py", "lvgl.py", "_material.py"):
        out.append([f"omnipython/packages/icons/icons/{name}", f"/lib/icons/{name}"])
    return out


def icons_font(omni: Path) -> bytes:
    """The icons font, which the page hands to the browser to draw glyphs."""
    return runpy.run_path(str(omni / "packages" / "icons" / "icons" / "_material.py"))["FONT"]


class Site:
    """Where each URL of the page comes from."""

    def __init__(self, omni: Path, wasm: Path):
        self.omni = omni
        self.wasm = wasm
        self.listing = files() + omnipython_files(omni)
        self.font = icons_font(omni)

    def source(self, url: str) -> Path | bytes | None:
        url = url.split("?", 1)[0].lstrip("/") or "index.html"
        if url == "files.json":
            return json.dumps(self.listing).encode()
        if url == "icons.ttf":
            return self.font
        if url == "hmilink/hmilink.js":
            return self.omni / "packages" / "hmilink" / "web-page" / "hmilink.js"
        for prefix, root in (("wasm/", self.wasm), ("repo/", REPO), ("omnipython/", self.omni)):
            if url.startswith(prefix):
                return _inside(root, url[len(prefix):])
        return _inside(PAGE, url)


def _inside(root: Path, rel: str) -> Path | None:
    path = (root / rel).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


def handler(site: Site):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            found = site.source(self.path)
            if found is None:
                self.send_error(404)
                return
            body = found if isinstance(found, bytes) else found.read_bytes()
            name = self.path.split("?", 1)[0]
            kind = TYPES.get(Path(name).suffix, "text/html" if name.endswith(("/", ".html")) else "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def build(site: Site, out: Path) -> None:
    """Write every file the page loads to ``out``, as the server lays them out."""
    urls = ["index.html", "page.js", "files.json", "icons.ttf", "hmilink/hmilink.js",
            "wasm/micropython.mjs", "wasm/micropython.wasm"] + [u for u, _ in site.listing]
    for url in urls:
        found = site.source(url)
        if found is None:
            raise SystemExit(f"{url}: not found")
        dest = out / url
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(found, bytes):
            dest.write_bytes(found)
        else:
            shutil.copyfile(found, dest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("what", choices=("serve", "build"))
    parser.add_argument("out", nargs="?", help="build: the folder to write")
    parser.add_argument("--port", type=int, default=8930)
    parser.add_argument("--omnipython")
    parser.add_argument("--wasm")
    args = parser.parse_args(argv)
    site = Site(find_omnipython(args.omnipython), find_wasm(args.wasm))
    if args.what == "build":
        if not args.out:
            parser.error("build needs OUT")
        build(site, Path(args.out))
        print(f"wrote the page to {args.out}")
        return
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler(site))
    print(f"Backline: http://localhost:{args.port}/  (Ctrl-C stops)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
