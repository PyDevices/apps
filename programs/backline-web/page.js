// SPDX-FileCopyrightText: 2026 Brad Barnett
//
// SPDX-License-Identifier: MIT

// Backline in a web page. ?role=box runs the box here (the songs, the drums
// through Web Audio, the floor view); ?role=desk runs the desk view for a
// box somewhere else. Both are Python in MicroPython's WebAssembly build,
// loaded with Backline's own modules from files.json.
//
// A board joins as the box's desk, or as the desk's box, on a port opened
// here from a click: WebSerial, Web Bluetooth, or (for a desk) a WebSocket
// to the box's desk port. The port goes on globalThis.backlinePorts, where
// the Python side picks it up.

import { openSerial, openBluetooth, Port } from "./hmilink/hmilink.js";

const q = new URLSearchParams(location.search);
const ROLE = q.get("role");
const PLANT = q.get("plant") || "";
const TICK_MS = 8;
const SIZES = { box: [800, 480], desk: [1024, 600] };
const KEYS = { " ": 0, b: 1, B: 1 };

const $ = (id) => document.getElementById(id);
globalThis.backlinePorts = [];
globalThis.backlineState = null;
globalThis.backlineReport = (text) => {
  const state = JSON.parse(text);
  globalThis.backlineState = state;
  showState(state);
};

function say(text, bad = false) {
  const line = $("status");
  line.textContent = text;
  line.classList.toggle("bad", bad);
}

// -- a WebSocket as a port: one hmilink frame per text message ------------

export class SocketPort extends Port {
  constructor(url) {
    super();
    this.url = url;
    this.ws = null;
    this._decoder = new TextDecoder();
    this._text = "";
  }

  open() {
    return new Promise((resolve, reject) => {
      const ws = (this.ws = new WebSocket(this.url));
      const encoder = new TextEncoder();
      ws.onopen = () => resolve(this);
      ws.onerror = () => reject(new Error("no box answered at " + this.url));
      ws.onclose = () => this._finish(null);
      ws.onmessage = (e) => {
        if (typeof e.data === "string") this._push(encoder.encode(e.data + "\n"));
      };
    });
  }

  async _write(bytes) {
    this._text += this._decoder.decode(bytes, { stream: true });
    let i;
    while ((i = this._text.indexOf("\n")) >= 0) {
      const line = this._text.slice(0, i);
      this._text = this._text.slice(i + 1);
      if (line) this.ws.send(line);
    }
  }

  async _teardown() {
    try { this.ws.close(); } catch (_e) { /* already closed */ }
  }
}

// -- the icons font, drawn here for ttfio's stand-in ----------------------

async function loadIcons() {
  const face = new FontFace("BacklineIcons", await (await fetch("./icons.ttf")).arrayBuffer());
  document.fonts.add(await face.load());
  const canvas = new OffscreenCanvas(8, 8);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const box = (code, size) => {
    ctx.font = `${size}px BacklineIcons`;
    const m = ctx.measureText(String.fromCodePoint(code));
    const x0 = Math.floor(-m.actualBoundingBoxLeft);
    const x1 = Math.max(x0 + 1, Math.ceil(m.actualBoundingBoxRight));
    const y0 = Math.floor(-m.actualBoundingBoxAscent);
    const y1 = Math.max(y0 + 1, Math.ceil(m.actualBoundingBoxDescent));
    return [x1 - x0, y1 - y0, x0, y0, Math.round(m.width)];
  };
  globalThis.backlineGlyph = (code, size) => box(code, size).join(",");
  globalThis.backlineRender = (code, size) => {
    const [w, h, x, y] = box(code, size);
    canvas.width = w;
    canvas.height = h;
    ctx.clearRect(0, 0, w, h);
    ctx.font = `${size}px BacklineIcons`;
    ctx.fillStyle = "#fff";
    ctx.fillText(String.fromCodePoint(code), -x, -y);
    const rgba = ctx.getImageData(0, 0, w, h).data;
    const out = new Uint8Array(w * h);
    for (let i = 0; i < out.length; i++) out[i] = rgba[i * 4 + 3];
    return out;
  };
}

// -- Python ---------------------------------------------------------------

async function loadPython() {
  const { loadMicroPython } = await import("./wasm/micropython.mjs");
  const mp = await loadMicroPython({
    heapsize: 128 * 1024 * 1024,
    stdout: (line) => console.log(line),
    stderr: (line) => console.error(line),
    linebuffer: true,
  });
  const files = await (await fetch("./files.json", { cache: "no-store" })).json();
  await Promise.all(files.map(async ([url, path]) => {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${url}: ${response.status}`);
    const data = new Uint8Array(await response.arrayBuffer());
    mp.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    mp.FS.writeFile(path, data);
  }));
  mp.runPython("import sys\nif '/lib' not in sys.path: sys.path.insert(0, '/lib')");
  return mp;
}

function run(mp, role) {
  const [w, h] = SIZES[role];
  const opts = JSON.stringify({ plant: PLANT, song: q.get("song"), kit: q.get("kit"), record: q.get("record") === "1" });
  mp.runPython(`
import json
opts = json.loads(${JSON.stringify(opts)})
if ${JSON.stringify(role)} == "box":
    from backline_web.box import Page
    page = Page("screen", (${w}, ${h}), song=opts["song"], kit=opts["kit"], plant=opts["plant"], record=opts["record"])
else:
    from backline_web.desk import Page
    page = Page("screen", (${w}, ${h}), plant=opts["plant"])

def tick():
    page.tick()

def pedal(which, down):
    page.pedal(which, down)

def key(name):
    if hasattr(page, "key"):
        page.key(name)

def notes():
    return page.notes() if hasattr(page, "notes") else "[]"
`);
  const notes = mp.globals.get("notes");
  globalThis.backlineNotes = () => notes();
  const tick = mp.globals.get("tick");
  const pedal = mp.globals.get("pedal");
  const key = mp.globals.get("key");
  globalThis.backlineKey = (name) => key(name);
  const timer = setInterval(() => {
    try {
      tick();
    } catch (e) {
      clearInterval(timer);
      say("Stopped: " + e, true);
      console.error(e);
    }
  }, TICK_MS);
  return pedal;
}

// -- the page around the canvas -------------------------------------------

function showState(s) {
  if (s.role === "box") {
    const desks = s.desks === 1 ? "1 desk" : `${s.desks} desks`;
    say(s.error || `${s.song} on ${s.kit} · ${s.playing ? s.part : "stopped"} · ${desks} joined`, Boolean(s.error));
  } else {
    say(s.ready ? `${s.song} · ${s.playing ? s.part : "stopped"}` : s.message || "choose a box to join");
  }
}

function pedals(pedal) {
  const held = new Set();
  const press = (which, down) => {
    if (down === held.has(which)) return;
    if (down) held.add(which); else held.delete(which);
    $(which ? "pad-b" : "pad-a").classList.toggle("down", down);
    pedal(which, down ? 1 : 0);
  };
  document.addEventListener("keydown", (e) => {
    // The desk's prompt sheet is open: keys type the request, not pedals.
    if (globalThis.backlineState?.typing && e.target.tagName !== "INPUT") {
      if (e.key.length === 1 || e.key === "Backspace" || e.key === "Enter") {
        e.preventDefault();
        globalThis.backlineKey(e.key);
      }
      return;
    }
    if (e.key in KEYS && !e.repeat && e.target.tagName !== "INPUT") {
      e.preventDefault();
      press(KEYS[e.key], true);
    }
  });
  document.addEventListener("keyup", (e) => {
    if (e.key in KEYS) press(KEYS[e.key], false);
  });
  for (const [id, which] of [["pad-a", 0], ["pad-b", 1]]) {
    const pad = $(id);
    pad.addEventListener("pointerdown", (e) => { pad.setPointerCapture(e.pointerId); press(which, true); });
    pad.addEventListener("pointerup", () => press(which, false));
    pad.addEventListener("pointercancel", () => press(which, false));
  }
}

function connections(role) {
  const add = (port, what) => {
    globalThis.backlinePorts.push(port);
    port.onclose = (error) => say(`${what} closed${error ? ": " + error.message : ""}`, Boolean(error));
  };
  const guard = (what, open) => async () => {
    try {
      add(await open(), what);
    } catch (e) {
      say(`${what}: ${e.message}`, true);
    }
  };
  // A test's stand-ins for the browser's ports, when one is loaded.
  const serial = globalThis.mockSerial || navigator.serial;
  const bluetooth = globalThis.mockBluetooth || navigator.bluetooth;
  $("join-usb").addEventListener("click", guard("USB", () => openSerial({ serial })));
  $("join-bt").addEventListener("click", guard("Bluetooth", () =>
    openBluetooth({ bluetooth, name: $("bt-name").value.trim() || undefined, mtu: 247 })));
  if (role === "desk") {
    $("join-ws").addEventListener("click", guard("Network", () => {
      let where = $("ws-host").value.trim() || "localhost:9300";
      if (!where.includes(":")) where += ":9300";
      return new SocketPort(`ws://${where}/ws`).open();
    }));
  }
}

async function start() {
  if (ROLE !== "box" && ROLE !== "desk") {
    document.body.classList.add("choosing");
    return;
  }
  document.body.classList.add(ROLE);
  say("Loading Python");
  try {
    const [mp] = await Promise.all([loadPython(), loadIcons()]);
    say(ROLE === "box" ? "Starting the box" : "Starting the desk");
    const pedal = run(mp, ROLE);
    pedals(pedal);
    connections(ROLE);
    document.body.classList.add("running");
  } catch (e) {
    say("Couldn't start: " + e, true);
    console.error(e);
  }
}

start();
