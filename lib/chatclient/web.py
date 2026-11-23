# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Send an HTTP POST in pieces and read the answer as it arrives.

`post` writes the body from a list of pieces, so a recording goes up from the
buffer it was made in, and gives back a `Reply` to read a little at a time,
so speech can start playing before all of it is here. A `Session` does the
same over one connection it keeps open from one request to the next, which
saves a TLS handshake (most of a second on a board) on every call. Both
block: call them from a worker.

On MicroPython a TLS connection is encrypted but the server's certificate is
not checked, as with MicroPython's ``requests``.
"""

import socket
import time

try:
    import select
except ImportError:  # no select: a connection is only found closed by using it
    select = None

try:
    import ssl
except ImportError:  # a build without TLS still reaches a server on the local network
    ssl = None


class Reply:
    """An HTTP response: `status`, `headers` (names in lower case), and the body through `read`."""

    def __init__(self, sock, stream, session=None):
        self._sock = sock
        self._stream = stream
        self._session = session
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
        #: True when the server will take another request on this connection.
        self.keep = parts[0] == b"HTTP/1.1" and self._left is not None and "close" not in self.headers.get("connection", "").lower()

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
                # trailers, if any, and the empty line that ends the body
                while True:
                    line = self._stream.readline()
                    if not line or line in (b"\r\n", b"\n"):
                        break
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
        """Let the reply go. A session keeps the connection when all of the body was read."""
        if self._session is not None:
            session, self._session = self._session, None
            session._done(self, self._ended and self.keep)
            return
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


def _connect(secure, host, port, timeout):
    """``(timed, sock)``: what to talk to *host* through, TLS when *secure*, and what takes its timeout.

    *timed* is *sock* where it has `settimeout`, and the socket under it
    where it hasn't (MicroPython's TLS socket).
    """
    if secure and ssl is None:
        raise OSError("this Python has no TLS, which https needs")
    info = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    raw = sock = socket.socket(info[0], info[1], info[2])
    try:
        raw.settimeout(timeout)
        raw.connect(info[-1])
        if secure:
            if hasattr(ssl, "create_default_context"):
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            else:
                sock = ssl.wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise
    return (sock if hasattr(sock, "settimeout") else raw), sock


def _send(sock, host, path, headers, pieces, keep):
    send = getattr(sock, "sendall", None) or sock.write
    head = ["POST %s HTTP/1.1" % path, "Host: %s" % host, "Connection: " + ("keep-alive" if keep else "close")]
    head.append("Content-Length: %d" % sum(len(piece) for piece in pieces))
    for name in headers:
        head.append("%s: %s" % (name, headers[name]))
    send(("\r\n".join(head) + "\r\n\r\n").encode())
    for piece in pieces:
        send(piece)


def _stream(sock):
    # a desktop socket reads through a file; a board's is one already
    return sock.makefile("rb") if hasattr(sock, "makefile") else sock


def post(url, headers, pieces, timeout=30):
    """POST *pieces*, bytes or buffers sent one after another, to *url*, on a connection of its own.

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
    sock = _connect(secure, host, port, timeout)[1]
    try:
        _send(sock, host, path, headers, pieces, False)
        stream = _stream(sock)
        return Reply(sock, stream)
    except Exception:
        sock.close()
        raise


class Session:
    """Requests to one server over a connection kept open between them.

    `post` is `post`'s twin. The connection opens on the first request, or
    ahead of it with `warm`, and stays open while the server agrees. One the
    server has closed meanwhile is found closed and opened again, and a
    request that fails on an old connection is sent once more on a new one,
    so the caller sees an error only when a fresh connection fails too. One
    request at a time: read a reply to its end and close it before the next.

    Args:
        idle (float): Seconds a connection may sit unused before it is
            opened afresh rather than trusted.
    """

    def __init__(self, idle=60):
        self.idle = idle
        self._raw = None
        self._sock = None
        self._stream = None
        self._where = None
        self._used = 0
        self._busy = None
        #: Connections opened so far, and requests sent again on a new one after an old one failed.
        self.opened = 0
        self.resent = 0

    def warm(self, url, timeout=30):
        """Open a connection to *url*'s server now, if no good one is open, so the next request needn't wait for it."""
        secure, host, port, _ = split(url)
        if not self._usable((secure, host, port)):
            self._open((secure, host, port), timeout)

    def post(self, url, headers, pieces, timeout=30):
        """As `post`, on the kept connection."""
        secure, host, port, path = split(url)
        where = (secure, host, port)
        if self._busy is not None:
            # a reply not read to its end: the connection is in the middle of it
            self._busy._session = None
            self._busy = None
            self.close()
        again = self._usable(where)
        if not again:
            self._open(where, timeout)
        while True:
            try:
                self._raw.settimeout(timeout)
                _send(self._sock, host, path, headers, pieces, True)
                reply = Reply(self._sock, self._stream, self)
            except Exception:
                self.close()
                if not again:
                    raise
                # the server let an old connection go: once more, on a new one
                again = False
                self.resent += 1
                self._open(where, timeout)
                continue
            self._busy = reply
            return reply

    def _usable(self, where):
        if self._sock is None or self._where != where:
            return False
        if time.time() - self._used > self.idle or self._closed_by_server():
            self.close()
            return False
        return True

    def _closed_by_server(self):
        """True when the server has closed the connection, or sent what nobody asked for."""
        if select is None:
            return False
        try:
            poller = select.poll()
            poller.register(self._sock, select.POLLIN)
            return bool(poller.poll(0))
        except Exception:
            return False  # a socket that can't be polled is found out by using it

    def _open(self, where, timeout):
        self.close()
        self._raw, self._sock = _connect(where[0], where[1], where[2], timeout)
        self._stream = _stream(self._sock)
        self._where = where
        self._used = time.time()
        self.opened += 1

    def _done(self, reply, keep):
        if reply is not self._busy:
            return
        self._busy = None
        if keep:
            self._used = time.time()
        else:
            self.close()

    def close(self):
        """Close the connection, if one is open."""
        raw, sock, stream = self._raw, self._sock, self._stream
        self._raw = self._sock = self._stream = self._where = None
        for thing in (stream, sock, raw):
            if thing is not None:
                try:
                    thing.close()
                except Exception:
                    pass  # closed already, by the other end or the line above
