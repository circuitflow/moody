# Moody

**The mood of your music library, mapped.**

Moody analyzes your music with modern Music Information Retrieval models. It places every track in a
continuous **valence × arousal** mood space, tags it with moods and themes, and lets you build
**mood-path playlists**, e.g. "tense → calm over 20 tracks". Playlists can be exported to Spotify, and
your listening history can be joined to see how your mood shifts over time.

It is a 2026 rewrite of a 2007 thesis project of the same name. The original Moody computed hand-built
features from a folder of MP3s. This version uses pretrained deep audio embeddings (Essentia's
Discogs-EffNet and MSD-MusiCNN), a web UI, and streaming-service integration.

> **Status:** M3 done: analysis core, an explore UI (mood map, track pages, list), mood-path
> playlists (M3U and Spotify export) and listening history from Last.fm and Spotify. See the
> [design spec](docs/superpowers/specs/2026-09-28-moody-rewrite-design.md) and the plans for
> [M0–M1](docs/superpowers/plans/2026-09-28-moody-m0-m1.md), [M2](docs/superpowers/plans/2026-10-31-moody-m2.md)
> and [M3](docs/superpowers/plans/2026-10-31-moody-m3.md).

## Quick start (self-hosted)

```bash
git clone https://github.com/circuitflow/moody.git && cd moody
(cd frontend && npm ci && npm run build)
cd backend
uv sync --extra analysis                 # Python 3.13; essentia-tensorflow on Linux x86_64 / macOS
uv run moody models pull                 # ~300 MB of pretrained models, checksum-verified
uv run moody scan ~/Music --workers 4    # incremental; rerun any time
uv run moody serve --ui ../frontend/dist # open http://127.0.0.1:8000
```

### Playlists and listening history

- **Mood paths** (`#/path`): drag a start and an end mood on the map and get an ordered playlist
  between them. Save it, then download it as M3U (Apple Music: File → Library → Import Playlist).
- **Spotify export:** create an app at [developer.spotify.com](https://developer.spotify.com/dashboard)
  with the redirect URI `http://127.0.0.1:8000/api/auth/spotify/callback`. Then put
  `MOODY_SPOTIFY_CLIENT_ID=<client id>` in `backend/.env`. No secret is needed (PKCE). Spotify's
  Development Mode requires the app owner to have Premium and allows 5 users.
- **Listening history:** Moody only knows the mood of music it has analyzed, so plays are matched
  to your library and each import reports how many matched.

```bash
# Last.fm: a free API key from https://www.last.fm/api/account/create
echo 'MOODY_LASTFM_API_KEY=<key>' >> .env
uv run moody history lastfm <your user>          # incremental; --full re-reads everything
# Spotify: request "Extended streaming history" under Account → Privacy, then
uv run moody history spotify-export ~/Downloads/my_spotify_data.zip
uv run moody history status                      # coverage per source; re-matches after scans
```

## How it works

```
audio ─▶ Discogs-EffNet embeddings ─▶ mood classifiers · 56 mood/theme tags · similarity
     ├─▶ MSD-MusiCNN embeddings  ─▶ valence/arousal regression (DEAM) ─▶ per-segment mood trajectory
     └─▶ DSP: tempo, key, loudness

mood map + style vectors ─▶ in-browser beam search ─▶ mood-path playlist ─▶ M3U · Spotify
Last.fm / Spotify plays ─▶ matched to analyzed tracks ─▶ mood by week and hour of day
```

Why not Spotify's audio features? Since late 2024 Spotify no longer offers audio features, audio analysis
or previews to new apps. Moody therefore analyzes audio it can actually reach: your local files when
self-hosting, or CC-licensed Jamendo tracks for the public demo. Spotify is used only for listening
history and playlist export.

## Development

Requirements: [uv](https://docs.astral.sh/uv/), Node 22.

```bash
# backend: http://127.0.0.1:8000/docs
cd backend
uv sync                      # add --extra analysis for essentia-tensorflow (Linux x86_64 / macOS, Python ≤3.13)
uv run moody serve --reload
uv run pytest && uv run ruff check . && uv run mypy

# frontend: http://localhost:5173 (proxies /api to the backend)
cd frontend
npm install
npm run dev
npm test && npm run lint && npm run typecheck
```

### Self-hosting with Docker

```bash
MOODY_LIBRARY=~/Music docker compose up --build   # then open http://127.0.0.1:8080
```

Your library is mounted read-only. For Spotify in Docker, use the redirect URI
`http://127.0.0.1:8080/api/auth/spotify/callback`. Pass `MOODY_SPOTIFY_CLIENT_ID`,
`MOODY_LASTFM_API_KEY` and `MOODY_LASTFM_USER` through the environment or a `.env` file next to
`docker-compose.yml`.

## Credits

- [Essentia](https://essentia.upf.edu/) (AGPL-3.0) and the Essentia pretrained models (CC BY-NC-SA 4.0), from the Music Technology Group, Universitat Pompeu Fabra.
- Valence/arousal heads trained on [DEAM](https://cvml.unige.ch/databases/DEAM/); mood/theme tags from [MTG-Jamendo](https://mtg.github.io/mtg-jamendo-dataset/).

## License

Moody is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE), in line with
Essentia's AGPL-3.0. The Essentia pretrained models are separately licensed under CC BY-NC-SA 4.0
(non-commercial).
