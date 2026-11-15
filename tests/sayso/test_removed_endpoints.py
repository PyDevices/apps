# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Methods Spotify removed for Development Mode apps say so, in their docstrings and in the coverage report."""

import os
import sys
import unittest

import sayso.client as client_module
from sayso import SpotifyClient

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "sayso"))

import endpoint_coverage  # noqa: E402

CLIENT_PATH = os.path.join(ROOT, "lib", "sayso", "client.py")

# A cut of Spotify's OpenAPI schema: enough paths to show each kind of report line.
SCHEMA = {
    "paths": {
        "/me": {"get": {"operationId": "get-current-users-profile"}},
        "/users/{user_id}": {"get": {"operationId": "get-users-profile"}},
        "/markets": {"get": {"operationId": "get-available-markets"}},
        "/playlists/{playlist_id}/tracks": {"put": {"operationId": "reorder-or-replace-playlists-tracks"}},
    }
}


class RemovedEndpointsTest(unittest.TestCase):
    def test_removed_methods_say_so_and_name_what_to_use(self):
        for method, (endpoint, replacement) in sorted(client_module._REMOVED_ENDPOINTS.items()):
            with self.subTest(method=method):
                doc = " ".join((getattr(SpotifyClient, method).__doc__ or "").split())
                self.assertIn("Removed for Development Mode apps", doc)
                self.assertIn("`%s`" % endpoint, doc)
                if replacement is None:
                    self.assertIn("no replacement", doc)
                else:
                    self.assertTrue(hasattr(SpotifyClient, replacement), replacement)
                    self.assertNotIn(replacement, client_module._REMOVED_ENDPOINTS)
                    self.assertIn("use `%s`" % replacement, doc)

    def test_the_table_names_the_endpoint_each_method_really_calls(self):
        called = {}
        for http_method, path, client_method in endpoint_coverage.extract_client_endpoints(CLIENT_PATH):
            called.setdefault(client_method, set()).add(http_method + " " + path)
        for method, (endpoint, replacement) in sorted(client_module._REMOVED_ENDPOINTS.items()):
            with self.subTest(method=method):
                self.assertEqual(called.get(method), {endpoint})

    def test_methods_that_still_work_are_not_marked(self):
        for method in ("me", "track", "playlist_items", "save_library_items", "search", "current_user_playlists"):
            self.assertNotIn(method, client_module._REMOVED_ENDPOINTS)
            self.assertNotIn("Removed for", getattr(SpotifyClient, method).__doc__ or "")

    def test_the_coverage_report_marks_removed_endpoints(self):
        removed = endpoint_coverage.removed_endpoints(CLIENT_PATH)
        self.assertEqual(removed, client_module._REMOVED_ENDPOINTS)
        report = endpoint_coverage.endpoint_coverage(
            SCHEMA, endpoint_coverage.extract_client_endpoints(CLIENT_PATH), removed
        )
        self.assertIn(("GET", "/users/{user_id}", "user", "me"), report["removed"])
        self.assertIn(("GET", "/markets", "available_markets", None), report["removed"])

        lines = endpoint_coverage.report_lines(report, show_map=True)
        self.assertIn("removed for Development Mode apps: %d" % len(removed), lines)
        self.assertIn("GET /users/{user_id} user() -> me()", lines)
        self.assertIn("GET /markets available_markets() -> no replacement", lines)
        self.assertIn(
            "PUT /playlists/{playlist_id}/tracks reorder_playlist_tracks() -> reorder_playlist_items()", lines
        )
        mapping = lines[lines.index("openapi path -> SpotifyClient method(s):") + 1:]
        self.assertEqual(
            mapping,
            [
                "GET /markets -> available_markets()  get-available-markets  [removed for Development Mode apps]",
                "GET /me -> me()  get-current-users-profile",
                "PUT /playlists/{playlist_id}/tracks -> reorder_playlist_tracks(), replace_playlist_tracks()"
                "  reorder-or-replace-playlists-tracks  [removed for Development Mode apps]",
                "GET /users/{user_id} -> user()  get-users-profile  [removed for Development Mode apps]",
            ],
        )


if __name__ == "__main__":
    unittest.main()
