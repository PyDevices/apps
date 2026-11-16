# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Send an HTTP POST in pieces and read the answer as it arrives.

`post` writes the body from a list of pieces, so a recording goes up from the
buffer it was made in, and gives back a `Reply` to read a little at a time,
so speech can start playing before all of it is here. It blocks: call it from
a worker.

On MicroPython a TLS connection is encrypted but the server's certificate is
not checked, as with MicroPython's ``requests``.
"""

import socket

try:
    import ssl
except ImportError:  # a build without TLS still reaches a server on the local network
    ssl = None


class Reply:
    """An HTTP response: `status`, `headers` (names in lower case), and the body through `read`."""

    def __init__(self, sock, stream):
        self._sock = sock
        self._stream = stream
        line = stream.readline()
        parts = line.split(None, 2)
        if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
            raise OSError("not an HTTP reply: %r" % (line[:40],))
        self.status = int(parts[1])
        self.headers = {}
        while True:
            line = stream.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            name, _, value = line.decode().partition(":")
            self.headers[name.strip().lower()] = value.strip()
        self._chunked = "chunked" in self.headers.get("transfer-encoding", "").lower()
        length = self.headers.get("content-length")
        # bytes left of the body, or of this chunk; None when the body runs to the close
        self._left = 0 if self._chunked else (int(length) if length is not None else None)
        self._ended = False

    def read(self, size):
        """Up to *size* bytes of the body, and ``b""`` once it has all been read."""
        if self._ended:
            return b""
        if self._chunked and self._left == 0:
            line = self._stream.readline()
            if line in (b"\r\n", b"\n"):  # the end of the chunk before
                line = self._stream.readline()
            self._left = int(line.split(b";")[0].strip() or b"0", 16)
            if self._left == 0:
                self._ended = True
                return b""
        if self._left is not None:
            if self._left == 0:
                self._ended = True
                return b""
            size = min(size, self._left)
        data = self._stream.read(size)
        if not data:
            self._ended = True
            if self._left:
                raise OSError("the connection closed %d bytes early" % self._left)
            return b""
        if self._left is not None:
            self._left -= len(data)
        return data

    def read_all(self, most):
        """The whole body, which must be *most* bytes or fewer.

        Raises:
            OSError: The body is longer than *most*.
        """
        parts = []
        total = 0
        while True:
            data = self.read(2048)
            if not data:
                return b"".join(parts)
            total += len(data)
            if total > most:
                raise OSError("the reply is longer than %d bytes" % most)
            parts.append(data)

    def close(self):
        for thing in (self._stream, self._sock):
            try:
                thing.close()
            except Exception:
                pass  # closed already, by the other end or the line above


def split(url):
    """``(secure, host, port, path)`` of an http or https *url*."""
    scheme, _, rest = url.partition("://")
    if scheme not in ("http", "https"):
        raise ValueError("not an http or https address: %r" % (url,))
    host, slash, path = rest.partition("/")
    port = 443 if scheme == "https" else 80
    if ":" in host:
        host, _, number = host.partition(":")
        port = int(number)
    return scheme == "https", host, port, slash + path if slash else "/"


def post(url, headers, pieces, timeout=30):
    """POST *pieces*, bytes or buffers sent one after another, to *url*.

    Args:
        url (str): An http or https address.
        headers (dict): Request headers; Host, Content-Length and Connection are added.
        pieces (list): The body.
        timeout (float): Seconds any one step may wait.

    Returns:
        A `Reply`, whatever its status. Close it when done.

    Raises:
        OSError: No connection, or no answer in time.
    """
    secure, host, port, path = split(url)
    if secure and ssl is None:
        raise OSError("this Python has no TLS, which %s needs" % (url,))
    info = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    sock = socket.socket(info[0], info[1], info[2])
    try:
        sock.settimeout(timeout)
        sock.connect(info[-1])
        if secure:
            if hasattr(ssl, "create_default_context"):
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            else:
                sock = ssl.wrap_socket(sock, server_hostname=host)
        send = getattr(sock, "sendall", None) or sock.write
        head = ["POST %s HTTP/1.1" % path, "Host: %s" % host, "Connection: close"]
        head.append("Content-Length: %d" % sum(len(piece) for piece in pieces))
        for name in headers:
            head.append("%s: %s" % (name, headers[name]))
        send(("\r\n".join(head) + "\r\n\r\n").encode())
        for piece in pieces:
            send(piece)
        # a desktop socket reads through a file; a board's is one already
        stream = sock.makefile("rb") if hasattr(sock, "makefile") else sock
        return Reply(sock, stream)
    except Exception:
        sock.close()
        raise
