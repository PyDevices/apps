# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey with no window, no network and no sound hardware: `huey_contract.py`
passes, and each fault it knows how to plant makes it fail.

    HUEY_INTERPRETER=/path/to/micropython python -m unittest tests.test_huey

It runs twice. On MicroPython it needs the unix port built with LVGL and
svgio, named in ``HUEY_INTERPRETER``. On CPython it runs on the Python that
runs this file, which needs the desktop ``lvgl``, ``svgio`` (with resvg-py
and Pillow), ``multimer`` and pydevices. A half whose interpreter is missing
skips, unless ``HUEY_REQUIRE=1`` says both must run.

The requests the app sends are also read by a real HTTP server on this
computer, which nothing outside it can reach.
"""

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
INTERPRETER = os.getenv("HUEY_INTERPRETER")
PLANTS = (
    "deaf", "no_key", "short_wav", "forgetful", "no_act", "strict", "wrong_rate", "lost_sound",
    "odd_frames", "shut_mouth", "open_speaker", "quiet_trouble", "hot_mic", "tap_asks", "leak",
)  # fmt: skip


def _run(plant=None, cpython=False):
    env = dict(os.environ)
    env.pop("HUEY_PLANT", None)
    if plant:
        env["HUEY_PLANT"] = plant
    command = [sys.executable] if cpython else [INTERPRETER, "-X", "heapsize=32M"]
    with tempfile.TemporaryDirectory() as scratch:
        env["HUEY_SCRATCH"] = scratch
        return subprocess.run(
            command + [os.path.join(TESTS, "huey_contract.py")],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )


class _Both:
    cpython = False

    def test_the_contract_passes(self):
        done = _run(cpython=self.cpython)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok", done.stdout)
        self.assertNotIn("Traceback", done.stdout + done.stderr)

    def test_every_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                done = _run(plant, cpython=self.cpython)
                self.assertNotEqual(done.returncode, 0, "the contract passed with %s planted" % plant)
                self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)


class HueyTest(_Both, unittest.TestCase):
    def setUp(self):
        if not INTERPRETER:
            if os.getenv("HUEY_REQUIRE") == "1":
                self.fail("HUEY_INTERPRETER names no interpreter")
            self.skipTest("HUEY_INTERPRETER names no interpreter with LVGL and svgio")


def _cpython_has():
    """Why the CPython half can't run here, or None: it needs LVGL, svgio, multimer and pydevices."""
    for name in ("lvgl", "svgio", "multimer", "boarddev", "audiodev"):
        try:
            __import__(name)
        except ImportError as e:
            return "no %s for this Python: %s" % (name, e)
    return None


@unittest.skipIf(_cpython_has() and os.getenv("HUEY_REQUIRE") != "1", _cpython_has())
class HueyOnCPythonTest(_Both, unittest.TestCase):
    """The same contract on this Python, with the desktop LVGL and svgio."""

    cpython = True


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.seen.append((self.path, dict(self.headers), body))
        if self.path.endswith("/audio/speech"):
            sound = b"RIFF\xff\xff\xff\xffWAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\xc0\x5d\x00\x00\x80\xbb\x00\x00\x02\x00\x10\x00data\xff\xff\xff\xff"
            sound += bytes(range(256)) * 40
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for at in range(0, len(sound), 1500):
                piece = sound[at : at + 1500]
                self.wfile.write(b"%x\r\n" % len(piece) + piece + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            return
        if self.path.endswith("/audio/transcriptions"):
            answer = {"text": " what do you eat "}
        elif self.headers.get("Authorization") != "Bearer a-key":
            self.send_response(401)
            answer = {"error": {"message": "no such key"}}
            body = json.dumps(answer).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        else:
            answer = {"choices": [{"message": {"content": '{"say": "Crickets."}'}}]}
        body = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipIf(_cpython_has() and os.getenv("HUEY_REQUIRE") != "1", _cpython_has())
class ClientOverHTTPTest(unittest.TestCase):
    """The client's three calls, over a socket, to a server on this computer."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, ROOT)
        from apps.huey import client, settings

        cls.client_module = client
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.seen = []
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.settings = dict(settings.DEFAULTS)
        cls.settings["base_url"] = "http://127.0.0.1:%d/v1" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_a_question_goes_up_as_a_form_with_a_wav_file(self):
        client = self.client_module.Client(self.settings, "a-key")
        sound = bytes(range(200)) * 10
        self.assertEqual(client.transcribe(memoryview(sound), 16000), "what do you eat")
        path, headers, body = self.server.seen[-1]
        self.assertEqual(path, "/v1/audio/transcriptions")
        self.assertEqual(headers["Authorization"], "Bearer a-key")
        import email

        form = email.message_from_bytes(b"Content-Type: " + headers["Content-Type"].encode() + b"\r\n\r\n" + body)
        parts = {part.get_param("name", header="content-disposition"): part for part in form.get_payload()}
        self.assertEqual(parts["model"].get_payload(), self.settings["stt_model"])
        wav = parts["file"].get_payload(decode=True)
        self.assertEqual(wav[:4] + wav[8:12], b"RIFFWAVE")
        self.assertEqual(wav[44:], sound)

    def test_a_reply_comes_back_as_text(self):
        client = self.client_module.Client(self.settings, "a-key")
        self.assertEqual(client.chat([{"role": "user", "content": "what do you eat"}]), '{"say": "Crickets."}')
        sent = json.loads(self.server.seen[-1][2])
        self.assertEqual(sent["model"], self.settings["chat_model"])

    def test_a_refusal_is_an_error_that_says_why(self):
        client = self.client_module.Client(self.settings, "another-key")
        with self.assertRaises(self.client_module.ServerError) as caught:
            client.chat([{"role": "user", "content": "hello"}])
        self.assertIn("401", str(caught.exception))
        self.assertIn("no such key", str(caught.exception))
        self.assertNotIn("another-key", str(caught.exception))

    def test_speech_arrives_in_pieces_with_its_rate(self):
        client = self.client_module.Client(self.settings, "")
        speech = client.speak("Crickets.")
        self.assertEqual((speech.rate, speech.channels), (24000, 1))
        got = b""
        while True:
            piece = speech.read(4096)
            if not piece:
                break
            got += piece
        speech.close()
        self.assertEqual(got, bytes(range(256)) * 40)
        self.assertNotIn("Authorization", self.server.seen[-1][1])
