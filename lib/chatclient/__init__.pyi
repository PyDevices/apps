# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Ask an OpenAI-compatible server for a chat reply, whole, as it arrives, or as JSON."""

from typing import Any, Callable

from . import web as web

FORMATS: tuple[str, ...]

class ServerError(Exception):
    """The server answered, and refused: its `status` and what it said."""

    status: int
    def __init__(self, message: str, status: int = 0) -> None: ...

def read_key(path: str) -> str:
    """The API key in the file at `path`, or an empty string when `path` is empty."""

class Chat:
    """A reply on its way."""

    done: bool
    def __init__(self, reply: web.Reply) -> None: ...
    @property
    def text(self) -> str: ...
    def more(self) -> None:
        """Wait for the next of the reply, and take it in."""
    def close(self) -> None:
        """Stop reading, whether or not all of it came."""

_Post = Callable[[str, dict[str, str], list[Any], float], web.Reply]

class Client:
    """Chat calls against one server."""

    base: str
    timeout: float
    json_format: str | None
    def __init__(self, base_url: str, key: str = "", post: _Post | None = None, timeout: float = 60) -> None: ...
    def body(self, messages: list[dict[str, Any]], model: str, fields: dict[str, Any]) -> dict[str, Any]:
        """The request for `messages` to `model`, with `fields` added."""
    def chat(self, messages: list[dict[str, Any]], model: str, **fields: Any) -> str:
        """The model's reply to `messages`, as text."""
    def chat_stream(self, messages: list[dict[str, Any]], model: str, **fields: Any) -> Chat:
        """The model's reply to `messages` as a `Chat`, to read as it arrives."""
    def chat_json(
        self,
        messages: list[dict[str, Any]],
        model: str,
        schema: dict[str, Any] | None = None,
        name: str = "answer",
        stream: bool = False,
        **fields: Any,
    ) -> str:
        """The model's reply to `messages`, asked for as JSON: the text, still to parse."""
