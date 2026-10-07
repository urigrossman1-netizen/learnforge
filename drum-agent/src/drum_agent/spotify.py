"""Spotify track metadata via the Web API client-credentials flow.

Only the search endpoint is used. It survives the February 2026 Web API
changes, with two limits that matter here: `limit` is capped at 10, and
tracks no longer carry `popularity` or `external_ids` (ISRC).
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
MAX_LIMIT = 10

_token: tuple[str, float] | None = None


class SpotifyError(RuntimeError):
    pass


def has_credentials() -> bool:
    return bool(os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET"))


def _token_value() -> str:
    global _token
    if _token and time.time() < _token[1] - 60:
        return _token[0]
    if not has_credentials():
        raise SpotifyError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not set "
            "(run `uv run drum-agent setup`)."
        )
    raw = f"{os.environ['SPOTIFY_CLIENT_ID']}:{os.environ['SPOTIFY_CLIENT_SECRET']}"
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": "Basic " + base64.b64encode(raw.encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    data = _send(req)
    _token = (data["access_token"], time.time() + data.get("expires_in", 3600))
    return _token[0]


def _send(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        hint = ""
        if e.code == 401 or "invalid_client" in body:
            hint = " Check the Client ID/Secret in drum-agent/.env."
        elif e.code == 403:
            hint = (
                " Spotify development-mode apps require the app owner to have"
                " an active Premium subscription."
            )
        elif e.code == 429:
            hint = " Rate limited / quota exceeded; wait and retry."
        raise SpotifyError(f"HTTP {e.code} from Spotify: {body}.{hint}") from None
    except urllib.error.URLError as e:
        raise SpotifyError(f"Cannot reach Spotify: {e.reason}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:  # timeouts, resets, non-JSON pages
        raise SpotifyError(f"Cannot reach Spotify: {type(e).__name__}: {e}") from None


def search_tracks(
    query: str, *, title: str | None = None, artist: str | None = None, limit: int = 5
) -> list[dict]:
    """Search tracks; field filters are used when title/artist are known."""
    if title and artist:
        q = f'track:"{title}" artist:"{artist}"'
    else:
        q = query
    params = {"q": q, "type": "track", "limit": max(1, min(limit, MAX_LIMIT))}
    req = urllib.request.Request(
        SEARCH_URL + "?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"Bearer {_token_value()}"},
    )
    items = _send(req).get("tracks", {}).get("items", [])
    if not items and q != query:
        return search_tracks(query, limit=limit)
    return [_track(t) for t in items if t]


def _track(t: dict) -> dict:
    album = t.get("album") or {}
    return {
        "id": t.get("id"),
        "title": t.get("name"),
        "artists": [a.get("name") for a in t.get("artists", [])],
        "album": album.get("name"),
        "release_date": album.get("release_date"),
        "duration_s": round(t.get("duration_ms", 0) / 1000, 2),
        "explicit": t.get("explicit"),
        "track_number": t.get("track_number"),
        "url": (t.get("external_urls") or {}).get("spotify"),
        "uri": t.get("uri"),
    }
