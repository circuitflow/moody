# Moody (2026 rewrite): design spec

- **Date:** 2026-09-28
- **Status:** Approved for M0; later milestones are refined per milestone
- **Owner:** circuitflow

## 1. Summary

Moody began as a 2007 Python thesis project that estimated the mood of songs in a local MP3 library. This rewrite rebuilds it as a **portfolio showcase**. It uses current Music Information Retrieval (MIR) methods: pretrained audio embeddings, continuous valence/arousal regression and mood tagging. It adds an interactive web UI and a link to streaming services for listening history and playlist export.

## 2. Goals and non-goals

### Goals
1. **Audio analysis:** mood is inferred from the audio itself with pretrained deep models, not taken from metadata.
2. **Mood representation:** a continuous 2D mood space (Russell's circumplex: valence × arousal) plus discrete mood tags, with per-segment *mood trajectories* inside a track.
3. **Web UI:** an interactive mood map, a track view and a mood-path playlist builder.
4. **Streaming:** Spotify/Last.fm listening history joined to analyzed tracks, and playlists exported to Spotify.
5. **Public demo:** a working demo that needs no backend, hosted on GitHub Pages from a precomputed CC-licensed dataset.
6. **Engineering quality:** typed code, tests, CI, reproducible evaluation with metrics published in the README.

### Non-goals
- A multi-tenant SaaS, user accounts, or hosted analysis of uploaded audio.
- Streaming or playing audio from Spotify. Moody never touches Spotify audio.
- Training models from scratch. We use pretrained heads; fine-tuning is an optional stretch.

## 3. Background and constraints

- **Spotify API (Nov 2024):** new apps lost access to `audio-features`, `audio-analysis`, recommendations and 30 s previews. Spotify is therefore used only for *identity* (search, ISRC), *history* (recently played, top tracks) and *output* (playlist creation). Apps in development mode are limited to 25 allow-listed users, which is acceptable for self-hosting.
- **Audio availability:** analysis runs only where we have audio: the user's local library when self-hosting, or CC-licensed Jamendo audio for the public demo.
- **Essentia:** `essentia-tensorflow==2.1b6.dev1389` ships wheels for CPython 3.9–3.13 on Linux x86_64 and macOS. Moody targets **Python 3.13**.
- **Licensing:** Essentia is AGPL-3.0, and the Essentia pretrained models are CC BY-NC-SA 4.0 (non-commercial). This fits an open-source portfolio project, and Moody itself is AGPL-3.0-or-later (§13).

## 4. User-facing features

| Feature | Description | Milestone |
|---|---|---|
| Library scan | `moody scan ~/Music` indexes and analyzes files; incremental and resumable | M1 |
| Mood map | Zoomable V/A scatter of the whole library; color by tag, filter by artist or tag, lasso selection | M2 |
| Track view | Mood trajectory over time, tag probabilities, DSP descriptors, nearest neighbors | M2 |
| Mood-path playlists | Pick start and end points on the map, choose a length, get an ordered and smooth playlist | M3 |
| Spotify export | Match tracks via ISRC/search and create the playlist on the user's account | M3 |
| Listening mood over time | Spotify recently-played + Last.fm scrobble import joined to the library; heatmap by week or hour | M3 |
| Public demo | Static build over a precomputed Jamendo subset | M4 |
| Custom V/A head (stretch) | Small MLP on EffNet embeddings trained on DEAM/PMEmo, evaluated against the pretrained head | M5 |
| Text-to-mood search (stretch) | CLAP text embeddings, e.g. "rainy Sunday morning" | M5 |
| Lyrics fusion (stretch) | Lyric sentiment fused with audio V/A (Lyricator lineage) | M5 |

## 5. Architecture

```
┌──────────────────────── frontend (React + TS + Vite) ────────────────────────┐
│  MoodMap (visx/D3) · TrackView · PathBuilder · History                         │
│  DataSource interface ─┬─ ApiDataSource  (self-host: talks to FastAPI)         │
│                        └─ StaticDataSource (demo: reads exported JSON bundle)  │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │ REST (OpenAPI → generated TS client)
┌──────────────────────── backend (FastAPI, Python 3.13) ──────────────────────┐
│ api/        routers: tracks, map, playlists, history, jobs, auth/spotify       │
│ jobs/       in-process worker + queue table; progress over SSE                 │
│ ingest/     file walker, mutagen tags, content hash, Chromaprint (optional)    │
│ analysis/   Essentia pipeline: decode → EffNet embeddings → heads → DSP        │
│ mood/       V/A normalization, tag vocabulary, path planner, neighbors         │
│ streaming/  Spotify (PKCE OAuth), Last.fm import, track matcher                │
│ store/      SQLAlchemy 2.x models + SQLite (WAL); embeddings as float32 blobs  │
│ export/     static demo bundle writer                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Repository layout:** a monorepo with `backend/` (uv project, `src/moody`), `frontend/` (npm), `eval/`, `demo/`, `docs/`, `docker-compose.yml` and `.github/workflows/`.

**Why this shape:**
- The single Python process with SQLite needs no infrastructure, is trivial to self-host, and is enough for libraries of up to about 100k tracks.
- Nearest-neighbor search over about 100k × 1280-d float32 vectors (about 500 MB) is done in NumPy for M1–M3. `sqlite-vec` or FAISS stays a drop-in option.
- The `DataSource` abstraction lets the same UI serve both the self-hosted app and the static demo.

## 6. Analysis pipeline

Two embedding extractors are needed. Essentia's pretrained valence/arousal heads exist only for MSD-MusiCNN and AudioSet-VGGish embeddings, while the mood/theme tags and the richest similarity space come from Discogs-EffNet. Verified against `MTG/essentia` `doc/sphinxdoc/models.rst` and the example scripts.

| Step | Implementation | Output |
|---|---|---|
| 1. Decode | `MonoLoader(sampleRate=16000, resampleQuality=4)` | mono float32 @16 kHz |
| 2a. Embed (style) | `TensorflowPredictEffnetDiscogs(graphFilename="discogs-effnet-bs64-1.pb", output="PartitionedCall:1")` | `[n_patches, 1280]`, used for tags, mood classifiers and similarity |
| 2b. Embed (emotion) | `TensorflowPredictMusiCNN(graphFilename="msd-musicnn-1.pb", output="model/dense/BiasAdd")` | `[n_patches, 200]` (3 s patches, 1.5 s hop), used for V/A |
| 3a. Valence/arousal | `TensorflowPredict2D(graphFilename="deam-msd-musicnn-2.pb", output="model/Identity")` (the alternative `emomusic-msd-musicnn-2.pb` is compared in eval) | `[n, 2]` = (valence, arousal), range [1, 9] |
| 3b. Mood classifiers | `mood_{happy,sad,aggressive,relaxed,party}-discogs-effnet-1.pb`, `output="model/Softmax"` | probability per class |
| 3c. Mood/theme tags | `mtg_jamendo_moodtheme-discogs-effnet-1.pb` (default output, sigmoid) | 56 tag probabilities |
| 4. DSP | `RhythmExtractor2013`, `KeyExtractor`, `LoudnessEBUR128` on 44.1 kHz audio | BPM, key/scale, LUFS |

**M5 showcase item:** train our own V/A regression head on Discogs-EffNet embeddings of DEAM (and PMEmo) with a small PyTorch MLP exported to ONNX. It should beat or match the MusiCNN head in `eval/`, and it would remove the second extractor from the pipeline.

**Normalization:** V/A is mapped linearly from [1, 9] to [-1, 1]. The track-level value is the mean over patches, with the per-patch MusiCNN series kept as the trajectory, smoothed with a moving average of about 3 patches before storage. Tag probabilities are stored in full, and the top-k above threshold go into a denormalized column for filtering.

**Model management:**
- `moody models pull` downloads the `.pb` files and their `.json` metadata from `essentia.upf.edu/models` into `~/.cache/moody/models`, checking SHA-256 values pinned in `models.lock.json`.
- Each analysis row records a `pipeline_version`, a hash of the model files plus the pipeline code version, so changing a model triggers a re-analysis of stale rows.

**Idempotency:** tracks are keyed by a content hash (BLAKE2b of the first and last 1 MB plus the file size), so renamed or moved files are not re-analyzed.

**Throughput target:** at least 5× real time on a laptop CPU. Decode and inference are batched per track, and the worker pool is process-based and CPU-bound.

**Testability:** the `Analyzer` is a protocol. Unit tests use a `FakeAnalyzer`, and integration tests run the real models on three short CC0 clips in `backend/tests/fixtures/audio` and compare against golden JSON within a tolerance.

## 7. Data model (SQLite)

- `tracks`: id, content_hash (unique), path, title, artist, album, duration_s, isrc, mb_recording_id, file_mtime, added_at
- `analyses`: track_id (PK/FK), pipeline_version, valence, arousal, bpm, key, scale, loudness_lufs, mood_probs (JSON), tag_probs (JSON), top_tags (text), analyzed_at
- `segments`: track_id, idx, start_s, valence, arousal (PK track_id + idx)
- `embeddings`: track_id, model (`discogs-effnet` | `msd-musicnn`), dim, vector (BLOB float32, mean-pooled)
- `jobs`: id, kind, status, progress, total, error, created_at, finished_at
- `plays`: id, provider, played_at, external_id, artist, title, isrc, track_id (nullable FK after matching)
- `external_ids`: track_id, provider, external_id (e.g. Spotify track URI)
- `playlists` and `playlist_items`: id, name, start/end V/A, params (JSON); position, track_id
- `oauth_tokens`: provider, access/refresh token (stored locally in plaintext; the file lives in the user's data dir, documented)

Migrations use Alembic from M1 onward.

## 8. Mood-path playlist algorithm

Input:
- start point p₀ and end point p₁ in V/A space
- length N
- optional filters (tags, artists, BPM range)
- smoothness weight λ

1. Place N waypoints wᵢ along the segment p₀→p₁. An optional curve through an intermediate point can be picked on the map.
2. Run a beam search (width B = 32) to choose tracks t₁…t_N, distinct and with no artist repeated within k = 3 positions, minimizing
   `Σ ‖va(tᵢ) − wᵢ‖² + λ · Σ (1 − cos(emb(tᵢ₋₁), emb(tᵢ)))`.
   The first term keeps the path on the mood trajectory; the second makes consecutive tracks sound compatible.
3. Candidates for each waypoint are the M = 200 nearest tracks in V/A space (a KD-tree over 2D points), so the search stays cheap.

The planner is a pure function over arrays, which makes it property-testable: it returns a valid length, distinct tracks, and a monotone approach to p₁ when data is dense.

## 9. Streaming integration

- **Spotify:**
  - Authorization Code with PKCE, using a loopback redirect `http://127.0.0.1:8000/api/auth/spotify/callback`.
  - Scopes: `user-read-recently-played user-top-read playlist-modify-private playlist-modify-public`.
  - Matching order: (1) ISRC from file tags → `search?q=isrc:`; (2) normalized artist + title search with duration within ±3 s; (3) otherwise unmatched and flagged in the UI.
- **Last.fm:** import full history with `user.getRecentTracks`, paginated, using an API key only. It is joined to the library by MusicBrainz ID, then by normalized artist/title.
- Recently-played is capped at 50 per call, so a background job polls it periodically while the app runs. Last.fm is the path for deep history.

## 10. API surface (v1)

`GET /api/health` · `GET /api/tracks?q=&tag=&limit=&cursor=` · `GET /api/tracks/{id}` · `GET /api/tracks/{id}/neighbors` · `GET /api/map` (compact arrays: id, v, a, top tag) · `POST /api/scan` · `GET /api/jobs/{id}` · `GET /api/jobs/{id}/events` (SSE) · `POST /api/playlists/path` · `POST /api/playlists/{id}/export/spotify` · `GET /api/history/mood?bucket=week|hour` · `GET /api/auth/spotify/login` · `GET /api/auth/spotify/callback` · `POST /api/history/lastfm/import` · `GET /api/audio/{id}` (range requests, local files only)

The OpenAPI schema is exported in CI, and the frontend client is generated from it with `openapi-typescript`.

## 11. Frontend

- React 19, TypeScript (strict), Vite, TanStack Query and TanStack Router, plus visx (D3 underneath) for charts.
- **Mood map:** canvas rendering for more than 10k points, an SVG overlay for axes, labels and selection, and a quadtree for hover picking. Quadrant labels: tense/angry, happy/excited, sad/depressed, calm/relaxed.
- **Theming:** light/dark, accessible palette, keyboard navigation for track lists.
- **Demo mode:** `VITE_DATA_SOURCE=static` builds against `/data/*.json` from the demo bundle. Audio previews stream from Jamendo's CC-licensed URLs.

## 12. Demo, deployment and evaluation

- **Demo bundle:** `demo/build_demo.py` selects about 1,500 CC-BY/CC-BY-SA tracks from MTG-Jamendo (moodtheme split), downloads the audio, runs the pipeline and writes `map.json`, `tracks/*.json` and attribution metadata. Audio is not rehosted; tracks link to Jamendo. The bundle is committed as a release asset, not into git.
- **GitHub Pages:** a workflow builds the frontend in static mode and deploys it on tags to `main`.
- **Self-hosting:**
  - `docker compose up`: the backend image with essentia-tensorflow and pulled models, the library mounted read-only at `/music`, and the frontend served by nginx proxying `/api`.
  - Native: `uv run moody serve` plus `npm run dev`.
- **Evaluation (`eval/`):**
  - V/A regression on the DEAM test split: Pearson r, R² and CCC for the chosen head, plus a comparison of the emomusic and DEAM heads.
  - Tag ROC-AUC/PR-AUC on the MTG-Jamendo moodtheme split-0 test set.
  - Results go to `eval/results/*.json`, and a script renders the README table.
  - **2007 vs 2026:** if the legacy thesis code and data are imported into `legacy/`, rerun its feature set as a baseline on the same split.

## 13. Quality, CI, licensing

- **Backend:**
  - ruff (lint and format) and mypy `--strict` on `src/`.
  - pytest with unit, integration (marker `models`, real Essentia, run in a separate CI job with cached models) and API tests (httpx `TestClient`).
- **Frontend:** `tsc --noEmit`, eslint, vitest + Testing Library, and a Playwright smoke test against the static demo build.
- **CI:** GitHub Actions jobs `backend`, `frontend`, `models` (scheduled and manual; heavy) and `pages`.
- **Repository license:** AGPL-3.0-or-later (decided 2026-09-28), for consistency with Essentia. The README carries model and dataset attributions, and the non-commercial model license is called out.

## 14. Risks

| Risk | Mitigation |
|---|---|
| The pretrained DEAM head generalizes poorly to modern pop | Report eval metrics honestly; M5 option: fine-tune a small head on DEAM + PMEmo embeddings |
| essentia-tensorflow wheel/Python version drift | Pin the exact version, test in CI, keep the Docker image as the reference environment |
| Spotify API policy changes further | Spotify is isolated behind a `StreamingProvider` interface; Last.fm, and potentially ListenBrainz, are alternatives |
| Jamendo audio availability or licensing for the demo | Store attribution; the bundle build is reproducible; the demo keeps working without audio previews |
| Large libraries: slow first scan | Incremental, resumable jobs with progress over SSE; `--limit` and path filters |

## 15. Milestones

- **M0 (scaffold):**
  - monorepo, backend FastAPI `/api/health` + Typer CLI, frontend Vite app calling health
  - CI, Docker Compose, this spec and the M0–M1 plan
- **M1 (analysis core):**
  - models pull and lock, ingest, analysis pipeline, SQLite + Alembic
  - `moody scan`, golden-file tests
- **M2 (explore UI):** map and track APIs, the mood map, the track view.
- **M3 (streaming + playlists):** path planner, Spotify OAuth, matching and export, Last.fm import, history heatmap.
- **M4 (showcase):** demo bundle, Pages deploy, eval report, README with GIFs.
- **M5 (stretch):** CLAP text search, lyrics fusion, a custom V/A head on EffNet embeddings.

## 16. Open questions

1. **Legacy code:** the original 2007 thesis code (on the author's Mac) should be imported into `legacy/`, read-only, to recover the thesis mood categories and results for the comparison.
2. The repository license is still undecided (§13).
