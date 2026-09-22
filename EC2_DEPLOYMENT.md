# Atlas-AI Platform — EC2 Deployment Procedure

> **Target**: Ubuntu t3.small (x86_64), Docker + Docker Compose v2, GHCR image.
>
> **Image name format**: `ghcr.io/mirofadlalla/atlas-ai:sha-<GITHUB_SHA>`

---

## Prerequisites (one-time EC2 setup)

```bash
# Install Docker (if not already installed)
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
# Re-login or run: newgrp docker
```

---

## 1. Authenticate to GHCR

```bash
# Use a GitHub Personal Access Token with read:packages scope.
# Store it as an environment variable — never hardcode it.
echo "$GHCR_PAT" | docker login ghcr.io -u mirofadlalla --password-stdin
```

> **Security**: Store `GHCR_PAT` as an EC2 Parameter Store value or in a
> `~/.secrets` file with `chmod 600`. Do NOT paste it directly in shell history.

---

## 2. Prepare the `.env` file on EC2

The `.env` file lives on the EC2 host **outside** the Docker image. It must
**never** be committed to git or baked into the image.

```bash
# Create the env file in a safe location (e.g., the deploy directory)
mkdir -p ~/atlas-deploy
nano ~/atlas-deploy/.env
```

Minimum required contents:

```dotenv
# ── Required secrets ────────────────────────────────────────────────────────
API_SECRET_KEY=<long-random-secret>         # python -c "import secrets; print(secrets.token_urlsafe(48))"
POSTGRES_USER=atlas_user
POSTGRES_PASSWORD=<strong-db-password>
POSTGRES_DB=atlas_db
REDIS_PASSWORD=<strong-redis-password>

# ── Embedding & environment ──────────────────────────────────────────────────
ENVIRONMENT=production
EMBEDDING_MODEL_NAME=BAAI/bge-m3

# ── Optional external APIs ───────────────────────────────────────────────────
JINA_API_KEY=<your-jina-key>                # Required if using Jina fallback
GROQ_API_KEY=<your-groq-key>
CREDENTIAL_ENCRYPTION_KEY=<fernet-key>      # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SENTRY_DSN=

# ── Image tag (set to exact SHA before deploying) ────────────────────────────
ATLAS_IMAGE=ghcr.io/mirofadlalla/atlas-ai:sha-<GITHUB_SHA>

# ── Port (default 8000) ──────────────────────────────────────────────────────
API_PORT=8000
```

```bash
chmod 600 ~/atlas-deploy/.env
```

---

## 3. Copy Compose Files to EC2

```bash
# From your local machine:
scp docker-compose.yml                ubuntu@<ec2-ip>:~/atlas-deploy/
scp docker-compose.monitoring.yml     ubuntu@<ec2-ip>:~/atlas-deploy/

# Copy monitoring configuration (required by Prometheus / Grafana)
scp -r monitoring/                    ubuntu@<ec2-ip>:~/atlas-deploy/
```

---

## 4. Handle the Manual `atlas-api` Container Conflict

> **Context**: A container named `atlas-api` was created manually (not via
> Compose). Docker Compose will refuse to create a new container with the same
> name. This step resolves the conflict **safely**.

```bash
# Check whether the manual container exists and its state
docker ps -a --filter name=atlas-api

# Stop and remove the manual container ONLY.
# This does NOT affect any volumes or other containers.
docker stop atlas-api 2>/dev/null || true
docker rm   atlas-api 2>/dev/null || true

# Verify it is gone
docker ps -a --filter name=atlas-api
```

---

## 5. Pull the Target Image

```bash
cd ~/atlas-deploy

# Export the target SHA from your .env (or set it explicitly)
export ATLAS_IMAGE=ghcr.io/mirofadlalla/atlas-ai:sha-<GITHUB_SHA>

# Pull the exact SHA image from GHCR
docker pull "$ATLAS_IMAGE"

# Verify the image architecture is linux/amd64
docker image inspect "$ATLAS_IMAGE" \
  --format '{{.Architecture}} {{.Os}}'
# Expected output: amd64 linux
```

---

## 6. Deploy the Core Stack

```bash
cd ~/atlas-deploy

# Start all core services (postgres, qdrant, redis, api, celery_worker, celery_beat)
docker compose \
  --env-file .env \
  up -d

# Watch startup progress (Ctrl-C to stop watching — does NOT stop containers)
docker compose logs -f --tail=50
```

> **Persistent volumes are preserved**: `docker compose up -d` never deletes
> named volumes. Postgres, Qdrant, and Redis data survive restarts and image
> updates.

---

## 7. Verify Service Health

```bash
# Check all containers are healthy
docker compose ps

# Expected output (all State = running, Status = healthy or starting):
# NAME                   STATUS          PORTS
# atlas-postgres         running         ...
# atlas-qdrant           running         ...
# atlas-redis            running         ...
# atlas-api              running         0.0.0.0:8000->8000/tcp
# atlas-celery-worker    running         ...
# atlas-celery-beat      running         ...
```

---

## 8. Verify API Health

```bash
# Health endpoint — must return HTTP 200
curl -f http://localhost:8000/health
# Expected: {"status": "ok"} or similar

# FastAPI docs (confirm the API is fully initialised)
curl -f http://localhost:8000/docs | head -5

# Verify CPU-only PyTorch (no CUDA packages installed)
docker exec atlas-api python -c "
import torch
print('torch version:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
assert not torch.cuda.is_available(), 'ERROR: CUDA is available — unexpected on CPU instance'
print('✓ CPU-only PyTorch confirmed')
"

# Verify BGE-M3 loads on CPU (may take 1-3 min on first run — downloads model)
docker exec atlas-api python -c "
from sentence_transformers import SentenceTransformer
import torch
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print('Loading BAAI/bge-m3 on', device, '...')
m = SentenceTransformer('BAAI/bge-m3', device=device)
vecs = m.encode(['Atlas AI benchmark test'], normalize_embeddings=True)
print('✓ BGE-M3 loaded. Vector shape:', vecs.shape)
"

# Verify PostgreSQL connection
docker exec atlas-postgres pg_isready -U atlas_user -d atlas_db

# Verify Redis connection
docker exec atlas-redis redis-cli -a "$REDIS_PASSWORD" ping
# Expected: PONG

# Verify Qdrant
curl -sf http://localhost:6333/readyz && echo "Qdrant: ready"
# Note: Qdrant is NOT on a public port — use docker exec:
docker exec atlas-qdrant curl -sf http://localhost:6333/readyz
```

---

## 9. Verify Alembic Migrations Ran

```bash
# Check migration logs from the API startup
docker logs atlas-api 2>&1 | grep -i alembic

# Or exec directly
docker exec atlas-api alembic current
docker exec atlas-api alembic history --verbose | head -20
```

---

## 10. Verify Celery Workers

```bash
# Celery worker should show "ready" and connected to Redis broker
docker logs atlas-celery-worker 2>&1 | tail -20

# Quick connectivity check via celery inspect
docker exec atlas-celery-worker \
  celery -A app.celery.celery_config inspect ping
```

---

## 11. Run Embedding Benchmark (Optional)

```bash
# Run inside the API container (no production data is affected)
docker exec atlas-api python scripts/benchmark_embeddings.py \
  --provider bge-m3 \
  --iterations 5 \
  --batch-size 8

# If JINA_API_KEY is set, benchmark both:
docker exec atlas-api python scripts/benchmark_embeddings.py \
  --provider both \
  --iterations 5 \
  --output /tmp/benchmark.json

docker cp atlas-api:/tmp/benchmark.json ./benchmark_results.json
cat benchmark_results.json
```

---

## 12. Start Optional Monitoring Stack

> ⚠️  Only start this when memory is not a bottleneck. Each monitoring
> container uses 128–256 MB RAM.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env \
  up -d prometheus grafana
```

Access Grafana at `http://<ec2-ip>:3100` (default: admin / admin123).

---

## 13. Rollback to Previous SHA Image

If the new deployment is broken, roll back to the previous known-good SHA:

```bash
PREVIOUS_SHA=sha-<previous-GITHUB_SHA>
export ATLAS_IMAGE="ghcr.io/mirofadlalla/atlas-ai:${PREVIOUS_SHA}"

# Pull the rollback image
docker pull "$ATLAS_IMAGE"

# Update the .env with the previous SHA
sed -i "s|^ATLAS_IMAGE=.*|ATLAS_IMAGE=${ATLAS_IMAGE}|" ~/atlas-deploy/.env

# Restart only the Atlas services (infra services are unaffected)
docker compose --env-file .env up -d api celery_worker celery_beat

# Verify health
curl -f http://localhost:8000/health
```

> **Volumes are preserved during rollback**: Postgres, Qdrant, and Redis data
> are on named Docker volumes and are NEVER touched by a service restart.

---

## Disk Cleanup (Safe)

```bash
# Remove only dangling (untagged) images — safe on any system
docker image prune -f

# Remove old GHCR image tags (specify exact SHA tags to remove)
docker rmi ghcr.io/mirofadlalla/atlas-ai:sha-<old-SHA>

# NEVER run these without understanding their impact:
# docker system prune -a    ← removes ALL unused images including still-needed ones
# docker volume prune       ← DESTROYS ALL UNUSED VOLUMES including database data
```

---

## Security Checklist

- [ ] `.env` file has `chmod 600` and is NOT in git
- [ ] `ATLAS_IMAGE` is set to an exact SHA tag, not `latest`
- [ ] PostgreSQL is NOT exposed publicly (only via Docker network)
- [ ] Redis is NOT exposed publicly (only via Docker network)
- [ ] Qdrant is NOT exposed publicly (only via Docker network)
- [ ] API secret key is at least 48 characters, randomly generated
- [ ] GHCR PAT has `read:packages` scope only
- [ ] EC2 security group allows only port 8000 (and 22 for SSH)
- [ ] Non-root user `atlas` (UID 1000) runs inside the container

---

## Future GPU Upgrade Path

> The current t3.small cannot have a GPU physically added.

To run BGE-M3 on GPU in the future:

1. **Stop the current stack** (`docker compose down`) — data volumes are preserved.
2. **Change or create a new EC2 instance** of type `g4dn.xlarge` (NVIDIA T4 GPU, 16 GB VRAM) or similar. Verify instance availability and service quota in your AWS region.
3. **Install NVIDIA drivers** on the new instance (see [AWS GPU driver guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/install-nvidia-driver.html)).
4. **Install NVIDIA Container Toolkit** for Docker GPU access.
5. **Build a GPU Dockerfile** (use `torch==2.4.1+cu121` instead of `+cpu` and add the `--runtime=nvidia` flag to the `api` service in Compose).
6. The existing `embedded_model.py` code already handles GPU automatically via `device = "cuda" if torch.cuda.is_available() else "cpu"` — no application code changes needed.
