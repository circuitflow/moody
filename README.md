# Moody

**The mood of your music library, mapped.**

Moody analyzes your music with modern Music Information Retrieval models. It places every track in a
continuous **valence × arousal** mood space, tags it with moods and themes, and lets you build
**mood-path playlists**, e.g. "tense → calm over 20 tracks". Playlists can be exported to Spotify, and
your listening history can be joined to see how your mood shifts over time.

It is a 2026 rewrite of a 2007 thesis project of the same name. The original Moody computed hand-built
features from a folder of MP3s. This version uses pretrained deep audio embeddings (Essentia's
Discogs-EffNet and MSD-MusiCNN), a web UI, and streaming-service integration.

> **Status:** early development (M0: scaffold). See the [design spec](docs/superpowers/specs/2026-09-28-moody-rewrite-design.md)
> and the [M0–M1 plan](docs/superpowers/plans/2026-09-28-moody-m0-m1.md).

## How it works

```
audio ─▶ Discogs-EffNet embeddings ─▶ mood classifiers · 56 mood/theme tags · similarity
     ├─▶ MSD-MusiCNN embeddings  ─▶ valence/arousal regression (DEAM) ─▶ per-segment mood trajectory
     └─▶ DSP: tempo, key, loudness
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
MOODY_LIBRARY=~/Music docker compose up --build   # then open http://localhost:8080
```

Your library is mounted read-only.

## Credits

- [Essentia](https://essentia.upf.edu/) (AGPL-3.0) and the Essentia pretrained models (CC BY-NC-SA 4.0), from the Music Technology Group, Universitat Pompeu Fabra.
- Valence/arousal heads trained on [DEAM](https://cvml.unige.ch/databases/DEAM/); mood/theme tags from [MTG-Jamendo](https://mtg.github.io/mtg-jamendo-dataset/).
