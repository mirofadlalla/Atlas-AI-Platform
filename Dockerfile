# ==================== BUILD STAGE ====================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies into builder
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ==================== RUNTIME STAGE ====================
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime C libraries & curl for healthcheck, create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 atlas

# Copy installed Python packages and binaries from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code with non-root ownership
COPY --chown=atlas:atlas . .

# Set up entrypoint script
COPY --chown=atlas:atlas scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint
RUN chmod +x /usr/local/bin/docker-entrypoint

# Create necessary runtime directories with non-root ownership
RUN mkdir -p /app/logs /app/data /app/uploads /app/mlruns /app/app/files/uploads && \
    chown -R atlas:atlas /app

# Switch to unprivileged user
USER atlas

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBUG=False \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose HTTP port
EXPOSE 8000

# Entrypoint executes entrypoint script (runs Alembic migrations if RUN_MIGRATIONS=true)
ENTRYPOINT ["/usr/local/bin/docker-entrypoint"]

# Default command runs FastAPI server via Uvicorn
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-config", "/app/logging_config.json"]

