# syntax=docker/dockerfile:1.6
###############################################################################
# Stage 1: builder -- install Python dependencies into a venv
###############################################################################
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by psycopg2-binary and pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first (maximise layer cache reuse)
COPY requirements.txt .

# Create a virtual environment and install all deps
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

###############################################################################
# Stage 2: runtime -- minimal image with non-root user
###############################################################################
FROM python:3.11-slim AS runtime

# Install libpq runtime (needed by psycopg2-binary at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 etlgroup && \
    useradd --uid 1001 --gid etlgroup --no-create-home --shell /bin/false etl-user

WORKDIR /app

# Copy the venv from builder
COPY --from=builder --chown=etl-user:etlgroup /opt/venv /opt/venv

# Copy application source
COPY --chown=etl-user:etlgroup etl/        ./etl/
COPY --chown=etl-user:etlgroup scripts/    ./scripts/
COPY --chown=etl-user:etlgroup main.py     ./main.py

# Ensure venv is on the PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER etl-user

# Use CMD (not ENTRYPOINT) so ECS task command overrides replace the full command.
# ECS --overrides command:["python","scripts/init_schema.py"] works correctly
# only when ENTRYPOINT is not set -- CMD is fully replaced by the override.
CMD ["python", "main.py"]
