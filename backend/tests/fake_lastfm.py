"""An in-memory Last.fm ``user.getRecentTracks`` behind an httpx2 MockTransport."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx2


@dataclass
class FakeLastfm:
    # (uts, artist, title, mbid)
    scrobbles: list[tuple[int, str, str, str]] = field(default_factory=list)
    now_playing: tuple[str, str] | None = None
    users: set[str] = field(default_factory=lambda: {"owen"})
    queued: list[httpx2.Response] = field(default_factory=list)
    requests: list[dict[str, str]] = field(default_factory=list)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        if self.queued:
            return self.queued.pop(0)
        if params.get("api_key") != "key":
            return httpx2.Response(403, json={"error": 10, "message": "Invalid API key"})
        if params["user"] not in self.users:
            return httpx2.Response(404, json={"error": 6, "message": "User not found"})
        lo = int(params.get("from", 0))
        hi = int(params.get("to", 2**40))
        rows = sorted((s for s in self.scrobbles if lo <= s[0] <= hi), reverse=True)
        limit = int(params["limit"])
        page = int(params["page"])
        total_pages = max(1, -(-len(rows) // limit))
        chunk = rows[(page - 1) * limit : page * limit]
        items: list[dict[str, Any]] = [
            {
                "artist": {"#text": artist, "mbid": ""},
                "name": title,
                "mbid": mbid,
                "album": {"#text": "Album"},
                "date": {"uts": str(uts), "#text": "..."},
            }
            for uts, artist, title, mbid in chunk
        ]
        if page == 1 and self.now_playing:
            items.insert(
                0,
                {
                    "artist": {"#text": self.now_playing[0]},
                    "name": self.now_playing[1],
                    "@attr": {"nowplaying": "true"},
                },
            )
        track: Any = items[0] if len(items) == 1 else items
        return httpx2.Response(
            200,
            json={
                "recenttracks": {
                    "track": track,
                    "@attr": {
                        "user": params["user"],
                        "page": str(page),
                        "perPage": str(limit),
                        "totalPages": str(total_pages),
                        "total": str(len(rows)),
                    },
                }
            },
        )
