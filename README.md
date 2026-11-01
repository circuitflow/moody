# Moody

**The mood of your music library, mapped.**

**[Try the demo →](https://circuitflow.github.io/moody/)** 1,151 Creative Commons tracks from Jamendo,
analyzed by Moody, in your browser. No install.

![The mood map: every track placed by valence and arousal, coloured by whether the 2007 thesis model agrees](docs/media/map.gif)

Moody analyzes your music with modern Music Information Retrieval models. It places every track in a
continuous **valence × arousal** mood space (Russell's circumplex) and tags it with moods and themes.
From there you can build **mood-path playlists**, e.g. "tense → calm over 20 tracks", export them to
Spotify or as M3U, and join your Last.fm or Spotify listening history to see the mood of what you
actually play.

It is a 2026 rewrite of a 2007 MIT thesis project of the same name. The original Moody computed
hand-built features from a folder of MP3s and classified them with a decision tree. This version uses
pretrained deep audio embeddings (Essentia's Discogs-EffNet and MSD-MusiCNN), a web UI and
streaming-service integration, and it keeps the 2007 verdict next to the 2026 one on every track.

| Mood paths | Inside a track |
|---|---|
| ![Dragging the end of a mood path re-plans the playlist as it moves](docs/media/path.gif) | ![A track page: mood over time, mood tags, audio facts, the 2007 verdict and similar tracks](docs/media/track.gif) |
| Drag a start and an end mood; the playlist re-plans as you move them. | The mood trajectory, tags, audio facts, the 2007-vs-2026 verdict and similar tracks. |

> **Status:** M0–M4 done: analysis core, explore UI, mood-path playlists (M3U and Spotify), listening
> history, scanning from the app, an evaluation report and the [public demo](https://circuitflow.github.io/moody/).
> See the [design spec](docs/superpowers/specs/2026-09-28-moody-rewrite-design.md) and the plans for
> [M0–M1](docs/superpowers/plans/2026-09-28-moody-m0-m1.md), [M2](docs/superpowers/plans/2026-10-31-moody-m2.md),
> [M3](docs/superpowers/plans/2026-10-31-moody-m3.md) and [M4](docs/superpowers/plans/2026-11-01-moody-m4.md).

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

<!-- eval:start -->
### How well it works

**Valence/arousal on DEAM** (400 clips, ratings by listeners; the head was trained on DEAM, so these are in-domain and optimistic):

| | Pearson r |
|---|---|
| valence | 0.82 |
| arousal | 0.84 |
| valence minus arousal (do the outputs mean different things?) | 0.61 |

Predicted valence and arousal correlate at +0.80, against +0.55 between listeners' ratings: the model leans on one "intensity" axis. Loudness correlates +0.18 with predicted valence minus arousal, -0.02 with rated: loud music looks happier to the model than to people.

**2007 thesis vs 2026** on Russell's eight octants, DEAM clips whose rated mood is clearly away from neutral (289 clips):

| model | exact octant | within one octant | mean angle error |
|---|---|---|---|
| 2026 (DEAM head) | 53% | 93% | 26° |
| 2007 (decision tree) | 10% | 41% | 89° |

Always guessing the most common octant: 28%; picking at random: 12.5%, with a 90° mean angle error. The 2007 tree runs on its five features re-derived with Essentia (CLAM and The Echo Nest are gone), and those mappings aren't yet calibrated against the thesis songs, so its row measures the port as much as the 2007 model.

**Mood/theme tags** on 1152 held-out MTG-Jamendo test tracks (54 tags): macro ROC-AUC 0.74, macro PR-AUC 0.13. Among tags with at least 20 tracks, best: epic 0.90, children 0.88, christmas 0.87, summer 0.87, motivational 0.87; hardest: slow 0.49, film 0.49, nature 0.50, inspiring 0.53, documentary 0.57.

Details: [`eval/results/`](eval/results/).
<!-- eval:end -->

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
- Demo music: Creative Commons tracks (BY, BY-SA, BY-NC, BY-NC-SA) from [Jamendo](https://www.jamendo.com) via the MTG-Jamendo dataset, streamed from Jamendo and credited track by track on the demo's [credits page](https://circuitflow.github.io/moody/#/credits). Some licences are non-commercial, so the demo's music is for non-commercial use.

## License

Moody is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE), in line with
Essentia's AGPL-3.0. The Essentia pretrained models are separately licensed under CC BY-NC-SA 4.0
(non-commercial).
