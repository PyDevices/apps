# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Spotify's limits are checked before a request leaves, with the HTTP layer stubbed out."""

import unittest

import sayso.client as client_module
from sayso import SpotifyClient, transport


class _Response:
    status_code = 200

    def __init__(self, body):
        self.content = body
        self.text = body.decode("utf-8")

    def json(self):
        import json

        return json.loads(self.content)

    def close(self):
        pass


class _Requests:
    """Stands in for `requests`: counts what would have gone to Spotify."""

    def __init__(self):
        self.sent = []

    def _send(self, method, url):
        self.sent.append((method, url))
        return _Response(b"{}")

    def get(self, url, **kwargs):
        return self._send("GET", url)

    def post(self, url, **kwargs):
        return self._send("POST", url)

    def put(self, url, **kwargs):
        return self._send("PUT", url)

    def delete(self, url, **kwargs):
        return self._send("DELETE", url)

    def request(self, method, url, **kwargs):
        return self._send(method, url)


class LimitsTest(unittest.TestCase):
    def setUp(self):
        self.original = transport.requests
        self.requests = transport.requests = _Requests()
        self.client = SpotifyClient(access_token="token", auto_set=False, local_device=object())

    def tearDown(self):
        transport.requests = self.original

    def _call(self, method, values, **kwargs):
        function = getattr(self.client, method)
        code = function.__code__
        names = code.co_varnames[1:code.co_argcount]
        if names[0] == "object_id":
            return function("playlist-id", values, **kwargs)
        return function(values, **kwargs)

    def test_every_counted_method_refuses_one_too_many_before_sending(self):
        for method, most in sorted(client_module._MOST.items()):
            with self.subTest(method=method):
                values = ["id%d" % index for index in range(most + 1)]
                with self.assertRaises(ValueError) as context:
                    self._call(method, values)
                message = str(context.exception)
                self.assertIn(method + "()", message)
                self.assertIn(str(most), message)
                self.assertIn(str(most + 1), message)
        self.assertEqual(self.requests.sent, [])

    def test_every_counted_method_sends_exactly_the_most(self):
        for method, most in sorted(client_module._MOST.items()):
            with self.subTest(method=method):
                before = len(self.requests.sent)
                self._call(method, ["id%d" % index for index in range(most)])
                self.assertEqual(len(self.requests.sent), before + 1)

    def test_a_comma_separated_string_is_counted(self):
        with self.assertRaises(ValueError):
            self.client.albums(",".join(["id"] * 21))
        self.client.albums(",".join(["id"] * 20))
        self.assertEqual(len(self.requests.sent), 1)

    def test_a_generator_is_counted_and_still_sent_whole(self):
        self.client.tracks("id%d" % index for index in range(3))
        self.assertEqual(self.requests.sent, [("GET", "https://api.spotify.com/v1/tracks?ids=id0%2Cid1%2Cid2")])

    def test_page_limit(self):
        with self.assertRaises(ValueError) as context:
            self.client.saved_tracks(limit=51)
        self.assertIn("50", str(context.exception))
        with self.assertRaises(ValueError):
            self.client.recently_played(limit=51)
        with self.assertRaises(ValueError):
            self.client.followed_artists(limit=-1)
        self.assertEqual(self.requests.sent, [])
        self.client.saved_tracks(limit=50)
        self.client.saved_tracks()
        self.assertEqual(len(self.requests.sent), 2)

    def test_recommendations_count_seeds_of_every_kind_together(self):
        with self.assertRaises(ValueError) as context:
            self.client.recommendations(seed_artists=["a", "b"], seed_genres="rock,jazz", seed_tracks=["t1", "t2"])
        self.assertIn("5 seeds", str(context.exception))
        with self.assertRaises(ValueError):
            self.client.recommendations(seed_genres="rock", limit=101)
        self.assertEqual(self.requests.sent, [])
        self.client.recommendations(seed_artists=["a", "b"], seed_genres="rock,jazz", seed_tracks=["t1"], limit=100)
        self.assertEqual(len(self.requests.sent), 1)

    def test_playlist_cover_size(self):
        with self.assertRaises(ValueError):
            self.client.set_playlist_cover_image("playlist-id", "A" * (256 * 1024 + 1))
        self.assertEqual(self.requests.sent, [])
        self.client.set_playlist_cover_image("playlist-id", "A" * (256 * 1024))
        self.assertEqual(len(self.requests.sent), 1)

    def test_each_limit_is_in_the_docstring(self):
        for method, most in sorted(client_module._MOST.items()):
            with self.subTest(method=method):
                doc = getattr(SpotifyClient, method).__doc__ or ""
                self.assertIn("at most %d " % most, doc)
                self.assertIn("Spotify's Web API", " ".join(doc.split()))


if __name__ == "__main__":
    unittest.main()
