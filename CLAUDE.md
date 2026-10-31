# Moody: notes for Claude

Monorepo: `backend/` (Python 3.13, uv, FastAPI, Typer CLI `moody`) and `frontend/` (React 19 + TS + Vite).
The design spec lives in `docs/superpowers/specs/`, implementation plans in `docs/superpowers/plans/`.

## Commands
- Backend (run in `backend/`): `uv sync`, `uv run pytest -W error`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy`
- Heavy MIR deps: `uv sync --extra analysis` (essentia-tensorflow, pinned; wheels only for CPython ≤3.13).
  Tests that need real models are marked `@pytest.mark.models` and are skipped by default; run with `-m models`.
- Frontend (run in `frontend/`): `npm ci`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`
- Static demo build: `VITE_DATA_SOURCE=static VITE_BASE=/moody/ npm run build`
- After changing API routes or schemas: `uv run moody openapi ../frontend/openapi.json` (CI fails if stale).
- Local end-to-end without models: `uv run moody scan <folder> --fake`, then `uv run moody serve`.
- Frontend types from the API: `npm run gen:api` (after regenerating `openapi.json`; CI fails if stale).
- Static bundle: `uv run moody export-static <dir>` (same JSON shapes as the API).
- Duplicate files (e.g. WAV + MP3 of one recording): `uv run moody duplicates` lists them; `scan` recomputes the groups (`ingest/duplicates.py`).
- Browser tests (in `frontend/`): `npm run e2e:data` (deterministic fixture into `public/data`), then `npm run e2e`.
- Listening history: `uv run moody history lastfm <user> | spotify-export <zip> | spotify | status`.
- Spotify/Last.fm need `MOODY_SPOTIFY_CLIENT_ID` / `MOODY_LASTFM_API_KEY` (e.g. in `backend/.env`, gitignored).
- Local Playwright reuses a server already on :4173. If e2e runs an old build, stop that `vite preview` by its exact PID.

## Conventions
- mypy `--strict` and ruff must pass; tests must pass with `-W error`.
- Frontend components never call `fetch` directly; they go through the `DataSource` interface (`src/data/source.ts`),
  so the static demo and the API-backed app share all UI code.
- Valence/arousal are stored normalized to [-1, 1]; the raw model output is in [1, 9].
- Catalog queries filter `queries.PRIMARY` (`Track.duplicate_of IS NULL`) so hidden copies never reach the UI.
- Migrations: SQLite batch mode rebuilds the table. `env.py` turns foreign keys off while migrating, so the rebuild can't cascade-delete child rows. Still prefer in-place `ALTER TABLE` where SQLite supports it.
- Essentia models: V/A heads take **MSD-MusiCNN** embeddings; mood/tag heads take **Discogs-EffNet** embeddings.
- The mood-path planner is TypeScript (`frontend/src/features/path/planner.ts`) so it runs in the static demo;
  the backend only serves style vectors (`/api/embeddings`) and stores playlists.
- Features the static demo can't have (saving, Spotify, history) check `DataSource.canSave`.
- Outbound HTTP (Spotify, Last.fm) goes through the app's `httpx2.Client` (`app.state.http`). Tests pass a
  `MockTransport` fake (`tests/fake_spotify.py`, `tests/fake_lastfm.py`); CI never calls real services.
- Spotify Web API (2026): `POST /me/playlists`, `POST /playlists/{id}/items`, search `limit` ≤ 10.
