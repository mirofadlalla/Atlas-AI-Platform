# ==================== BUILD STAGE ====================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (minimal set required for psycopg2 compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools/wheel first (single layer, rarely changes)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# ── CPU-only PyTorch pre-install ──────────────────────────────────────────────
# Install PyTorch CPU wheel BEFORE requirements.txt so pip sees torch already
# satisfied and never resolves the CUDA-enabled wheel pulled in by
# sentence-transformers.  The CPU wheel eliminates:
#   - ~3.2 GB  NVIDIA CUDA runtime libraries
#   - ~0.9 GB  triton (GPU compiler, not used on CPU inference)
#
# torch==2.4.1+cpu  — latest stable CPU release for Python 3.11 / x86_64.
# Compatible with sentence-transformers==2.2.2 (requires torch>=1.6.0).
# Only available from the official PyTorch CPU wheel index below.
RUN pip install --no-cache-dir \
    "torch==2.4.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies (torch already satisfied → skipped)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================== RUNTIME STAGE ====================
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime C libraries, curl (healthcheck), and create non-root user.
# libgomp1 — required by PyTorch CPU for OpenMP multi-threading (intra-op parallelism).
# libpq5  — required by psycopg2-binary at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 atlas

# Copy installed Python packages and binaries from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code with non-root ownership.
# Files excluded by .dockerignore are never sent to the build context.
COPY --chown=atlas:atlas . .

# Set up entrypoint script (runs Alembic migrations when RUN_MIGRATIONS=true)
COPY --chown=atlas:atlas scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint
RUN chmod +x /usr/local/bin/docker-entrypoint

# Create necessary runtime directories with non-root ownership.
# /app/app/files/uploads — used by the file-upload endpoints.
RUN mkdir -p /app/logs /app/data /app/uploads /app/mlruns /app/app/files/uploads \
    && chown -R atlas:atlas /app

# Switch to unprivileged user
USER atlas

# Runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBUG=False \
    PORT=8000 \
    # Disable tokenizers parallelism warning (safe for single-process inference)
    TOKENIZERS_PARALLELISM=false

# Health check — waits 60 s before first probe to allow slow BGE-M3 cold-start
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose HTTP port (Prometheus metrics exposed on /metrics, same port)
EXPOSE 8000

# Entrypoint handles optional Alembic migrations, then exec CMD
ENTRYPOINT ["/usr/local/bin/docker-entrypoint"]

# Default command: FastAPI via Uvicorn
# workers=1 is intentional — BGE-M3 holds ~1.5 GB RAM; multiple workers on
# t3.small (2 GB) will OOM.  Use Celery for background parallelism instead.
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-config", "/app/logging_config.json"]
