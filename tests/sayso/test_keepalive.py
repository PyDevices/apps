# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""keepalive.Session: one request at a time, and no waiting on its own thread."""

import threading
import unittest

from sayso import keepalive


class _Conn:
    sock = object()

    def open(self):
        pass

    def close(self):
        pass


class NestedRequest(unittest.TestCase):
    def test_a_request_from_a_callback_inside_a_request_raises(self):
        # A scheduled callback can run between two bytecodes of request() on
        # the same thread. It runs on a thread of its own here, so that a wait
        # on its own lock fails the test instead of stopping the run.
        session = keepalive.Session()
        session._conn = lambda host, port: _Conn()
        seen = []

        def exchange(c, req, data, got_any):
            if not seen:
                seen.append("outer")
                try:
                    session.request("GET", "https://example.com/b")
                except RuntimeError as exc:
                    seen.append(str(exc))
            return "answer"

        session._exchange = exchange
        got = []
        t = threading.Thread(target=lambda: got.append(session.request("GET", "https://example.com/a")), daemon=True)
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), "the inner request waited for its own thread")
        self.assertEqual(got, ["answer"])
        self.assertEqual(len(seen), 2, seen)
        self.assertIn("inside another request", seen[1])
        # The lock is free again.
        self.assertEqual(session.request("GET", "https://example.com/c"), "answer")


if __name__ == "__main__":
    unittest.main()
