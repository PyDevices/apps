# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

from .auth import ClientCredentialsAuth
from .objects import (
    Album,
    AlbumPage,
    Artist,
    ArtistCursorPage,
    ArtistPage,
    AudioAnalysis,
    AudioFeatures,
    Audiobook,
    AudiobookPage,
    Category,
    CategoryPage,
    Chapter,
    ChapterPage,
    CurrentlyPlaying,
    Device,
    Episode,
    EpisodePage,
    FeaturedPlaylists,
    Image,
    Playlist,
    PlaylistPage,
    PlaylistTrackPage,
    PlayHistoryCursorPage,
    PrivateUser,
    Queue,
    Recommendations,
    SavedAlbumPage,
    SavedEpisodePage,
    SavedShowPage,
    SavedTrackPage,
    SearchResults,
    Show,
    SnapshotResult,
    TrackPage,
    Track,
    User,
    set_client,
)
from .transport import (
    API_BASE_URL,
    TransportError,
    build_url,
    delete_json,
    get_json,
    post_json,
    put_body,
    put_json,
)
from .local import EarfulAdapter, discover as discover_local

# The most IDs or URIs one request takes, by client method, from the parameter
# descriptions in Spotify's Web API reference
# (https://developer.spotify.com/documentation/web-api/reference).
_MOST = {
    "tracks": 50,
    "albums": 20,
    "artists": 50,
    "episodes": 50,
    "shows": 50,
    "audiobooks": 50,
    "chapters": 50,
    "audio_features_many": 100,
    "add_playlist_items": 100,
    "add_playlist_tracks": 100,
    "remove_playlist_items": 100,
    "remove_playlist_tracks": 100,
    "replace_playlist_items": 100,
    "replace_playlist_tracks": 100,
    "contains_saved_albums": 20,
    "save_albums": 50,
    "remove_saved_albums": 50,
    "contains_saved_tracks": 50,
    "save_tracks": 50,
    "remove_saved_tracks": 50,
    "contains_saved_episodes": 50,
    "save_episodes": 50,
    "remove_saved_episodes": 50,
    "contains_saved_shows": 50,
    "save_shows": 50,
    "remove_saved_shows": 50,
    "contains_saved_audiobooks": 50,
    "save_audiobooks": 50,
    "remove_saved_audiobooks": 50,
    "library_contains": 40,
    "save_library_items": 40,
    "remove_library_items": 40,
    "follows_artists": 50,
    "follows_users": 50,
    "follow_artists": 50,
    "follow_users": 50,
    "unfollow_artists": 50,
    "unfollow_users": 50,
}

# The most seeds `recommendations` takes, artists, genres and tracks together.
_MOST_SEEDS = 5

# The largest playlist cover Spotify accepts, as Base64 text.
_MOST_COVER_BYTES = 256 * 1024

# Client methods whose endpoint Spotify removed for Development Mode apps, with
# the method to use instead, or None where there is none. From the February 2026
# migration guide
# (https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).
# Apps in Extended Quota Mode still have every one of them.
_REMOVED_ENDPOINTS = {
    "tracks": ("GET /tracks", "track"),
    "albums": ("GET /albums", "album"),
    "artists": ("GET /artists", "artist"),
    "episodes": ("GET /episodes", "episode"),
    "shows": ("GET /shows", "show"),
    "audiobooks": ("GET /audiobooks", "audiobook"),
    "chapters": ("GET /chapters", "chapter"),
    "artist_top_tracks": ("GET /artists/{id}/top-tracks", None),
    "create_playlist": ("POST /users/{user_id}/playlists", "create_current_user_playlist"),
    "playlist_tracks": ("GET /playlists/{playlist_id}/tracks", "playlist_items"),
    "add_playlist_tracks": ("POST /playlists/{playlist_id}/tracks", "add_playlist_items"),
    "remove_playlist_tracks": ("DELETE /playlists/{playlist_id}/tracks", "remove_playlist_items"),
    "replace_playlist_tracks": ("PUT /playlists/{playlist_id}/tracks", "replace_playlist_items"),
    "reorder_playlist_tracks": ("PUT /playlists/{playlist_id}/tracks", "reorder_playlist_items"),
    "follow_playlist": ("PUT /playlists/{playlist_id}/followers", "save_library_items"),
    "unfollow_playlist": ("DELETE /playlists/{playlist_id}/followers", "remove_library_items"),
    "playlist_followers_contains": ("GET /playlists/{playlist_id}/followers/contains", "library_contains"),
    "category": ("GET /browse/categories/{category_id}", None),
    "categories": ("GET /browse/categories", None),
    "new_releases": ("GET /browse/new-releases", None),
    "user": ("GET /users/{user_id}", "me"),
    "user_playlists": ("GET /users/{user_id}/playlists", "current_user_playlists"),
    "contains_saved_albums": ("GET /me/albums/contains", "library_contains"),
    "save_albums": ("PUT /me/albums", "save_library_items"),
    "remove_saved_albums": ("DELETE /me/albums", "remove_library_items"),
    "contains_saved_tracks": ("GET /me/tracks/contains", "library_contains"),
    "save_tracks": ("PUT /me/tracks", "save_library_items"),
    "remove_saved_tracks": ("DELETE /me/tracks", "remove_library_items"),
    "contains_saved_episodes": ("GET /me/episodes/contains", "library_contains"),
    "save_episodes": ("PUT /me/episodes", "save_library_items"),
    "remove_saved_episodes": ("DELETE /me/episodes", "remove_library_items"),
    "contains_saved_shows": ("GET /me/shows/contains", "library_contains"),
    "save_shows": ("PUT /me/shows", "save_library_items"),
    "remove_saved_shows": ("DELETE /me/shows", "remove_library_items"),
    "contains_saved_audiobooks": ("GET /me/audiobooks/contains", "library_contains"),
    "save_audiobooks": ("PUT /me/audiobooks", "save_library_items"),
    "remove_saved_audiobooks": ("DELETE /me/audiobooks", "remove_library_items"),
    "follows_artists": ("GET /me/following/contains", "library_contains"),
    "follow_artists": ("PUT /me/following", "save_library_items"),
    "unfollow_artists": ("DELETE /me/following", "remove_library_items"),
    "follows_users": ("GET /me/following/contains", "library_contains"),
    "follow_users": ("PUT /me/following", "save_library_items"),
    "unfollow_users": ("DELETE /me/following", "remove_library_items"),
    "available_markets": ("GET /markets", None),
}


class SpotifyClientError(Exception):
    pass


class SpotifyClient:
    API_BASE_URL = API_BASE_URL

    def __init__(
        self,
        access_token=None,
        client_id=None,
        client_secret=None,
        auth=None,
        auto_set=True,
        config_path=None,
        scope=None,
        authenticate_if_needed=True,
        auth_state="sayso",
        local_device=None,
    ):
        self.access_token = access_token
        self.auth = auth
        self.local = local_device if isinstance(local_device, EarfulAdapter) else (
            EarfulAdapter(local_device) if local_device is not None else discover_local()
        )

        if self.auth is None and access_token is None:
            if client_id is not None and client_secret is not None:
                self.auth = ClientCredentialsAuth(client_id, client_secret)
            else:
                from .auth import auth_from_config

                self.auth = auth_from_config(
                    config_path=config_path,
                    scope=scope,
                    authenticate_if_needed=authenticate_if_needed,
                    auth_state=auth_state,
                )

        if auto_set:
            set_client(self)

    def _get_json(self, path, query=None):
        def request(token):
            return get_json(path, access_token=token, query=query)

        return self._request_with_retry(request)

    def _put_json(self, path, data=None, query=None):
        return self._request_json(put_json, path, data=data, query=query)

    def _put_body(self, path, body, content_type, query=None):
        def request(token):
            return put_body(path, body, content_type, access_token=token, query=query)

        return self._request_with_retry(request)

    def _post_json(self, path, data=None, query=None):
        return self._request_json(post_json, path, data=data, query=query)

    def _delete_json(self, path, data=None, query=None):
        return self._request_json(delete_json, path, data=data, query=query)

    def _url(self, path, query=None):
        return build_url(path, query=query, base_url=self.API_BASE_URL)

    def _request_json(self, request, path, data=None, query=None):
        def do_request(token):
            return request(path, data=data, access_token=token, query=query)

        return self._request_with_retry(do_request)

    def _request_with_retry(self, request):
        token = self._access_token()
        if token is None:
            raise SpotifyClientError("An access_token is required for Spotify Web API requests")

        try:
            return request(token)
        except TransportError as error:
            if error.status != 401 or self.auth is None:
                raise

            self.auth.refresh()
            if self.access_token is not None and self.auth.access_token is not None:
                self.access_token = self.auth.access_token

            token = self._access_token()
            if token is None:
                raise SpotifyClientError("An access_token is required for Spotify Web API requests")

            return request(token)

    def _access_token(self):
        if self.access_token is not None:
            return self.access_token
        if self.auth is not None:
            return self.auth.token()
        return None

    def _local(self, device_id=None):
        if self.local is None:
            return None
        if device_id is None or device_id == self.local.device_id or device_id == self.local.name:
            return self.local
        return None

    def _one(self, cls, path, query=None):
        return cls(self._get_json(path, query=query))

    def _many(self, cls, field, path, ids, query=None):
        query = self._query_with_ids(ids, query=query)
        data = self._get_json(path, query=query)
        values = data.get(field, ())
        return [cls(item) for item in values]

    def _page(self, cls, path, query=None):
        return cls(self._get_json(path, query=query))

    def _page_url(self, page_url, page_class):
        if page_url is None:
            return None
        return page_class(self._get_json(page_url))

    def next_page(self, page):
        return self._page_url(page.next, page.__class__)

    def previous_page(self, page):
        return self._page_url(page.previous, page.__class__)

    def _path_id(self, value):
        return str(value)

    def _most(self, method, values):
        """`values`, as a string or a list, once it fits what `method` takes in one request."""
        if isinstance(values, str):
            count = values.count(",") + 1
        else:
            values = list(values)
            count = len(values)
        most = _MOST[method]
        if count > most:
            raise ValueError("%s() takes at most %d items in one request, and got %d" % (method, most, count))
        return values

    def _limit(self, limit, most=50):
        """A page `limit`, once it is within what Spotify's Web API reference allows."""
        if isinstance(limit, int) and not 0 <= limit <= most:
            raise ValueError("limit must be from 0 to %d, and got %d" % (most, limit))
        return limit

    def track(self, object_id, market=None):
        return self._one(Track, "/tracks/" + self._path_id(object_id), self._market_query(market))

    def tracks(self, ids, market=None):
        """Several tracks by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /tracks`): use `track`, once per ID.
        """
        return self._many(Track, "tracks", "/tracks", self._most("tracks", ids), self._market_query(market))

    def album(self, object_id, market=None):
        return self._one(Album, "/albums/" + self._path_id(object_id), self._market_query(market))

    def albums(self, ids, market=None):
        """Several albums by ID.

        Takes at most 20 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /albums`): use `album`, once per ID.
        """
        return self._many(Album, "albums", "/albums", self._most("albums", ids), self._market_query(market))

    def album_tracks(self, object_id, market=None, limit=None, offset=None):
        query = self._page_query(market=market, limit=limit, offset=offset)
        return self._page(TrackPage, "/albums/" + self._path_id(object_id) + "/tracks", query)

    def artist(self, object_id):
        return self._one(Artist, "/artists/" + self._path_id(object_id))

    def artists(self, ids):
        """Several artists by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /artists`): use `artist`, once per ID.
        """
        return self._many(Artist, "artists", "/artists", self._most("artists", ids))

    def artist_albums(self, object_id, include_groups=None, market=None, limit=None, offset=None):
        query = self._page_query(market=market, limit=limit, offset=offset)
        self._add_query(query, "include_groups", include_groups)
        return self._page(AlbumPage, "/artists/" + self._path_id(object_id) + "/albums", query)

    def artist_top_tracks(self, object_id, market=None):
        """An artist's top tracks.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /artists/{id}/top-tracks`), with no replacement.
        """
        data = self._get_json("/artists/" + self._path_id(object_id) + "/top-tracks", self._market_query(market))
        tracks = data.get("tracks")
        if tracks is None:
            return ()
        return [Track(item) for item in tracks]

    def artist_related_artists(self, object_id):
        data = self._get_json("/artists/" + self._path_id(object_id) + "/related-artists")
        artists = data.get("artists")
        if artists is None:
            return ()
        return [Artist(item) for item in artists]

    def playlist(self, object_id, market=None, fields=None, additional_types=None):
        query = {}
        self._add_query(query, "market", market)
        self._add_query(query, "fields", fields)
        self._add_query(query, "additional_types", additional_types)
        return self._one(Playlist, "/playlists/" + self._path_id(object_id), query)

    def create_playlist(self, user_id, name, public=None, collaborative=None, description=None):
        """Create a playlist for a user, by user ID.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`POST /users/{user_id}/playlists`): use `create_current_user_playlist`.
        """
        data = {"name": name}
        self._add_query(data, "public", public)
        self._add_query(data, "collaborative", collaborative)
        self._add_query(data, "description", description)
        return Playlist(self._post_json("/users/" + self._path_id(user_id) + "/playlists", data=data))

    def create_current_user_playlist(self, name, public=None, collaborative=None, description=None):
        data = {"name": name}
        self._add_query(data, "public", public)
        self._add_query(data, "collaborative", collaborative)
        self._add_query(data, "description", description)
        return Playlist(self._post_json("/me/playlists", data=data))

    def update_playlist_details(self, object_id, name=None, public=None, collaborative=None, description=None):
        data = {}
        self._add_query(data, "name", name)
        self._add_query(data, "public", public)
        self._add_query(data, "collaborative", collaborative)
        self._add_query(data, "description", description)
        return self._put_json("/playlists/" + self._path_id(object_id), data=data)

    def playlist_items(self, object_id, market=None, fields=None, limit=None, offset=None, additional_types=None):
        query = self._page_query(market=market, limit=limit, offset=offset)
        self._add_query(query, "fields", fields)
        self._add_query(query, "additional_types", additional_types)
        return self._page(PlaylistTrackPage, "/playlists/" + self._path_id(object_id) + "/items", query)

    def playlist_tracks(self, object_id, market=None, fields=None, limit=None, offset=None, additional_types=None):
        """A page of a playlist's entries, from the old `/tracks` path.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /playlists/{playlist_id}/tracks`): use `playlist_items`.
        """
        query = self._page_query(market=market, limit=limit, offset=offset)
        self._add_query(query, "fields", fields)
        self._add_query(query, "additional_types", additional_types)
        return self._page(PlaylistTrackPage, "/playlists/" + self._path_id(object_id) + "/tracks", query)

    def add_playlist_items(self, object_id, uris, position=None):
        """Add tracks or episodes to a playlist.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        data = {"uris": self._uri_list(self._most("add_playlist_items", uris))}
        self._add_query(data, "position", position)
        return self._snapshot(self._post_json("/playlists/" + self._path_id(object_id) + "/items", data=data))

    def add_playlist_tracks(self, object_id, uris, position=None):
        """Add tracks or episodes to a playlist, through the old `/tracks` path.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`POST /playlists/{playlist_id}/tracks`): use `add_playlist_items`.
        """
        data = {"uris": self._uri_list(self._most("add_playlist_tracks", uris))}
        self._add_query(data, "position", position)
        return self._snapshot(self._post_json("/playlists/" + self._path_id(object_id) + "/tracks", data=data))

    def remove_playlist_items(self, object_id, uris, snapshot_id=None):
        """Remove tracks or episodes from a playlist.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        data = {
            "items": [{"uri": uri} for uri in self._uri_list(self._most("remove_playlist_items", uris))],
        }
        self._add_query(data, "snapshot_id", snapshot_id)
        return self._snapshot(self._delete_json("/playlists/" + self._path_id(object_id) + "/items", data=data))

    def remove_playlist_tracks(self, object_id, uris, snapshot_id=None):
        """Remove tracks or episodes from a playlist, through the old `/tracks` path.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /playlists/{playlist_id}/tracks`): use `remove_playlist_items`.
        """
        data = {
            "tracks": [{"uri": uri} for uri in self._uri_list(self._most("remove_playlist_tracks", uris))],
        }
        self._add_query(data, "snapshot_id", snapshot_id)
        return self._snapshot(self._delete_json("/playlists/" + self._path_id(object_id) + "/tracks", data=data))

    def replace_playlist_items(self, object_id, uris):
        """Replace everything in a playlist.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        return self._snapshot(
            self._put_json(
                "/playlists/" + self._path_id(object_id) + "/items",
                data={"uris": self._uri_list(self._most("replace_playlist_items", uris))},
            )
        )

    def replace_playlist_tracks(self, object_id, uris):
        """Replace everything in a playlist, through the old `/tracks` path.

        Takes at most 100 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /playlists/{playlist_id}/tracks`): use `replace_playlist_items`.
        """
        return self._snapshot(
            self._put_json(
                "/playlists/" + self._path_id(object_id) + "/tracks",
                data={"uris": self._uri_list(self._most("replace_playlist_tracks", uris))},
            )
        )

    def reorder_playlist_items(self, object_id, range_start, insert_before, range_length=None, snapshot_id=None):
        data = {
            "range_start": range_start,
            "insert_before": insert_before,
        }
        self._add_query(data, "range_length", range_length)
        self._add_query(data, "snapshot_id", snapshot_id)
        return self._snapshot(self._put_json("/playlists/" + self._path_id(object_id) + "/items", data=data))

    def reorder_playlist_tracks(self, object_id, range_start, insert_before, range_length=None, snapshot_id=None):
        """Move a run of a playlist's entries, through the old `/tracks` path.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /playlists/{playlist_id}/tracks`): use `reorder_playlist_items`.
        """
        data = {
            "range_start": range_start,
            "insert_before": insert_before,
        }
        self._add_query(data, "range_length", range_length)
        self._add_query(data, "snapshot_id", snapshot_id)
        return self._snapshot(self._put_json("/playlists/" + self._path_id(object_id) + "/tracks", data=data))

    def follow_playlist(self, object_id, public=None):
        """Follow a playlist.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /playlists/{playlist_id}/followers`): use `save_library_items`.
        """
        data = {}
        self._add_query(data, "public", public)
        return self._put_json("/playlists/" + self._path_id(object_id) + "/followers", data=data)

    def unfollow_playlist(self, object_id):
        """Stop following a playlist.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /playlists/{playlist_id}/followers`): use `remove_library_items`.
        """
        return self._delete_json("/playlists/" + self._path_id(object_id) + "/followers")

    def playlist_followers_contains(self, object_id, ids):
        """Whether each user follows a playlist.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /playlists/{playlist_id}/followers/contains`): use `library_contains`.
        """
        return self._bools("/playlists/" + self._path_id(object_id) + "/followers/contains", ids)

    def episode(self, object_id, market=None):
        return self._one(Episode, "/episodes/" + self._path_id(object_id), self._market_query(market))

    def episodes(self, ids, market=None):
        """Several episodes by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /episodes`): use `episode`, once per ID.
        """
        return self._many(Episode, "episodes", "/episodes", self._most("episodes", ids), self._market_query(market))

    def show(self, object_id, market=None):
        return self._one(Show, "/shows/" + self._path_id(object_id), self._market_query(market))

    def shows(self, ids, market=None):
        """Several shows by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /shows`): use `show`, once per ID.
        """
        return self._many(Show, "shows", "/shows", self._most("shows", ids), self._market_query(market))

    def show_episodes(self, object_id, market=None, limit=None, offset=None):
        query = self._page_query(market=market, limit=limit, offset=offset)
        return self._page(EpisodePage, "/shows/" + self._path_id(object_id) + "/episodes", query)

    def audiobook(self, object_id, market=None):
        return self._one(Audiobook, "/audiobooks/" + self._path_id(object_id), self._market_query(market))

    def audiobooks(self, ids, market=None):
        """Several audiobooks by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /audiobooks`): use `audiobook`, once per ID.
        """
        return self._many(Audiobook, "audiobooks", "/audiobooks", self._most("audiobooks", ids), self._market_query(market))

    def audiobook_chapters(self, object_id, market=None, limit=None, offset=None):
        query = self._page_query(market=market, limit=limit, offset=offset)
        return self._page(ChapterPage, "/audiobooks/" + self._path_id(object_id) + "/chapters", query)

    def chapter(self, object_id, market=None):
        return self._one(Chapter, "/chapters/" + self._path_id(object_id), self._market_query(market))

    def chapters(self, ids, market=None):
        """Several chapters by ID.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /chapters`): use `chapter`, once per ID.
        """
        return self._many(Chapter, "chapters", "/chapters", self._most("chapters", ids), self._market_query(market))

    def audio_features(self, object_id):
        return self._one(AudioFeatures, "/audio-features/" + self._path_id(object_id))

    def audio_features_many(self, ids):
        """Audio features for several tracks.

        Takes at most 100 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        return self._many(AudioFeatures, "audio_features", "/audio-features", self._most("audio_features_many", ids))

    def audio_analysis(self, object_id):
        return self._one(AudioAnalysis, "/audio-analysis/" + self._path_id(object_id))

    def recommendations(self, seed_artists=None, seed_genres=None, seed_tracks=None, limit=None, market=None, **kwargs):
        """Tracks recommended from seed artists, genres and tracks.

        Takes at most 5 seeds in one request, counting all three kinds together,
        and a `limit` up to 100, the maximums in Spotify's Web API reference. More
        raises `ValueError` before anything is sent.
        """
        seeds = [self._join_optional(seed_artists), self._join_optional(seed_genres), self._join_optional(seed_tracks)]
        count = sum(seed.count(",") + 1 for seed in seeds if seed)
        if count > _MOST_SEEDS:
            raise ValueError("recommendations() takes at most %d seeds in one request, and got %d" % (_MOST_SEEDS, count))
        query = {}
        self._add_query(query, "seed_artists", seeds[0])
        self._add_query(query, "seed_genres", seeds[1])
        self._add_query(query, "seed_tracks", seeds[2])
        self._add_query(query, "limit", self._limit(limit, 100))
        self._add_query(query, "market", market)

        for key in kwargs:
            self._add_query(query, key, kwargs[key])

        return self._one(Recommendations, "/recommendations", query)

    def category(self, object_id, country=None, locale=None):
        """One browse category.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /browse/categories/{category_id}`), with no replacement.
        """
        query = {}
        self._add_query(query, "country", country)
        self._add_query(query, "locale", locale)
        return self._one(Category, "/browse/categories/" + self._path_id(object_id), query)

    def categories(self, country=None, locale=None, limit=None, offset=None):
        """A page of browse categories.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /browse/categories`), with no replacement.
        """
        query = self._page_query(limit=limit, offset=offset)
        self._add_query(query, "country", country)
        self._add_query(query, "locale", locale)
        data = self._get_json("/browse/categories", query=query)
        return CategoryPage(data.get("categories", data))

    def category_playlists(self, category_id, limit=None, offset=None):
        query = self._page_query(limit=limit, offset=offset)
        data = self._get_json("/browse/categories/" + self._path_id(category_id) + "/playlists", query=query)
        return PlaylistPage(data.get("playlists", data))

    def featured_playlists(self, country=None, locale=None, timestamp=None, limit=None, offset=None):
        query = self._page_query(limit=limit, offset=offset)
        self._add_query(query, "country", country)
        self._add_query(query, "locale", locale)
        self._add_query(query, "timestamp", timestamp)
        return self._one(FeaturedPlaylists, "/browse/featured-playlists", query)

    def new_releases(self, country=None, limit=None, offset=None):
        """A page of new album releases.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /browse/new-releases`), with no replacement.
        """
        query = self._page_query(limit=limit, offset=offset)
        self._add_query(query, "country", country)
        data = self._get_json("/browse/new-releases", query=query)
        return AlbumPage(data.get("albums", data))

    def search(self, q, item_types, market=None, limit=None, offset=None, include_external=None):
        """Search the catalogue for albums, artists, playlists, tracks, shows, episodes or audiobooks.

        Spotify's February 2026 changes cut the largest `limit` from 50 to 10 for
        Development Mode apps. Page with `offset` to read more.
        """
        query = self._page_query(market=market, limit=limit, offset=offset)
        self._add_query(query, "q", q)
        self._add_query(query, "type", self._join_ids(item_types))
        self._add_query(query, "include_external", include_external)
        return self._one(SearchResults, "/search", query)

    def me(self):
        return self._one(PrivateUser, "/me")

    def user(self, object_id):
        """Another user's public profile.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /users/{user_id}`): use `me` for the current user.
        """
        return self._one(User, "/users/" + self._path_id(object_id))

    def current_playback(self, market=None, additional_types=None):
        query = {}
        self._add_query(query, "market", market)
        self._add_query(query, "additional_types", additional_types)
        return self._one(CurrentlyPlaying, "/me/player", query)

    def currently_playing(self, market=None, additional_types=None):
        query = {}
        self._add_query(query, "market", market)
        self._add_query(query, "additional_types", additional_types)
        return self._one(CurrentlyPlaying, "/me/player/currently-playing", query)

    def queue(self):
        return self._one(Queue, "/me/player/queue")

    def transfer_playback(self, device_ids, play=None):
        data = {"device_ids": self._string_list(device_ids)}
        self._add_query(data, "play", play)
        return self._put_json("/me/player", data=data)

    def play(self, device_id=None, context_uri=None, uris=None, offset=None, position_ms=None):
        local = self._local(device_id)
        if local is not None:
            return local.play(context_uri=context_uri, uris=uris, position_ms=position_ms)
        data = {}
        self._add_query(data, "context_uri", context_uri)
        if uris is not None:
            data["uris"] = self._uri_list(uris)
        self._add_query(data, "offset", offset)
        self._add_query(data, "position_ms", position_ms)
        return self._put_json("/me/player/play", data=data, query=self._device_query(device_id))

    def pause(self, device_id=None):
        local = self._local(device_id)
        if local is not None:
            return local.pause()
        return self._put_json("/me/player/pause", query=self._device_query(device_id))

    def next_track(self, device_id=None):
        local = self._local(device_id)
        if local is not None:
            return local.next()
        return self._post_json("/me/player/next", query=self._device_query(device_id))

    def previous_track(self, device_id=None):
        local = self._local(device_id)
        if local is not None:
            return local.previous()
        return self._post_json("/me/player/previous", query=self._device_query(device_id))

    def seek(self, position_ms, device_id=None):
        local = self._local(device_id)
        if local is not None:
            return local.seek(position_ms)
        query = {"position_ms": position_ms}
        self._add_query(query, "device_id", device_id)
        return self._put_json("/me/player/seek", query=query)

    def repeat(self, state, device_id=None):
        query = {"state": state}
        self._add_query(query, "device_id", device_id)
        return self._put_json("/me/player/repeat", query=query)

    def shuffle(self, state, device_id=None):
        query = {"state": bool_string(state)}
        self._add_query(query, "device_id", device_id)
        return self._put_json("/me/player/shuffle", query=query)

    def volume(self, volume_percent, device_id=None):
        local = self._local(device_id)
        if local is not None:
            return local.set_volume(volume_percent)
        query = {"volume_percent": volume_percent}
        self._add_query(query, "device_id", device_id)
        return self._put_json("/me/player/volume", query=query)

    def add_to_queue(self, uri, device_id=None):
        query = {"uri": self._uri(uri)}
        self._add_query(query, "device_id", device_id)
        return self._post_json("/me/player/queue", query=query)

    def devices(self):
        data = self._get_json("/me/player/devices")
        devices = data.get("devices")
        result = [] if devices is None else [Device(item) for item in devices]
        if self.local is not None and self.local.device_id is not None:
            local_state = self.local.state()
            if not any(getattr(item, "id", None) == self.local.device_id for item in result):
                result.append(Device(local_state))
        return result

    def recently_played(self, limit=None, after=None, before=None):
        query = {}
        self._add_query(query, "limit", self._limit(limit))
        self._add_query(query, "after", after)
        self._add_query(query, "before", before)
        return self._page(PlayHistoryCursorPage, "/me/player/recently-played", query)

    def current_user_playlists(self, limit=None, offset=None):
        return self._page(PlaylistPage, "/me/playlists", self._page_query(limit=limit, offset=offset))

    def user_playlists(self, object_id, limit=None, offset=None):
        """A page of another user's playlists.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /users/{user_id}/playlists`): use `current_user_playlists` for the current user.
        """
        return self._page(
            PlaylistPage,
            "/users/" + self._path_id(object_id) + "/playlists",
            self._page_query(limit=limit, offset=offset),
        )

    def saved_albums(self, market=None, limit=None, offset=None):
        return self._page(SavedAlbumPage, "/me/albums", self._page_query(market=market, limit=limit, offset=offset))

    def saved_tracks(self, market=None, limit=None, offset=None):
        return self._page(SavedTrackPage, "/me/tracks", self._page_query(market=market, limit=limit, offset=offset))

    def saved_episodes(self, market=None, limit=None, offset=None):
        return self._page(SavedEpisodePage, "/me/episodes", self._page_query(market=market, limit=limit, offset=offset))

    def saved_shows(self, limit=None, offset=None):
        return self._page(SavedShowPage, "/me/shows", self._page_query(limit=limit, offset=offset))

    def saved_audiobooks(self, limit=None, offset=None):
        return self._page(AudiobookPage, "/me/audiobooks", self._page_query(limit=limit, offset=offset))

    def contains_saved_albums(self, ids):
        """Whether each of these albums is in the current user's library.

        Takes at most 20 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/albums/contains`): use `library_contains`.
        """
        return self._bools("/me/albums/contains", self._most("contains_saved_albums", ids))

    def save_albums(self, ids):
        """Save albums to the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/albums`): use `save_library_items`.
        """
        return self._put_ids("/me/albums", self._most("save_albums", ids))

    def remove_saved_albums(self, ids):
        """Remove albums from the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/albums`): use `remove_library_items`.
        """
        return self._delete_ids("/me/albums", self._most("remove_saved_albums", ids))

    def contains_saved_tracks(self, ids):
        """Whether each of these tracks is in the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/tracks/contains`): use `library_contains`.
        """
        return self._bools("/me/tracks/contains", self._most("contains_saved_tracks", ids))

    def save_tracks(self, ids):
        """Save tracks to the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/tracks`): use `save_library_items`.
        """
        return self._put_ids("/me/tracks", self._most("save_tracks", ids))

    def remove_saved_tracks(self, ids):
        """Remove tracks from the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/tracks`): use `remove_library_items`.
        """
        return self._delete_ids("/me/tracks", self._most("remove_saved_tracks", ids))

    def contains_saved_episodes(self, ids):
        """Whether each of these episodes is in the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/episodes/contains`): use `library_contains`.
        """
        return self._bools("/me/episodes/contains", self._most("contains_saved_episodes", ids))

    def save_episodes(self, ids):
        """Save episodes to the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/episodes`): use `save_library_items`.
        """
        return self._put_ids("/me/episodes", self._most("save_episodes", ids))

    def remove_saved_episodes(self, ids):
        """Remove episodes from the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/episodes`): use `remove_library_items`.
        """
        return self._delete_ids("/me/episodes", self._most("remove_saved_episodes", ids))

    def contains_saved_shows(self, ids):
        """Whether each of these shows is in the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/shows/contains`): use `library_contains`.
        """
        return self._bools("/me/shows/contains", self._most("contains_saved_shows", ids))

    def save_shows(self, ids):
        """Save shows to the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/shows`): use `save_library_items`.
        """
        return self._put_ids("/me/shows", self._most("save_shows", ids))

    def remove_saved_shows(self, ids):
        """Remove shows from the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/shows`): use `remove_library_items`.
        """
        return self._delete_ids("/me/shows", self._most("remove_saved_shows", ids))

    def contains_saved_audiobooks(self, ids):
        """Whether each of these audiobooks is in the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/audiobooks/contains`): use `library_contains`.
        """
        return self._bools("/me/audiobooks/contains", self._most("contains_saved_audiobooks", ids))

    def save_audiobooks(self, ids):
        """Save audiobooks to the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/audiobooks`): use `save_library_items`.
        """
        return self._put_ids("/me/audiobooks", self._most("save_audiobooks", ids))

    def remove_saved_audiobooks(self, ids):
        """Remove audiobooks from the current user's library.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/audiobooks`): use `remove_library_items`.
        """
        return self._delete_ids("/me/audiobooks", self._most("remove_saved_audiobooks", ids))

    def library_contains(self, uris):
        """Whether each URI is saved or followed by the current user.

        Takes at most 40 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        return tuple(bool(value) for value in self._get_json("/me/library/contains", query=self._query_with_uris(self._most("library_contains", uris))))

    def save_library_items(self, uris):
        """Save or follow anything that has a Spotify URI.

        Takes at most 40 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        return self._put_json("/me/library", query=self._query_with_uris(self._most("save_library_items", uris)))

    def remove_library_items(self, uris):
        """Remove or stop following anything that has a Spotify URI.

        Takes at most 40 URIs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        return self._delete_json("/me/library", query=self._query_with_uris(self._most("remove_library_items", uris)))

    def followed_artists(self, after=None, limit=None):
        query = {"type": "artist"}
        self._add_query(query, "after", after)
        self._add_query(query, "limit", self._limit(limit))
        data = self._get_json("/me/following", query=query)
        return ArtistCursorPage(data.get("artists", data))

    def follows_artists(self, ids):
        """Whether the current user follows each artist.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/following/contains`): use `library_contains`.
        """
        return self._following_bools("artist", self._most("follows_artists", ids))

    def follows_users(self, ids):
        """Whether the current user follows each user.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /me/following/contains`): use `library_contains`.
        """
        return self._following_bools("user", self._most("follows_users", ids))

    def follow_artists(self, ids):
        """Follow artists.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/following`): use `save_library_items`.
        """
        return self._follow("artist", self._most("follow_artists", ids))

    def follow_users(self, ids):
        """Follow users.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`PUT /me/following`): use `save_library_items`.
        """
        return self._follow("user", self._most("follow_users", ids))

    def unfollow_artists(self, ids):
        """Stop following artists.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/following`): use `remove_library_items`.
        """
        return self._unfollow("artist", self._most("unfollow_artists", ids))

    def unfollow_users(self, ids):
        """Stop following users.

        Takes at most 50 IDs in one request, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`DELETE /me/following`): use `remove_library_items`.
        """
        return self._unfollow("user", self._most("unfollow_users", ids))

    def top_artists(self, time_range=None, limit=None, offset=None):
        query = self._page_query(limit=limit, offset=offset)
        self._add_query(query, "time_range", time_range)
        return self._page(ArtistPage, "/me/top/artists", query)

    def top_tracks(self, time_range=None, limit=None, offset=None):
        query = self._page_query(limit=limit, offset=offset)
        self._add_query(query, "time_range", time_range)
        return self._page(TrackPage, "/me/top/tracks", query)

    def playlist_cover_image(self, object_id):
        data = self._get_json("/playlists/" + self._path_id(object_id) + "/images")
        return [Image(item) for item in data]

    def set_playlist_cover_image(self, object_id, base64_jpeg):
        """Upload a playlist's cover, a JPEG as Base64 text.

        Takes at most 256 KB of Base64, the maximum in Spotify's Web API
        reference. More raises `ValueError` before anything is sent.
        """
        if len(base64_jpeg) > _MOST_COVER_BYTES:
            raise ValueError(
                "set_playlist_cover_image() takes at most %d bytes of Base64, and got %d"
                % (_MOST_COVER_BYTES, len(base64_jpeg))
            )
        return self._put_body(
            "/playlists/" + self._path_id(object_id) + "/images",
            base64_jpeg,
            "image/jpeg",
        )

    def available_markets(self):
        """The markets where Spotify is available.

        Removed for Development Mode apps by Spotify's February 2026 changes
        (`GET /markets`), with no replacement.
        """
        data = self._get_json("/markets")
        markets = data.get("markets")
        if markets is None:
            return ()
        return markets

    def recommendation_genres(self):
        data = self._get_json("/recommendations/available-genre-seeds")
        genres = data.get("genres")
        if genres is None:
            return ()
        return genres

    def _market_query(self, market):
        if market is None:
            return None
        return {"market": market}

    def _page_query(self, market=None, limit=None, offset=None):
        query = {}
        self._add_query(query, "market", market)
        self._add_query(query, "limit", self._limit(limit))
        self._add_query(query, "offset", offset)
        return query

    def _device_query(self, device_id):
        if device_id is None:
            return None
        return {"device_id": device_id}

    def _query_with_ids(self, ids, query=None):
        if query is None:
            query = {}
        else:
            query = dict(query)
        query["ids"] = self._join_ids(ids)
        return query

    def _query_with_uris(self, uris, query=None):
        if query is None:
            query = {}
        else:
            query = dict(query)
        query["uris"] = self._join_uris(uris)
        return query

    def _bools(self, path, ids, query=None):
        return tuple(bool(value) for value in self._get_json(path, query=self._query_with_ids(ids, query=query)))

    def _following_bools(self, item_type, ids):
        query = {"type": item_type}
        return self._bools("/me/following/contains", ids, query=query)

    def _put_ids(self, path, ids):
        return self._put_json(path, data={"ids": self._id_list(ids)})

    def _delete_ids(self, path, ids):
        return self._delete_json(path, data={"ids": self._id_list(ids)})

    def _follow(self, item_type, ids):
        return self._put_json("/me/following", data={"ids": self._id_list(ids)}, query={"type": item_type})

    def _unfollow(self, item_type, ids):
        return self._delete_json("/me/following", data={"ids": self._id_list(ids)}, query={"type": item_type})

    def _snapshot(self, data):
        if data is None:
            return None
        return SnapshotResult(data)

    def _id_list(self, ids):
        if isinstance(ids, str):
            return [ids]
        return [self._id(value) for value in ids]

    def _id(self, value):
        object_id = getattr(value, "id", None)
        if object_id is not None:
            return object_id
        return str(value)

    def _uri_list(self, values):
        if isinstance(values, str):
            return [values]
        return [self._uri(value) for value in values]

    def _uri(self, value):
        uri = getattr(value, "uri", None)
        if uri is not None:
            return uri
        return str(value)

    def _string_list(self, values):
        if isinstance(values, str):
            return [values]
        return [str(value) for value in values]

    def _join_ids(self, ids):
        if isinstance(ids, str):
            return ids
        return ",".join(str(value) for value in ids)

    def _join_uris(self, uris):
        if isinstance(uris, str):
            return uris
        return ",".join(self._uri(value) for value in uris)

    def _join_optional(self, values):
        if values is None:
            return None
        return self._join_ids(values)

    def _add_query(self, query, field, value):
        if value is not None:
            query[field] = value


def bool_string(value):
    if value:
        return "true"
    return "false"


def snapshot_id(result):
    if result is None:
        return None
    value = getattr(result, "snapshot_id", None)
    if value is not None:
        return value
    return result.get("snapshot_id")
