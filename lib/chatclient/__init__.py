# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Ask an OpenAI-compatible server for a chat reply, whole, as it arrives, or as JSON.

`Client` makes ``chat/completions`` calls against one server: DeepInfra,
lite-assistant on your own network, or any other that speaks the same API.
`Client.chat_json` asks for a reply held to a JSON Schema where the server
can do that, plain JSON where it can only do that, and remembers what
worked. `read_key` reads an API key from a file.

    from chatclient import Client, read_key

    client = Client("http://192.0.2.10:5000/v1", read_key("/lite-assistant.key"))
    print(client.chat([{"role": "user", "content": "Hello"}], "gemma-4-E2B-it"))

Every call blocks: make it from a worker. `web` sends the requests, and a
`web.Session` keeps one connection open from one call to the next.
"""

import json

from . import web

#: What `Client.chat_json` asks for, strongest first.
FORMATS = ("json_schema", "json_object", "text")


class ServerError(Exception):
    """The server answered, and refused: its `status` and what it said.

    `status` is the HTTP status, or 0 when a streamed reply stopped with an error.
    """

    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def read_key(path):
    """The API key in the file at *path*, or ``""`` when *path* is ``""``.

    Raises:
        OSError: The file isn't there, or is empty.
    """
    if not path:
        return ""
    with open(path) as f:
        key = f.read().strip()
    if not key:
        raise OSError("%s is empty" % path)
    return key


class Chat:
    """A reply on its way: `text` so far, `more` to read the next of it, and `done` once it is all here.

    A server that sends the reply whole, not in pieces, gives a `Chat` that
    is done at once.
    """

    def __init__(self, reply):
        self._reply = reply
        self._parts = []
        self._held = b""
        self.done = False
        if "event-stream" not in reply.headers.get("content-type", ""):
            try:
                found = json.loads(reply.read_all(65536).decode())
            finally:
                self.close()
            self._parts.append(found["choices"][0]["message"]["content"] or "")

    @property
    def text(self):
        return "".join(self._parts)

    def more(self):
        """Wait for the next of the reply, and take it in."""
        if self.done:
            return
        data = self._reply.read(1024)
        if not data:
            self.close()
            return
        lines = (self._held + data).split(b"\n")
        self._held = lines.pop()
        for line in lines:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            line = line[5:].strip()
            if line == b"[DONE]":
                # all of it is here; what follows is the end of the stream
                self._reply.read_all(1024)
                self.close()
                return
            event = json.loads(line)
            if event.get("error"):
                trouble = event["error"]
                raise ServerError("the reply stopped: %s" % (trouble.get("message", trouble) if isinstance(trouble, dict) else trouble,))
            choices = event.get("choices")
            piece = choices and (choices[0].get("delta") or {}).get("content")
            if piece:
                self._parts.append(piece)

    def close(self):
        """Stop reading, whether or not all of it came."""
        self.done = True
        self._reply.close()


class Client:
    """Chat calls against one server.

    Args:
        base_url (str): The address the server's ``/chat/completions`` is
            under, such as ``https://api.deepinfra.com/v1/openai``.
        key (str): The API key, or ``""`` for a server that asks for none.
        post: What sends a request; `web.post` unless a test gives its own,
            or a `web.Session`'s to keep the connection.
        timeout (float): Seconds any one step of a call may wait.
    """

    def __init__(self, base_url, key="", post=None, timeout=60):
        self.base = base_url.rstrip("/")
        self._key = key
        self._post = post or web.post
        self.timeout = timeout
        #: What `chat_json` found the server takes: one of `FORMATS`, or None until it has asked.
        self.json_format = None

    def _send(self, path, headers, pieces, timeout, post=None):
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        reply = (post or self._post)(self.base + path, headers, pieces, timeout)
        if reply.status != 200:
            try:
                said = reply.read_all(4096).decode()
            finally:
                reply.close()
            try:
                found = json.loads(said)
                detail = found.get("error", found.get("detail", said))
                if isinstance(detail, dict):
                    detail = detail.get("message", detail)
                said = str(detail)
            except ValueError:
                pass
            raise ServerError("%d from %s: %s" % (reply.status, path, " ".join(said.split())[:160]), reply.status)
        return reply

    def _json(self, path, headers, pieces, timeout):
        reply = self._send(path, headers, pieces, timeout)
        try:
            return json.loads(reply.read_all(65536).decode())
        finally:
            reply.close()

    def body(self, messages, model, fields):
        """The request for *messages* to *model*, with *fields* (``max_tokens``, ``temperature``...) added."""
        body = {"model": model, "messages": messages}
        # lite-assistant otherwise offers the model its own tools, which
        # grows the prompt a hundredfold; other servers pass over it
        body["builtin_tools"] = False
        for name in fields:
            body[name] = fields[name]
        return body

    def chat(self, messages, model, **fields):
        """The model's reply to *messages*, as text."""
        body = self.body(messages, model, fields)
        found = self._json("/chat/completions", {"Content-Type": "application/json"}, [json.dumps(body).encode()], self.timeout)
        return found["choices"][0]["message"]["content"] or ""

    def chat_stream(self, messages, model, **fields):
        """The model's reply to *messages* as a `Chat`, to read as it arrives."""
        body = self.body(messages, model, fields)
        body["stream"] = True
        reply = self._send("/chat/completions", {"Content-Type": "application/json"}, [json.dumps(body).encode()], self.timeout)
        try:
            return Chat(reply)
        except Exception:
            reply.close()
            raise

    def chat_json(self, messages, model, schema=None, name="answer", **fields):
        """The model's reply to *messages*, asked for as JSON: the text, still to parse.

        With *schema*, a JSON Schema, the server is asked to hold the reply
        to it (``response_format`` ``json_schema``). A server that refuses
        that is asked for any JSON object, and one that refuses that too is
        asked plainly, so the messages must say what JSON to write. What
        worked is kept in `json_format` and asked for first next time.

        Raises:
            ServerError: The server refused the plain request as well.
        """
        formats = FORMATS if schema is not None else FORMATS[1:]
        if self.json_format in formats:
            formats = formats[formats.index(self.json_format):]
        refused = None
        for kind in formats:
            body = self.body(messages, model, fields)
            if kind == "json_schema":
                body["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
            elif kind == "json_object":
                body["response_format"] = {"type": "json_object"}
            try:
                found = self._json("/chat/completions", {"Content-Type": "application/json"}, [json.dumps(body).encode()], self.timeout)
            except ServerError as e:
                # 400 or 422 is the server saying it can't take this format;
                # anything else is trouble no other format gets around
                if kind == "text" or e.status not in (400, 422):
                    raise
                refused = e
                continue
            self.json_format = kind
            return found["choices"][0]["message"]["content"] or ""
        raise refused
