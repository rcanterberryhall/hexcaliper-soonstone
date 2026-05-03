FROM python:3.12-slim

# System deps: sqlite3 CLI for the .backup command (DEPLOYMENT.md / backups),
# curl for the docker-compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache pip layer separately from app code.
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[dev]"

# App code
COPY soonstone/ /app/soonstone/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Data dir mounted from host
VOLUME ["/data"]

ENV DATABASE_URL=sqlite:////data/soonstone.db \
    PYTHONUNBUFFERED=1 \
    TZ=UTC

EXPOSE 5055

# Apply any new migrations on container start, then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m soonstone --serve"]
