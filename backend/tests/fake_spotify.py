"""An in-memory Spotify (accounts + Web API) behind an httpx2 MockTransport."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx2

from moody.streaming.match import core_artist, core_title


def track_item(
    uri: str, name: str, artist: str, seconds: float, isrc: str | None = None
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "uri": uri,
        "name": name,
        "artists": [{"name": artist}],
        "duration_ms": int(seconds * 1000),
    }
    if isrc:
        item["external_ids"] = {"isrc": isrc}
    return item


@dataclass
class FakeSpotify:
    catalog: list[dict[str, Any]] = field(default_factory=list)
    valid_tokens: set[str] = field(default_factory=lambda: {"access-1"})
    refresh_ok: bool = True
    challenge: str | None = None  # from the authorize URL, to check PKCE
    playlists: dict[str, dict[str, Any]] = field(default_factory=dict)
    searches: list[str] = field(default_factory=list)
    token_grants: list[str] = field(default_factory=list)
    queued: list[httpx2.Response] = field(default_factory=list)  # forced API responses
    recently_played: list[dict[str, Any]] = field(default_factory=list)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "accounts.spotify.com":
            return self._token(request)
        if self.queued:
            return self.queued.pop(0)
        if (
            request.headers.get("Authorization", "").removeprefix("Bearer ")
            not in self.valid_tokens
        ):
            return httpx2.Response(
                401, json={"error": {"status": 401, "message": "The access token expired"}}
            )
        path = request.url.path.removeprefix("/v1")
        if path == "/me":
            return httpx2.Response(200, json={"id": "owen", "display_name": "Owen"})
        if path == "/search":
            return self._search(request.url.params["q"], int(request.url.params["limit"]))
        if path == "/me/playlists" and request.method == "POST":
            body = _json(request)
            pid = f"pl{len(self.playlists) + 1}"
            self.playlists[pid] = {"name": body["name"], "public": body["public"], "uris": []}
            return httpx2.Response(
                201,
                json={
                    "id": pid,
                    "name": body["name"],
                    "external_urls": {"spotify": f"https://open.spotify.com/playlist/{pid}"},
                },
            )
        m = re.fullmatch(r"/playlists/(\w+)/items", path)
        if m and request.method == "POST":
            self.playlists[m.group(1)]["uris"].extend(_json(request)["uris"])
            return httpx2.Response(201, json={"snapshot_id": "s"})
        if path == "/me/player/recently-played":
            return httpx2.Response(200, json={"items": self.recently_played, "next": None})
        return httpx2.Response(404, json={"error": {"status": 404, "message": f"no route {path}"}})

    def _token(self, request: httpx2.Request) -> httpx2.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        grant = form["grant_type"]
        self.token_grants.append(grant)
        if grant == "authorization_code":
            digest = hashlib.sha256(form["code_verifier"].encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if form["code"] != "good-code" or challenge != self.challenge:
                return httpx2.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "Invalid authorization code",
                    },
                )
            return httpx2.Response(
                200,
                json={
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "scope": "x",
                },
            )
        if grant == "refresh_token" and self.refresh_ok and form["refresh_token"] == "refresh-1":
            self.valid_tokens.add("access-2")
            return httpx2.Response(200, json={"access_token": "access-2", "expires_in": 3600})
        return httpx2.Response(
            400, json={"error": "invalid_grant", "error_description": "Refresh token revoked"}
        )

    def _search(self, q: str, limit: int) -> httpx2.Response:
        self.searches.append(q)
        if limit > 10:
            return httpx2.Response(400, json={"error": {"status": 400, "message": "Invalid limit"}})
        isrc = re.fullmatch(r"isrc:(\S+)", q)
        if isrc:
            items = [
                i for i in self.catalog if i.get("external_ids", {}).get("isrc") == isrc.group(1)
            ]
        else:
            m = re.fullmatch(r"track:(.*?)(?: artist:(.*))?", q)
            assert m, q
            title, artist = m.group(1), m.group(2)
            items = [
                i
                for i in self.catalog
                if core_title(i["name"]) == core_title(title)
                and (artist is None or core_artist(i["artists"][0]["name"]) == core_artist(artist))
            ]
        return httpx2.Response(200, json={"tracks": {"items": items[:limit]}})


def _json(request: httpx2.Request) -> dict[str, Any]:
    import json

    data: dict[str, Any] = json.loads(request.content)
    return data
