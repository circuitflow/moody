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

## Conventions
- mypy `--strict` and ruff must pass; tests must pass with `-W error`.
- Frontend components never call `fetch` directly; they go through the `DataSource` interface (`src/data/source.ts`),
  so the static demo and the API-backed app share all UI code.
- Valence/arousal are stored normalized to [-1, 1]; the raw model output is in [1, 9].
- Essentia models: V/A heads take **MSD-MusiCNN** embeddings; mood/tag heads take **Discogs-EffNet** embeddings.
