# syntax=docker/dockerfile:1

# --- Stage 1: build the frontend SPA -----------------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend runtime -------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock /app/backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

COPY backend/ /app/backend/
COPY data/ /app/data/

COPY --from=frontend-build /app/frontend/dist /app/static

RUN mkdir -p /data

ENV FIPM_DATA_DIR=/app/data \
    FIPM_STATIC_DIR=/app/static \
    PATH="/app/backend/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["sh", "-c", "python -m fipm import-data && uvicorn fipm.main:app --host 0.0.0.0 --port 8000"]
