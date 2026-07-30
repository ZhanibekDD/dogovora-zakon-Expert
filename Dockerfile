FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-liberation2 \
        fonts-dejavu-core \
        libpq5 \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 zakonexpert && \
    useradd --uid 10001 --gid zakonexpert --create-home --shell /usr/sbin/nologin zakonexpert

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /app/storage/uploads /app/storage/documents /app/storage/backups \
    && chown -R zakonexpert:zakonexpert /app

USER zakonexpert

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('localhost', 8000), timeout=3)" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bot"]
