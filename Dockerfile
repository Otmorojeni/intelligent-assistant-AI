# ==============================================================================
# CDO AI Assistant — Production Dockerfile (MSKs-2 VM: 2 vCPU, 4 GB RAM, 60 GB NVMe)
# Serves FastAPI Backend + Static React/Next.js Web UI from a single container (0 MB Node runtime)
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install minimal system dependencies for psycopg / healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy backend source, seeding scripts, normative materials, and compiled UI bundle (if present)
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY materials/ ./materials/
COPY tests/ ./tests/

# Create directories for generated DOCX files and static React/Next.js frontend export
RUN mkdir -p /app/generated_docs /app/ui

EXPOSE 8000

# Idempotently initialize & seed PostgreSQL if empty, then start single-worker Uvicorn
CMD ["sh", "-c", "python scripts/01_seed_postgres.py --if-empty && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]
