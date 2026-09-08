# FIP Manager

A small tool for creating, editing and exporting GO FAIR FAIR Implementation
Profiles (FIPs), built for a CONFOA 2026 workshop. FastAPI + SQLAlchemy +
SQLite backend, Vue 3 + Vite + vue-i18n frontend. Questionnaires, the FER
catalogue and translations live as JSON under `data/`.

## Run locally

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
uv sync
cp ../.env.example ../.env   # adjust as needed
uv run python -m fipm import-data
uv run python -m fipm serve   # http://localhost:8000
```

`FIPM_DB_PATH` and `FIPM_DATA_DIR` default to `<repo-root>/fipm.db` and
`<repo-root>/data` (resolved from `backend/fipm/config.py`'s own location, not
the process's working directory), so `import-data` and `serve` find the real
`data/` whether you run them from the repo root or from `backend/`. Override
either in `.env` if you need a different location.

Tests: `cd backend && uv run pytest`. Lint: `uv run ruff check . && uv run ruff format --check .`

Frontend (Node 20):

```sh
cd frontend && npm install && npm run dev
```

Or run everything with Docker: `docker compose up --build`.

## Environment variables

All config is `FIPM_`-prefixed env vars, read by `backend/fipm/config.py`;
see `.env.example` for the full list and defaults (base URL, DB path, secret
key, admin bootstrap, session TTL, cookie security, CSRF origins, data/static dirs).

## Docs

- [`docs/PLAN.md`](docs/PLAN.md) — overall plan and data model
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — week-by-week roadmap
- [`docs/specs/`](docs/specs) — implementation specs
