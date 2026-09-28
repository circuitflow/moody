# Reference runtime for the analysis backend (essentia-tensorflow, CPU).
FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    MOODY_DATA_DIR=/data MOODY_MODELS_DIR=/models MOODY_LIBRARY_PATH=/music
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra analysis --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra analysis

EXPOSE 8000
CMD ["moody", "serve", "--host", "0.0.0.0", "--port", "8000"]
