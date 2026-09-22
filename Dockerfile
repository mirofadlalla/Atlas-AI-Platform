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

# python:3.11-slim currently inherits top-level wheel==0.46.3 from its own
# bootstrap. It is not required by this application, and its packaging>=24
# metadata conflicts with mlflow==2.10.1 (packaging<24). Setuptools is pinned
# to 80.10.1 for its compatible vendored wheel; remove only the independent,
# inherited top-level distribution. Build isolation remains managed by pip.
RUN python -m pip install --no-cache-dir --upgrade pip "setuptools==80.10.1" \
    && python -m pip uninstall -y wheel \
    && python -c "import importlib.metadata as m; top_level_wheel = [str(d.locate_file('')) for d in m.distributions() if d.metadata['Name'].lower() == 'wheel' and '/setuptools/_vendor' not in str(d.locate_file(''))]; assert not top_level_wheel, f'Unexpected top-level wheel: {top_level_wheel}'"

# CPU-only PyTorch dependency resolution
# Resolve requirements and the CPU-only PyTorch constraint together.
# The constraints use the official CPU wheels for CPython 3.11 / Linux amd64.
# The selected wheel is compatible with sentence-transformers==2.6.1
# (which requires torch>=1.11.0).
# Resolve the complete graph in one pip invocation. Merely pre-installing
# torch is insufficient without a constraint: a later resolver can otherwise
# choose and install a newer CUDA torch build.
#
# constraints-cpu.txt pins the CPU-only wheel: torch==2.4.1+cpu.
# sentence-transformers==2.6.1 no longer requires torchvision; Atlas-AI does
# not import it, so omitting it removes the package that caused the CUDA
# upgrade path in the prior build.
# They are fetched only from the official PyTorch CPU wheel index; all other
# dependencies continue to come from PyPI. CPU wheels have no nvidia-* or
# triton runtime dependencies.
COPY requirements.txt constraints-cpu.txt ./
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --constraint constraints-cpu.txt \
    -r requirements.txt \
    && python -m pip check \
    && python -c "import importlib.metadata as m; dists = list(m.distributions()); names = {d.metadata['Name'].lower() for d in dists}; forbidden = sorted(name for name in names if name.startswith('nvidia-') or name == 'triton'); top_level_wheel = [str(d.locate_file('')) for d in dists if d.metadata['Name'].lower() == 'wheel' and '/setuptools/_vendor' not in str(d.locate_file(''))]; assert not forbidden, f'Unexpected GPU packages: {forbidden}'; assert 'torchvision' not in names, 'Unexpected torchvision dependency'; assert not top_level_wheel, f'Unexpected top-level wheel: {top_level_wheel}'"

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
