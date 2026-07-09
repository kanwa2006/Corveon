# Corveon backend — multi-stage production image.
# The SAME image runs the API and the ARQ worker via different commands (§17):
#   API    : gunicorn app.main:app -k uvicorn.workers.UvicornWorker
#   Worker : arq app.workers.main.WorkerSettings
# Build context is the repository root: docker build -f infra/docker/backend.Dockerfile .

# ── Builder ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
# System deps for OCR / PDF handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr ghostscript build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install .

# ── Runtime ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr ghostscript \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 corveon
COPY --from=builder /venv /venv
WORKDIR /app
COPY backend/ /app/
USER corveon
EXPOSE 8000
# Default to the API; override the command to run the worker.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "2"]
