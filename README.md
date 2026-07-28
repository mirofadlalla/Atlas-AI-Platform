# Atlas AI Platform - Complete Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Architecture](#architecture)
4. [Project Structure](#project-structure)
5. [Installation & Setup](#installation--setup)
6. [Configuration](#configuration)
7. [Running the Application](#running-the-application)
8. [API Endpoints](#api-endpoints)
9. [Core Features & Components](#core-features--components)
10. [Database Schema](#database-schema)
11. [RAG Pipeline](#rag-pipeline)
12. [Agent System](#agent-system)
13. [Monitoring & Observability](#monitoring--observability)
14. [Development Guide](#development-guide)
15. [Deployment](#deployment)
16. [Troubleshooting](#troubleshooting)
17. [Contributing](#contributing)

---

## Project Overview

**Atlas AI Platform** is an enterprise-grade, multi-tenant SaaS application that combines **Retrieval-Augmented Generation (RAG)** with **autonomous multi-step reasoning agents** to enable organizations with:

- 🤖 **Intelligent Query Answering**: Semantic search across documents with reranking
- 🧠 **Multi-Step Reasoning**: LangGraph-based autonomous agents that decompose complex questions
- 📊 **Real-time Streaming**: Server-Sent Events (SSE) for live agent thinking process
- 💰 **Cost Tracking**: Detailed billing and token usage analytics
- 🏢 **Multi-Tenancy**: Complete tenant isolation with role-based access
- 🔐 **User Management**: Admin approval workflow with invitation system
- 📈 **Monitoring**: Prometheus + Grafana for system metrics and observability
- ⚡ **Async Processing**: Celery task queue for non-blocking operations

---

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.10+) with Uvicorn ASGI server
- **ORM**: SQLAlchemy with Alembic migrations
- **API Documentation**: OpenAPI/Swagger (auto-generated)

### AI/ML Components
- **LLM**: OpenAI API (GPT-4, GPT-3.5-Turbo)
- **Embeddings**: Sentence Transformers (all-MiniLM-L6-v2)
- **Vector Database**: Qdrant (hybrid dense/sparse search)
- **Reasoning Engine**: LangGraph (stateful multi-step workflows)
- **Reranking**: Cross-Encoder (ms-marco-MiniLM-L-6-v2) + BM25

### Databases & Caching
- **Relational DB**: PostgreSQL 15
- **Vector DB**: Qdrant
- **Cache**: Redis 7 (query cache, semantic cache, Celery broker)
- **Message Queue**: RabbitMQ/AMQP (Celery broker)

### Monitoring & Logging
- **Metrics**: Prometheus
- **Visualization**: Grafana
- **Error Tracking**: Sentry
- **Logging**: JSON structured logs via pythonjsonlogger

### Frontend
- **Framework**: React (SPA)
- **Build Tool**: webpack/Create React App
- **API Client**: Axios with automatic JWT handling
- **Real-time**: Server-Sent Events (SSE)

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Package Management**: pip with requirements.txt
- **Database Migrations**: Alembic

---

## Architecture

### High-Level System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     React Frontend (SPA)                       │
│                    (Auth, Query, Upload UI)                    │
└─────────────────────────┬──────────────────────────────────────┘
                          │ HTTPS/WSS
                          ▼
┌────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (4 workers)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Routes Layer: /auth, /query, /agent, /ingest, /metrics  │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │                                      │
│  ┌──────────────────────▼─────────────────────────────────┐  │
│  │     Services Layer (Business Logic & Controllers)      │  │
│  │  • Auth Service      • RAG Service      • Agent Runner │  │
│  │  • Ingest Service    • Logging Service  • Cost Tracker │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │                                      │
│  ┌──────────────────────▼─────────────────────────────────┐  │
│  │   Repositories Layer (Data Access Abstraction)         │  │
│  └──┬──────────────┬──────────────┬────────────────────┬─┘  │
└─────┼──────────────┼──────────────┼────────────────────┼──────┘
      │              │              │                    │
   ┌──▼──────┐  ┌───▼───────┐ ┌───▼──────┐         ┌───▼────┐
   │PostgreSQL│  │ Qdrant    │ │  Redis   │         │Celery  │
   │  (Users, │  │ (Vectors, │ │  (Cache, │         │(Tasks) │
   │  Tenants,│  │ Embeddings)│ │ Broker)  │         │        │
   │  Runs,   │  │           │ │          │         └────┬───┘
   │  Costs)  │  │           │ │          │              │
   └──────────┘  └──────────┘ └──────────┘         ┌─────▼──────┐
                                                    │ RabbitMQ   │
                                                    │ (Message   │
                                                    │  Broker)   │
                                                    └────────────┘

External APIs:
├─ OpenAI (LLM)
├─ Prometheus (Metrics)
├─ Sentry (Error Tracking)
└─ Email Service (Invitations)
```

### Request Flow Diagram

```
User Query (HTTP POST)
    │
    ├─► [Authentication Middleware]
    │   └─► Validate JWT, extract tenant_id
    │
    ├─► [Rate Limiter]
    │   └─► Check request quota (Redis)
    │
    ├─► [Route Handler]
    │   ├─► Input validation (Pydantic schemas)
    │   └─► Call service layer
    │
    ├─► [Service Layer]
    │   ├─► Business logic
    │   ├─► Repository calls for DB/Vector DB
    │   └─► Stream response (SSE for agents)
    │
    ├─► [Repository Layer]
    │   ├─► PostgreSQL CRUD
    │   ├─ Qdrant vector search
    │   └─► Redis cache operations
    │
    └─► [Async Task (Celery)]
        ├─► Logging (non-blocking)
        ├─► Cost aggregation
        └─► Email notifications
```

---

## Project Structure

```
atlas-ai/
├─ alembic/                          # Database migration management
│  ├─ versions/                      # Migration scripts
│  │  ├─ dcf644ec6a71_create_atlas_db.py
│  │  ├─ 31ddc81adc69_create_atlas_db_tables.py
│  │  ├─ 1eb4a877921f_create_runs_and_costlog_tables.py
│  │  ├─ 3c409934de50_added_tracker_db_table.py
│  │  ├─ add_user_approval_workflow.py
│  │  ├─ add_invitations_table.py
│  │  ├─ add_processing_status_to_tracker.py
│  │  └─ add_user_approval_workflow.py
│  ├─ env.py                        # Alembic configuration
│  └─ script.py.mako                # Migration template
│
├─ app/                              # Main application package
│
│  ├─ core/                          # Foundation & Configuration
│  │  ├─ config.py                   # Pydantic Settings (environment variables)
│  │  │                              # - Database URLs
│  │  │                              # - Redis/Qdrant configuration
│  │  │                              # - API keys, JWT secrets
│  │  │                              # - LLM model names and timeouts
│  │  ├─ db.py                       # SQLAlchemy setup
│  │  │                              # - Engine initialization
│  │  │                              # - Session factory
│  │  │                              # - Connection pooling
│  │  ├─ auth.py                     # JWT & Password utilities
│  │  │                              # - Token creation/verification
│  │  │                              # - bcrypt password hashing
│  │  │                              # - Claims extraction
│  │  ├─ monitors.py                 # Prometheus metrics registration
│  │  │                              # - HTTP request/response metrics
│  │  │                              # - Document ingestion metrics
│  │  │                              # - Custom LLM metrics
│  │  ├─ metrics.py                  # RAG-specific metric container
│  │  │                              # - Token usage aggregation
│  │  │                              # - Cache statistics
│  │  │                              # - Latency tracking
│  │  ├─ rate_limitizer.py           # Role-based rate limiting
│  │  │                              # - Admin: 300 req/min
│  │  │                              # - User: 100 req/min
│  │  │                              # - Guest: 20 req/min
│  │  └─ README.md                   # Core module documentation
│
│  ├─ models/                        # SQLAlchemy ORM Models
│  │  ├─ base.py                     # Base model with common fields
│  │  │                              # - id (UUID)
│  │  │                              # - created_at, updated_at
│  │  │                              # - tenant_id (multi-tenancy)
│  │  ├─ user.py                     # User model
│  │  │                              # - email, password_hash
│  │  │                              # - role (admin, user, viewer)
│  │  │                              # - approval_status (pending/approved/rejected)
│  │  ├─ tenant.py                   # Tenant (Organization) model
│  │  │                              # - company_name, plan_tier
│  │  │                              # - subscription_status
│  │  ├─ runs.py                     # Agent execution runs model
│  │  │                              # - agent_type, status
│  │  │                              # - tokens_used, latency_ms
│  │  │                              # - cache_hit, cost_usd
│  │  ├─ costLog.py                  # Cost tracking model
│  │  │                              # - cost_type (embedding, completion)
│  │  │                              # - model_used, token_count
│  │  │                              # - cost_usd
│  │  ├─ documents.py                # Document metadata model
│  │  │                              # - file_hash (deduplication)
│  │  │                              # - chunk_count
│  │  ├─ invitation.py               # Invitation model
│  │  │                              # - token, email
│  │  │                              # - expires_at, status
│  │  ├─ TRACKER_DB_FILE.py          # File processing status model
│  │  │                              # - file_path, status
│  │  │                              # - progress_percentage
│  │  ├─ uuid.py                     # UUID generation utils
│  │  ├─ __init__.py
│  │  └─ README.md                   # Models documentation
│
│  ├─ agent/                         # LangGraph-based Reasoning Engine
│  │  ├─ core/
│  │  │  ├─ state.py                 # AgentState TypedDict
│  │  │  │                           # - question, decomposed_questions
│  │  │  │                           # - thoughts, observations
│  │  │  │                           # - cost tracking, token counts
│  │  │  ├─ graph.py                 # LangGraph workflow definition
│  │  │  │                           # - State machine transitions
│  │  │  │                           # - Node connections
│  │  │  │                           # - Conditional routing
│  │  │  └─ callbacks.py             # Event streaming & logging
│  │  │
│  │  ├─ nodes/
│  │  │  ├─ decompose_node.py        # Question decomposition
│  │  │  │                           # - Break complex Q into sub-questions
│  │  │  │                           # - Creates execution plan
│  │  │  ├─ thought_node.py          # Decision logic
│  │  │  │                           # - Decide next action (retrieve/SQL/finish)
│  │  │  │                           # - Route based on reasoning
│  │  │  ├─ retrieval_node.py        # RAG document retrieval
│  │  │  │                           # - Calls Qdrant vector search
│  │  │  │                           # - Integrates reranking
│  │  │  ├─ sql_node.py              # SQL query execution
│  │  │  │                           # - Plans SQL queries
│  │  │  │                           # - Executes against PostgreSQL
│  │  │  └─ finish_node.py           # Final answer formatting
│  │  │                              # - Aggregates observations
│  │  │                              # - Returns formatted response
│  │  │
│  │  ├─ tools/
│  │  │  ├─ retrieval.py             # Semantic search implementation
│  │  │  │                           # - Query embedding
│  │  │  │                           # - Qdrant hybrid search
│  │  │  │                           # - Cross-encoder reranking
│  │  │  │                           # - Result formatting
│  │  │  ├─ sql_engine/
│  │  │  │  ├─ query_planner.py      # SQL query planning
│  │  │  │  │                        # - Question to SQL translation
│  │  │  │  │                        # - Safety checks
│  │  │  │  └─ executor.py           # SQL execution wrapper
│  │  │  │                           # - Connection pooling
│  │  │  │                           # - Result formatting
│  │  │  └─ utils.py                 # Tool utilities
│  │  │
│  │  ├─ schemas.py                  # Pydantic request/response schemas
│  │  ├─ README.md                   # Agent architecture documentation
│  │  └─ __init__.py
│
│  ├─ rag/                           # RAG Pipeline
│  │  ├─ ingest_data_pipline.py      # Document ingestion orchestration
│  │  │                              # - File upload handling
│  │  │                              # - Deduplication (SHA-256 hash)
│  │  │                              # - Document parsing (PDF, markdown, JSON)
│  │  │                              # - Semantic chunking
│  │  │                              # - Batch embedding generation
│  │  │                              # - Qdrant upsert
│  │  ├─ retrivel_data_pipline.py    # Query processing pipeline
│  │  │                              # - 3-tier cache checking
│  │  │                              # - Embedding generation
│  │  │                              # - Hybrid vector search
│  │  │                              # - Cross-encoder reranking
│  │  │                              # - Result formatting
│  │  ├─ reranker.py                 # Reranking strategies
│  │  │                              # - Cross-Encoder model
│  │  │                              # - BM25 fallback
│  │  │                              # - Hybrid scoring
│  │  ├─ data/                       # Temporary data storage
│  │  ├─ evaluation/                 # RAG evaluation suite
│  │  ├─ steps/                      # Pipeline step implementations
│  │  ├─ README.md                   # RAG documentation
│  │  └─ __init__.py
│
│  ├─ repositories/                  # Data Access Layer (Repository Pattern)
│  │  ├─ user_repository.py          # User CRUD operations
│  │  │                              # - Create, get, list, update, delete
│  │  │                              # - Tenant-filtered queries
│  │  │                              # - Role-based filtering
│  │  ├─ tenant_repository.py        # Tenant CRUD operations
│  │  │                              # - Org registration
│  │  │                              # - Plan management
│  │  ├─ runs_repository.py          # Agent execution history
│  │  │                              # - Store run records
│  │  │                              # - Query with date range filtering
│  │  │                              # - Cost aggregation
│  │  ├─ cost_log_repository.py      # Cost tracking & billing
│  │  │                              # - Log LLM costs
│  │  │                              # - Generate billing reports
│  │  ├─ qdrant.py                   # Vector database operations
│  │  │                              # - Hybrid search (dense + sparse)
│  │  │                              # - Collection management
│  │  │                              # - Metadata filtering
│  │  ├─ invitation_repository.py    # Invitation management
│  │  │                              # - Create invitations
│  │  │                              # - Validate tokens
│  │  │                              # - Accept/reject invitations
│  │  ├─ trakcer_db_file_repositorie.py # File processing status
│  │  │                              # - Track ingestion progress
│  │  ├─ README.md                   # Repository pattern documentation
│  │  └─ __init__.py
│
│  ├─ services/                      # Business Logic Layer
│  │  ├─ llm_runner.py               # LLM API wrapper
│  │  │                              # - OpenAI integration
│  │  │                              # - Token counting & cost calculation
│  │  │                              # - Streaming support
│  │  │                              # - Error handling & retries
│  │  ├─ token_service.py            # JWT token management
│  │  │                              # - Token creation
│  │  │                              # - Token verification
│  │  │                              # - Token refresh logic
│  │  ├─ hash_service.py             # Password utilities
│  │  │                              # - bcrypt hashing
│  │  │                              # - Verification
│  │  │
│  │  ├─ auth_services/
│  │  │  ├─ auth_service.py          # Login/logout logic
│  │  │  │                           # - User authentication
│  │  │  │                           # - Current user extraction
│  │  │  ├─ auth_admin_service.py    # Admin operations
│  │  │  │                           # - User approval
│  │  │  │                           # - Role management
│  │  │  └─ user_profile_service.py  # Profile management
│  │  │                              # - Update profile
│  │  │                              # - Preference management
│  │  │
│  │  ├─ rag_services/
│  │  │  ├─ ingest_rag_service.py    # RAG ingestion orchestration
│  │  │  │                           # - Validation & deduplication
│  │  │  │                           # - Repository coordination
│  │  │  ├─ query_logging_service.py # Async query logging
│  │  │  │                           # - Celery task for logging
│  │  │  ├─ agent_logging_service.py # Agent execution logging
│  │  │  │                           # - Detailed telemetry
│  │  │  └─ eval_pipline.py          # RAG evaluation
│  │  │                              # - Quality metrics
│  │  │                              # - Performance benchmarks
│  │  │
│  │  ├─ tenant_registration_service.py # Organization signup
│  │  │                              # - Tenant creation
│  │  │                              # - Admin user setup
│  │  ├─ user_approval_service.py    # User approval workflow
│  │  │                              # - Approve/reject users
│  │  ├─ invitation_management_service.py # Invitation lifecycle
│  │  │                              # - Create, send, validate
│  │  ├─ README.md                   # Services documentation
│  │  └─ __init__.py
│
│  ├─ routes/                        # API Endpoint Handlers
│  │  ├─ auth_routes.py              # /api/auth/*
│  │  │                              # - POST /register
│  │  │                              # - POST /login
│  │  │                              # - GET /profile
│  │  │                              # - POST /invitations/send
│  │  │                              # - POST /invitations/validate
│  │  │                              # - POST /invitations/register
│  │  ├─ query_routes.py             # /api/query/*
│  │  │                              # - POST /search (RAG)
│  │  │                              # - GET /cache-stats
│  │  ├─ agent_routes.py             # /api/agent/*
│  │  │                              # - POST /reason (SSE)
│  │  │                              # - GET /runs
│  │  │                              # - GET /runs/{id}
│  │  ├─ ingest_rag_routes.py        # /api/ingest-rag/*
│  │  │                              # - POST /upload
│  │  │                              # - GET /status/{id}
│  │  │                              # - GET /documents
│  │  ├─ eval_rag_routes.py          # /api/eval-rag/*
│  │  │                              # - POST /evaluate
│  │  │                              # - GET /results
│  │  ├─ metrics_routes.py           # /api/metrics
│  │  │                              # - Prometheus metrics endpoint
│  │  ├─ README.md                   # API documentation
│  │  ├─ __init__.py
│  │  └─ schemas.py                  # Request/response Pydantic models
│
│  ├─ controllers/                   # HTTP Request Handlers (optional layer)
│  │  ├─ auth_controller.py          # Auth-related handlers
│  │  ├─ ingest_rag_controller.py    # Ingest-related handlers
│  │  ├─ README.md
│  │  └─ __init__.py
│
│  ├─ design_pattern/                # Design Patterns
│  │  ├─ embedded_model.py           # Singleton pattern
│  │  │                              # - Single embedding model instance
│  │  │                              # - Thread-safe lazy loading
│  │  ├─ llm_singlton.py             # LLM singleton
│  │  │                              # - Shared LLM instance
│  │  ├─ upload_factory.py           # Factory pattern
│  │  │                              # - Dynamic file handler creation
│  │  ├─ upload_factory_pattern/     # Strategy pattern
│  │  │                              # - PDF handler
│  │  │                              # - Markdown handler
│  │  │                              # - JSON handler
│  │  ├─ user_factory.py             # User creation factory
│  │  ├─ README.md                   # Design patterns documentation
│  │  └─ __init__.py
│
│  ├─ celery/                        # Task Queue Configuration
│  │  ├─ celery_config.py            # Celery setup
│  │  │                              # - Broker (RabbitMQ)
│  │  │                              # - Backend (RPC result storage)
│  │  │                              # - Queue definitions
│  │  │                              # - Task routing
│  │  └─ README.md
│
│  ├─ files/                         # File Storage
│  │  ├─ eval_files/                 # Evaluation dataset files
│  │  └─ uploads/                    # User-uploaded documents
│
│  ├─ __init__.py
│  └─ __pycache__/
│
├─ frontend/                         # React SPA
│  ├─ src/
│  │  ├─ components/                 # React components
│  │  ├─ pages/                      # Page components
│  │  ├─ services/                   # API client service
│  │  ├─ hooks/                      # Custom React hooks
│  │  ├─ utils/                      # Utility functions
│  │  ├─ styles/                     # CSS/SCSS files
│  │  ├─ App.js                      # Root component
│  │  └─ index.js                    # Entry point
│  ├─ public/                        # Static assets
│  ├─ build/                         # Production build output
│  ├─ package.json                   # Dependencies
│  ├─ README.md                      # Frontend documentation
│  └─ webpack.config.js              # Build configuration
│
├─ alembic.ini                       # Alembic CLI configuration
├─ docker-compose.yml                # Full local stack (Postgres, Qdrant, Redis)
├─ docker-compose.monitoring.yml     # Monitoring stack (Prometheus, Grafana)
├─ Dockerfile                        # Multi-stage API container build
├─ main.py                           # FastAPI application entry point
├─ logging_setup.py                  # JSON structured logging configuration
├─ requirements.txt                  # Python dependencies
├─ START_MONITORING.bat              # Windows script to start monitoring
├─ verify_metrics.py                 # Utility script for metric verification
├─ fake_metrics.txt                  # Fake data for testing
│
├─ monitoring/                       # Prometheus & Grafana
│  ├─ prometheus.yml                 # Prometheus scrape config
│  ├─ prometheus.monitoring.yml      # Extended monitoring config
│  ├─ grafana/                       # Grafana dashboards
│  │  └─ atlas-monitoring.json       # Main dashboard definition
│  └─ README.md                      # Monitoring documentation
│
├─ mlruns/                           # MLflow experiment tracking (optional)
│  └─ models/                        # Model artifacts
│
├─ diagrams/                         # Architecture diagrams
│
├─ SRS/                              # Software Requirements Specification docs
│
└─ GRAFANA_METRICS_FIX.md            # Grafana troubleshooting guide
```

---

## Installation & Setup

### Prerequisites
- **Python 3.10+** (3.11 recommended)
- **Docker & Docker Compose**
- **PostgreSQL 15** (or via Docker)
- **Redis 7** (or via Docker)
- **Qdrant** (or via Docker)
- **OpenAI API Key**
- **Git**

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd atlas-ai
```

### Step 2: Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables
Create a `.env` file in the root directory:
```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/atlas_db
SQLALCHEMY_ECHO=False

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_DB=1

# Qdrant Vector DB
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=YOUR_API_KEY

# LLM & Embeddings
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4
EMBEDDING_MODEL=all-MiniLM-L6-v2

# JWT & Auth
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=1
BCRYPT_ROUNDS=12

# Celery
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//

# Sentry (Optional)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# CORS
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

# Environment
ENVIRONMENT=development
DEBUG=True
```

### Step 5: Start Docker Services
```bash
# Start all services (Postgres, Redis, Qdrant, Prometheus, Grafana)
docker-compose up -d

# Verify services
docker-compose ps
```

### Step 6: Run Database Migrations
```bash
# Upgrade to latest schema
alembic upgrade head

# Verify migrations
alembic current
```

### Step 7: Initialize Embedding Model (First Time)
```bash
python -c "from app.design_pattern.embedded_model import EmbeddingModel; model = EmbeddingModel.get_instance()"
```

---

## Configuration

### Environment Variables Reference

#### Database Configuration
| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SQLALCHEMY_ECHO` | Log SQL queries for debugging | False |
| `DB_POOL_SIZE` | Max concurrent connections | 20 |
| `DB_POOL_TIMEOUT` | Connection timeout (seconds) | 30 |

#### Cache & Message Queue
| Variable | Purpose | Default |
|----------|---------|---------|
| `REDIS_URL` | Redis connection string | redis://localhost:6379 |
| `REDIS_CACHE_DB` | Redis database for caching | 1 |
| `CELERY_BROKER_URL` | Message broker for task queue | amqp://guest:guest@localhost:5672 |

#### Vector Database
| Variable | Purpose | Default |
|----------|---------|---------|
| `QDRANT_URL` | Qdrant API endpoint | http://localhost:6333 |
| `QDRANT_API_KEY` | Qdrant authentication | - |
| `QDRANT_TIMEOUT` | Request timeout (seconds) | 30 |

#### LLM Integration
| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_MODEL` | Default model for reasoning | gpt-4 |
| `OPENAI_TIMEOUT` | API timeout (seconds) | 60 |
| `EMBEDDING_MODEL` | Sentence Transformers model | all-MiniLM-L6-v2 |

#### Authentication & Security
| Variable | Purpose | Default |
|----------|---------|---------|
| `JWT_SECRET_KEY` | Secret for token signing | - |
| `JWT_ALGORITHM` | Token encoding algorithm | HS256 |
| `JWT_EXPIRATION_HOURS` | Token lifetime | 1 |
| `BCRYPT_ROUNDS` | Password hashing iterations | 12 |

#### Application Settings
| Variable | Purpose | Default |
|----------|---------|---------|
| `ENVIRONMENT` | dev/staging/production | development |
| `DEBUG` | Enable debug mode | False |
| `LOG_LEVEL` | Logging level | INFO |
| `ALLOWED_ORIGINS` | CORS allowed origins | ["http://localhost:3000"] |

---

## Running the Application

### Start Backend Server
```bash
# Development mode with auto-reload
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode (4 workers)
python -m uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

### Start Celery Worker
```bash
# Terminal 2
celery -A app.celery.celery_config worker --loglevel=info
```

### Start Frontend Development Server
```bash
# Terminal 3
cd frontend
npm install
npm start
```

### Access Applications
- **FastAPI Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Frontend**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (user: admin, pass: admin)

### Docker Compose Quick Start
```bash
# Build and start all services
docker-compose up --build

# Stop all services
docker-compose down

# View logs
docker-compose logs -f api
```

---

## API Endpoints

### Authentication (`/api/auth/`)

#### Register New Tenant
```http
POST /api/auth/register
Content-Type: application/json

{
  "company_name": "Acme Corp",
  "admin_email": "admin@acme.com",
  "admin_password": "SecurePassword123!",
  "plan_tier": "pro"
}

Response 201:
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "token": "jwt-token",
  "expires_in": 3600
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@acme.com",
  "password": "password"
}

Response 200:
{
  "token": "jwt-token",
  "user_id": "uuid",
  "tenant_id": "uuid",
  "role": "admin"
}
```

#### Get Current Profile
```http
GET /api/auth/profile
Authorization: Bearer {token}

Response 200:
{
  "user_id": "uuid",
  "email": "user@acme.com",
  "role": "admin",
  "tenant_id": "uuid",
  "approval_status": "approved"
}
```

#### Send User Invitation
```http
POST /api/auth/invitations/send
Authorization: Bearer {admin-token}
Content-Type: application/json

{
  "email": "newuser@acme.com",
  "role": "user"
}

Response 201:
{
  "invitation_id": "uuid",
  "token": "invitation-token",
  "expires_at": "2024-03-25T10:00:00Z"
}
```

#### Validate Invitation
```http
POST /api/auth/invitations/validate
Content-Type: application/json

{
  "token": "invitation-token"
}

Response 200:
{
  "valid": true,
  "email": "newuser@acme.com",
  "expires_at": "2024-03-25T10:00:00Z"
}
```

#### Register via Invitation
```http
POST /api/auth/invitations/register
Content-Type: application/json

{
  "token": "invitation-token",
  "password": "NewPassword123!",
  "first_name": "John",
  "last_name": "Doe"
}

Response 201:
{
  "user_id": "uuid",
  "email": "newuser@acme.com",
  "approval_status": "pending"
}
```

---

### Query & RAG (`/api/query/`)

#### Simple RAG Search
```http
POST /api/query/search
Authorization: Bearer {token}
Content-Type: application/json

{
  "query": "What are the key metrics for Q3 2024?",
  "top_k": 5,
  "use_cache": true
}

Response 200:
{
  "results": [
    {
      "content": "...",
      "metadata": { "source": "document.pdf", "page": 5 },
      "relevance_score": 0.92,
      "cached": false
    }
  ],
  "execution_time_ms": 245,
  "tokens_used": 1500,
  "cost_usd": 0.0225
}
```

#### Cache Statistics
```http
GET /api/query/cache-stats
Authorization: Bearer {token}

Response 200:
{
  "total_queries": 150,
  "cache_hits": 45,
  "cache_hit_rate": 0.30,
  "avg_cache_latency_ms": 2.3,
  "avg_retrieval_latency_ms": 234.5
}
```

---

### Agent Reasoning (`/api/agent/`)

#### Multi-Step Reasoning (SSE Streaming)
```http
POST /api/agent/reason
Authorization: Bearer {token}
Content-Type: application/json

{
  "query": "Analyze our Q3 performance and recommend cost optimization strategies",
  "max_iterations": 10,
  "stream": true
}

Response 200 (Server-Sent Events):
event: agent_start
data: {"run_id": "uuid", "query": "..."}

event: decomposed_questions
data: {"question": "What was Q3 revenue?", "sub_questions": [...]}

event: thought
data: {"thought": "I should retrieve financial documents first"}

event: tool_start
data: {"tool": "retrieval", "query": "Q3 financial results"}

event: tool_result
data: {"documents": [...], "latency_ms": 234}

event: cost_update
data: {"tokens": 1200, "cost_usd": 0.018}

event: agent_finish
data: {"answer": "...", "cost_usd": 0.025, "reasoning": "..."}
```

#### Get Agent Execution Runs
```http
GET /api/agent/runs?page=1&limit=10&start_date=2024-01-01&end_date=2024-03-25
Authorization: Bearer {token}

Response 200:
{
  "total": 45,
  "page": 1,
  "limit": 10,
  "runs": [
    {
      "run_id": "uuid",
      "query": "...",
      "status": "completed",
      "created_at": "2024-03-20T10:15:00Z",
      "tokens_used": 5000,
      "cost_usd": 0.075,
      "latency_ms": 2340,
      "cache_hit": false
    }
  ]
}
```

#### Get Run Details
```http
GET /api/agent/runs/{run_id}
Authorization: Bearer {token}

Response 200:
{
  "run_id": "uuid",
  "query": "...",
  "decomposed_questions": [
    { "question": "Q1", "answer": "A1" },
    { "question": "Q2", "answer": "A2" }
  ],
  "final_answer": "...",
  "reasoning_trace": [...],
  "token_breakdown": { "prompt": 2000, "completion": 3000 },
  "cost_breakdown": { "completion": 0.05, "embedding": 0.025 },
  "execution_time_ms": 2340,
  "status": "completed"
}
```

---

### Document Ingestion (`/api/ingest-rag/`)

#### Upload Document
```http
POST /api/ingest-rag/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

{
  "file": <binary>,
  "document_name": "Q3 Report",
  "tags": ["financial", "2024"]
}

Response 202:
{
  "task_id": "uuid",
  "status": "processing",
  "document_id": "uuid",
  "file_hash": "sha256hash",
  "progress": 0
}
```

#### Check Ingestion Status
```http
GET /api/ingest-rag/status/{document_id}
Authorization: Bearer {token}

Response 200:
{
  "document_id": "uuid",
  "file_name": "Q3 Report.pdf",
  "status": "completed",
  "progress": 100,
  "chunks_created": 245,
  "tokens_used": 12000,
  "created_at": "2024-03-20T10:15:00Z",
  "completed_at": "2024-03-20T10:18:30Z"
}
```

#### List Documents
```http
GET /api/ingest-rag/documents?page=1&limit=20
Authorization: Bearer {token}

Response 200:
{
  "total": 45,
  "documents": [
    {
      "document_id": "uuid",
      "file_name": "Q3 Report.pdf",
      "status": "completed",
      "chunks": 245,
      "created_at": "2024-03-20T10:15:00Z",
      "tags": ["financial", "2024"]
    }
  ]
}
```

---

### Evaluation (`/api/eval-rag/`)

#### Run RAG Evaluation
```http
POST /api/eval-rag/evaluate
Authorization: Bearer {token}
Content-Type: application/json

{
  "eval_dataset_id": "uuid",
  "sample_size": 30
}

Response 202:
{
  "eval_run_id": "uuid",
  "status": "running",
  "progress": 0
}
```

#### Get Evaluation Results
```http
GET /api/eval-rag/results/{eval_run_id}
Authorization: Bearer {token}

Response 200:
{
  "eval_run_id": "uuid",
  "status": "completed",
  "metrics": {
    "retrieval_accuracy": 0.87,
    "answer_relevance": 0.91,
    "answer_completeness": 0.84,
    "latency_avg_ms": 234.5,
    "cost_per_query_usd": 0.025
  }
}
```

---

### Metrics (`/api/metrics`)

#### Prometheus Metrics
```http
GET /api/metrics
Content-Type: text/plain

Response 200:
# HELP atlas_http_requests_total Total HTTP requests
# TYPE atlas_http_requests_total counter
atlas_http_requests_total{method="GET",endpoint="/api/query/search",status="200"} 1250

# HELP atlas_http_request_duration_seconds HTTP request latency
# TYPE atlas_http_request_duration_seconds histogram
atlas_http_request_duration_seconds_bucket{le="0.001",endpoint="/api/query/search"} 50
atlas_http_request_duration_seconds_bucket{le="0.5",endpoint="/api/query/search"} 1200

# HELP atlas_rag_tokens_total RAG token consumption
# TYPE atlas_rag_tokens_total counter
atlas_rag_tokens_total{model="gpt-4",type="prompt"} 125000
atlas_rag_tokens_total{model="gpt-4",type="completion"} 75000

# ... [more metrics]
```

---

## Core Features & Components

### 1. Multi-Tenant Architecture

Every operation is tenant-scoped:

**User Registration**
```
/api/auth/register
├─ Create Tenant record
├─ Create Admin User (approved)
├─ Generate JWT with tenant_id claim
└─ Return token
```

**Tenant Isolation**
- Every table has `tenant_id` column
- Every query filters by `tenant_id` (from JWT)
- Users can only access their tenant's data
- Queries are SQL-injected with: `WHERE tenant_id = ?`

**Exemplary Code** (from `repositories/user_repository.py`):
```python
def get_users(self, tenant_id: UUID) -> List[User]:
    return self.db.query(User).filter(
        User.tenant_id == tenant_id
    ).all()
```

---

### 2. Role-Based Access Control (RBAC)

Three role levels with graduated permissions:

| Role | Permissions |
|------|-------------|
| **Admin** | ✅ All endpoints, user management, invitations, approvals |
| **User** | ✅ Query, ingest, agent reasoning; ❌ No user management |
| **Viewer** | ✅ Query only; ❌ No ingest, no agent, no management |

**Rate Limiting by Role**
- Admin: 300 requests/minute
- User: 100 requests/minute  
- Viewer: 20 requests/minute

---

### 3. User Approval Workflow

**Step-by-Step Process**

1. **Tenant Registration** (Public)
   - New company signs up via `/api/auth/register`
   - Creates tenant + admin user
   - Admin user is auto-approved

2. **Invitation Creation** (Admin only)
   - Admin sends invite: `/api/auth/invitations/send`
   - Creates `Invitation` record with 7-day expiration
   - Generates secure token

3. **User Registration** (Public)
   - New user clicks email link with token
   - Posts to `/api/auth/invitations/register`
   - Creates user with `approval_status = "pending"`

4. **Admin Approval** (Admin only)
   - Admin reviews pending users
   - Approves: `approval_status = "approved"` → User can login
   - Rejects: `approval_status = "rejected"` → User blocked

**Database Flow**
```
Invitations table:
├─ token: invitation-token-xyz
├─ email: newuser@acme.com
├─ expires_at: 2024-03-25T10:00:00Z
├─ status: pending → accepted → completed
└─ created_by: admin-user-uuid

Users table (after registration via invitation):
├─ user_id: uuid
├─ email: newuser@acme.com
├─ approval_status: pending → approved
├─ role: user
└─ created_at: 2024-03-20T10:15:00Z
```

---

### 4. JWT Authentication

**Token Structure**
```
Headers: {"alg": "HS256", "typ": "JWT"}
Payload: {
  "sub": "user-uuid",          # User ID
  "tenant_id": "tenant-uuid",  # Multi-tenancy claim
  "email": "user@acme.com",
  "role": "admin",
  "exp": 1711000000            # Expires 1 hour from issue
}
Signature: HMACSHA256(header.payload, SECRET_KEY)
```

**Flow**
```
User Login (email/password)
    ↓
Verify password against bcrypt hash
    ↓
Extract user details + role + tenant_id
    ↓
Create JWT with 1-hour expiration
    ↓
Return token to client
    ↓
Client stores in localStorage
    ↓
Client includes in Authorization header: Bearer {token}
    ↓
Server verifies token in middleware
    ├─ ✅ Valid → Extract claims, continue
    └─ ❌ Invalid/Expired → Return 401 Unauthorized
```

---

## Database Schema

### Core Tables

#### Users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) NOT NULL,  -- admin, user, viewer
    approval_status VARCHAR(50), -- pending, approved, rejected
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
```

#### Tenants
```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    plan_tier VARCHAR(50),  -- free, pro, enterprise
    subscription_status VARCHAR(50),  -- active, trial, cancelled
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tenants_company_name ON tenants(company_name);
```

#### Runs (Agent Executions)
```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    query TEXT NOT NULL,
    agent_type VARCHAR(50),  -- reasoning, retrieval
    status VARCHAR(50),  -- running, completed, failed
    decomposed_questions JSONB,
    observations JSONB,
    final_answer TEXT,
    tokens_used INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms FLOAT,
    cache_hit BOOLEAN DEFAULT FALSE,
    cost_usd DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_runs_tenant_id ON runs(tenant_id);
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);
```

#### CostLog (Billing)
```sql
CREATE TABLE cost_logs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    run_id UUID,
    cost_type VARCHAR(50),  -- completion, embedding, retrieval
    model_used VARCHAR(100),
    token_count INTEGER,
    cost_usd DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX idx_cost_logs_tenant_id ON cost_logs(tenant_id);
CREATE INDEX idx_cost_logs_created_at ON cost_logs(created_at DESC);
```

#### Documents (Processed Files)
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64),  -- SHA-256 for deduplication
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    status VARCHAR(50),  -- pending, processing, completed, failed
    chunk_count INTEGER,
    tokens_total INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX idx_documents_file_hash ON documents(file_hash);
```

#### Invitations (User Onboarding)
```sql
CREATE TABLE invitations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    created_by_user_id UUID NOT NULL,
    email VARCHAR(255) NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50),  -- pending, accepted, expired, revoked
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE INDEX idx_invitations_tenant_id ON invitations(tenant_id);
CREATE INDEX idx_invitations_email ON invitations(email);
CREATE INDEX idx_invitations_token ON invitations(token);
```

#### TRACKER_DB_FILE (File Processing)
```sql
CREATE TABLE tracker_db_files (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    document_id UUID NOT NULL,
    file_path VARCHAR(500),
    status VARCHAR(50),  -- uploaded, parsing, embedding, completed, failed
    progress_percentage INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_tracker_tenant_id ON tracker_db_files(tenant_id);
```

---

## RAG Pipeline

### Ingestion Pipeline (Document Upload)

**Flow Diagram**
```
User Uploads File
    ↓
Validate file type & size
├─ Supported: PDF, Markdown, JSON, TXT
├─ Max size: 50MB
└─ Check quota usage
    ↓
Compute file hash (SHA-256)
├─ Query Documents table: SELECT * WHERE file_hash = ?
└─ If exists → Return existing document (deduplication)
    ↓
Parse document
├─ PDF: PyPDF2 extraction
├─ Markdown: Direct parsing
├─ JSON: Field extraction
└─ TXT: Line-by-line parsing
    ↓
Semantic chunking
├─ Split on paragraph boundaries
├─ Respect token limits (max 512 tokens per chunk)
├─ Include overlap for context (50 tokens pad)
└─ Preserve metadata (page, section, source)
    ↓
Embed chunks
├─ Batch embed 32 chunks at a time (efficient GPU usage)
├─ Model: all-MiniLM-L6-v2
├─ Output: 384-dim dense vectors
└─ Track token usage for billing
    ↓
Upsert to Qdrant
├─ Create collection if needed (4 shards, 1 replica)
├─ Upsert vectors with metadata
├─ Metadata: chunk_id, page, section, source, tenant_id
└─ Enable tenant filtering in search
    ↓
Save document record
├─ Create Documents table entry
├─ Set status: completed
├─ Store chunk_count, token_count
└─ Record completion time
    ↓
Async logging (Celery)
└─ Log ingestion metrics
```

**Example Request**
```python
POST /api/ingest-rag/upload

# Result in databases:
PostgreSQL Documents:
{
    "id": "doc-uuid",
    "tenant_id": "tenant-uuid",
    "file_name": "Q3_Financial_Report.pdf",
    "file_hash": "sha256..."
    "status": "completed",
    "chunk_count": 245
}

Qdrant Collection "documents_tenant-uuid":
[
    {
        "id": "chunk-001",
        "vector": [0.123, -0.456, ...],  # 384 dimensions
        "metadata": {
            "doc_id": "doc-uuid",
            "page": 5,
            "section": "Financial Results",
            "source": "Q3_Financial_Report.pdf",
            "tenant_id": "tenant-uuid"
        }
    },
    ...  # 245 chunks total
]
```

---

### Retrieval Pipeline (Query Processing)

**3-Tier Caching**
```
User Query
    ↓
TIER 1: In-Memory RAM Cache
├─ Fastest (sub-millisecond)
├─ Limited size (128MB default)
├─ Exact query match lookup
└─ ✅ Hit → Return cached results + cost
    ↓ (MISS)
TIER 2: Redis Semantic Cache
├─ Fast (10-50ms)
├─ Distributed across cluster
├─ Cosine similarity threshold 0.95
├─ Cached embedding vectors
└─ ✅ Hit → Return cached results + cost
    ↓ (MISS)
TIER 3: Full Retrieval (No cache)
└─ Full database/API access required
```

**Flow Diagram**
```
Checked all caches → MISS
    ↓
Generate Query Embedding
├─ Model: all-MiniLM-L6-v2
├─ Same encoder as documents
└─ Output: 384-dim vector
    ↓
Hybrid Search (Qdrant)
├─ Dense Vector Search (cosine similarity)
│  ├─ Query vector vs document vectors
│  └─ Return top 10 by similarity
│
├─ Sparse BM25 Search (keyword matching)
│  ├─ Tokenize query
│  ├─ BM25 scoring vs documents
│  └─ Return top 10 by BM25 score
│
└─ Merge results (dedup by doc_id)
    ↓
Cross-Encoder Reranking
├─ Model: ms-marco-MiniLM-L-6-v2
├─ Score: (query, document) → relevance [0-1]
├─ Rerank by relevance score
└─ Return top-k (default: 5)
    ↓
Generate LLM Response
├─ Prompt: "{query}\n\nDocuments:\n{reranked_docs}"
├─ Model: GPT-4 or GPT-3.5-Turbo
├─ Stream response token-by-token
└─ Track tokens for billing
    ↓
Cache Result (Async)
├─ Save to Redis (24-hour TTL)
├─ Save to PostgreSQL (long-term analytics)
└─ Log costs to CostLog table
    ↓
Return to User
└─ Include: results, cost, latency, cache_hit flag
```

**Example Query**

Input:
```json
{
  "query": "What were our key financial metrics in Q3?",
  "top_k": 5,
  "use_cache": true
}
```

Cache Check Result:
```json
{
  "cache_tier": 2,
  "latency_ms": 23,
  "cached": true,
  "results": [
    {
      "content": "Q3 Revenue: $2.5M, up 15% YoY...",
      "relevance_score": 0.94,
      "source": "Q3_Report.pdf",
      "page": 3
    },
    ...
  ],
  "tokens_used": 0,
  "cost_usd": 0.0
}
```

---

### Reranking Strategies

**Cross-Encoder (Primary)**
- Neural model: `ms-marco-MiniLM-L-6-v2`
- Input: (query, document_text) pair
- Output: Relevance score [0-1]
- Latency: ~2ms per document
- Handles semantic nuances

**BM25 Fallback**
- Lexical matching: keyword overlap
- TF-IDF + document length normalization
- Fast (< 1ms per document)
- Used if cross-encoder unavailable
- Good for exact phrase matching

**Hybrid Scoring**
```
final_score = 0.7 * cross_encoder_score + 0.3 * bm25_score
```

---

## Agent System

### Multi-Step Reasoning with LangGraph

**State Machine**
```
graph = StateGraph(AgentState)

graph.add_node("decompose", decompose_questions)
    # Input: question
    # Output: decomposed_questions = [Q1, Q2, Q3, ...]

graph.add_node("thought", think_node)
    # Input: question, decomposed_questions, observations
    # Output: next_action = ("retrieve" | "sql" | "finish")

graph.add_node("retrieval", retrieve_documents)
    # Input: question, observations
    # Output: documents, updated observations

graph.add_node("sql", execute_sql)
    # Input: question, observations
    # Output: result, updated observations

graph.add_node("finish", format_answer)
    # Input: question, observations
    # Output: final_answer

graph.add_edge("decompose", "thought")
graph.add_conditional_edges(
    source="thought",
    path=lambda state: state["next_action"],
    conditional_map={
        "retrieve": "retrieval",
        "sql": "sql",
        "finish": "finish"
    }
)
graph.add_edge("retrieval", "thought")  # Loop back
graph.add_edge("sql", "thought")        # Loop back
graph.add_edge("finish", END)
```

**Execution Trace Example**

```
Query: "Analyze Q3 sales trends and compare with Q2"
    │
    ├─► DECOMPOSE
    │   └─ Sub-questions:
    │       1. What were Q3 sales figures?
    │       2. What were Q2 sales figures?
    │       3. What are the differences?
    │
    ├─► THOUGHT
    │   └─ "I should retrieve sales data for both quarters"
    │       next_action: "retrieve"
    │
    ├─► RETRIEVAL
    │   ├─ Query: "Q3 sales figures"
    │   ├─ Retrieved: 3 documents with sales data
    │   └─ Observation 1: "Q3 sales were $2.5M, up 15% QoQ"
    │
    ├─► THOUGHT
    │   └─ "Need Q2 data for comparison"
    │       next_action: "retrieve"
    │
    ├─► RETRIEVAL
    │   ├─ Query: "Q2 sales figures"
    │   ├─ Retrieved: 2 documents
    │   └─ Observation 2: "Q2 sales were $2.17M"
    │
    ├─► THOUGHT
    │   └─ "Have enough data to answer. Formulating response..."
    │       next_action: "finish"
    │
    ├─► FINISH
    │   └─ Answer: "Q3 sales increased 15% to $2.5M compared to Q2's $2.17M..."
    │
    └─► COMPLETE
        ├─ Total tokens: 5000
        ├─ Cost: $0.075
        ├─ Latency: 2340ms
        └─ Saved to Runs table
```

**Real-Time Streaming (SSE)**

The frontend receives these events as agent runs:

```javascript
// Client-side EventSource
const eventSource = new EventSource('/api/agent/reason', {
  headers: { 'Authorization': `Bearer ${token}` }
});

eventSource.addEventListener('decomposed_questions', (e) => {
  const { question, sub_questions } = JSON.parse(e.data);
  uiUpdateSubQuestions(sub_questions);
});

eventSource.addEventListener('thought', (e) => {
  const { thought } = JSON.parse(e.data);
  uiAppendThought(thought);  // Real-time display
});

eventSource.addEventListener('tool_start', (e) => {
  const { tool, query } = JSON.parse(e.data);
  uiShowLoading(`Executing ${tool}...`);
});

eventSource.addEventListener('tool_result', (e) => {
  const { documents, latency_ms } = JSON.parse(e.data);
  uiDisplayResults(documents);
});

eventSource.addEventListener('agent_finish', (e) => {
  const { answer, cost_usd } = JSON.parse(e.data);
  uiDisplayFinalAnswer(answer);
  uiDisplayCost(cost_usd);
});
```

---

## Monitoring & Observability

### Prometheus Metrics Collection

**HTTP Metrics** (`app/core/monitors.py`)

```python
atlas_http_requests_total = Counter(
    'atlas_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

atlas_http_request_duration_seconds = Histogram(
    'atlas_http_request_duration_seconds',
    'HTTP request latency',
    ['endpoint'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0)
)
```

**RAG Metrics** (from `app/core/metrics.py`)

```python
rag_token_usage_total = Counter(
    'atlas_rag_tokens_total',
    'RAG token consumption',
    ['model', 'type']  # type: prompt, completion, embedding
)

rag_process_latency_seconds = Histogram(
    'atlas_rag_latency_seconds',
    'RAG step latency',
    ['step']  # step: retrieval, reranking, generation
)

rag_cache_hits_total = Counter(
    'atlas_rag_cache_hits_total',
    'Cache hit count',
    ['tier']  # tier: memory, redis, database
)
```

### Grafana Dashboards

**Main Dashboard**: `monitoring/grafana/atlas-monitoring.json`

**Panels**:
1. **System Health** (CPU, Memory, Disk)
2. **API Traffic** (Requests/sec, Endpoint breakdown, Status codes, Latency p95/p99)
3. **LLM Consumption** (Tokens used, Costs in USD, Model breakdown)
4. **Agent Analytics** (Avg steps per query, Sub-questions parsed, Reasoning latency)
5. **RAG Insights** (Retrieval latency, Chunk count, Cache hit rate)

**Access**
```
URL: http://localhost:3000
User: admin
Password: admin
```

### Error Tracking (Sentry)

**Configuration** (in `main.py`)
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    integrations=[FastApiIntegration()],
    environment=settings.ENVIRONMENT,
    traces_sample_rate=0.1  # 10% of transactions
)
```

**Features**
- Automatic exception capturing
- Request context (user, tenant_id, headers)
- Transaction tracking (performance monitoring)
- Release tracking (version management)

---

## Development Guide

### Project Setup for Development

```bash
# 1. Clone & setup
git clone <repo>
cd atlas-ai
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .  # Install in editable mode

# 3. Start services
docker-compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Start development server
python -m uvicorn main:app --reload
```

### Code Organization Best Practices

**Layered Architecture**
```
Routes (API handlers)
    ↓
Services (Business logic)
    ↓
Repositories (Data access)
    ↓
Models (Database/ORM)
```

**Example: Adding a New Feature**

1. **Create Model** (`app/models/`)
```python
class NewFeature(Base):
    __tablename__ = "new_features"
    id: UUID = Column(UUID)
    tenant_id: UUID = Column(UUID, ForeignKey("tenants.id"))
    # ... fields
```

2. **Create Repository** (`app/repositories/new_feature_repository.py`)
```python
class NewFeatureRepository:
    def __init__(self, db):
        self.db = db
    
    def create(self, tenant_id, data) -> NewFeature:
        # Implementation
        pass
```

3. **Create Service** (`app/services/new_feature_service.py`)
```python
class NewFeatureService:
    def __init__(self, repo: NewFeatureRepository):
        self.repo = repo
    
    def process_feature(self, tenant_id, data):
        # Business logic
        return self.repo.create(tenant_id, data)
```

4. **Create Route** (`app/routes/new_feature_routes.py`)
```python
@router.post("/new-feature")
async def create_new_feature(
    data: NewFeatureSchema,
    current_user: User = Depends(get_current_user)
):
    service = NewFeatureService(repo)
    return await service.process_feature(current_user.tenant_id, data)
```

### Testing

**Unit Tests**
```bash
# Run tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=app
```

**Integration Tests**
```bash
# Start test database
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/ -v
```

**Test Structure**
```
tests/
├─ conftest.py              # Pytest fixtures
├─ unit/
│  ├─ test_repositories.py
│  ├─ test_services.py
│  └─ test_utils.py
└─ integration/
   ├─ test_api_endpoints.py
   └─ test_workflows.py
```

### Alembic Database Migrations

**Creating a Migration**
```bash
# Auto-generate based on model changes
alembic revision --autogenerate -m "Add new field to users table"

# Edit the generated file in alembic/versions/

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Code Style & Linting

```bash
# Format code
black app/

# Lint
flake8 app/

# Type checking
mypy app/

# Security scan
bandit -r app/
```

---

## Deployment

### Production Checklist

- [ ] Set `.env` with production secrets
- [ ] Enable SSL/HTTPS (NGINX reverse proxy)
- [ ] Use strong JWT_SECRET_KEY (128+ char random)
- [ ] Configure database backups
- [ ] Set up error tracking (Sentry)
- [ ] Enable monitoring (Prometheus + Grafana)
- [ ] Configure CORS for frontend domain
- [ ] Set `DEBUG = False`
- [ ] Use database connection pooling
- [ ] Enable rate limiting
- [ ] Set up logging aggregation (ELK stack optional)

### Docker Deployment

**Build Production Image**
```bash
docker build -t atlas-ai:latest \
  --build-arg ENVIRONMENT=production \
  .
```

**Docker Compose Production**
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Health Checks**
```bash
# Check API health
curl http://localhost:8000/health

# Check database
docker-compose exec postgres psql -U postgres -d atlas_db -c "SELECT 1"

# Check Qdrant
curl http://localhost:6333/health

# Check all services
docker-compose ps
```

### Kubernetes Deployment (Optional)

[Helm charts and K8s manifests in `k8s/` directory]

```bash
helm install atlas-ai ./helm-chart \
  --set image.tag=latest \
  --set environment=production \
  --values k8s/values-prod.yaml
```

---

## Troubleshooting

### Common Issues

#### 1. **Database Connection Error**
```
Error: Connection refused on postgresql://localhost:5432/atlas_db
```

**Solution**:
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check connection string in .env
echo $DATABASE_URL

# Test connection
psql postgresql://user:password@localhost:5432/atlas_db
```

#### 2. **Qdrant Connection Error**
```
Error: Failed to connect to Qdrant at http://localhost:6333
```

**Solution**:
```bash
# Verify Qdrant is running
curl http://localhost:6333/health

# Check Qdrant logs
docker-compose logs qdrant

# Verify API key
echo $QDRANT_API_KEY
```

#### 3. **Redis Cache Issues**
```
Error: Redis connection refused
```

**Solution**:
```bash
# Check Redis status
redis-cli ping

# Clear cache (if needed)
redis-cli FLUSHDB

# Restart Redis
docker-compose restart redis
```

#### 4. **OpenAI API Errors**
```
Error: Invalid API key provided
```

**Solution**:
```bash
# Verify API key
echo $OPENAI_API_KEY

# Test API
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

#### 5. **Migration Errors**
```
Error: Alembic revision not found
```

**Solution**:
```bash
# Check current version
alembic current

# View migration history
alembic history

# Downgrade and retry
alembic downgrade base
alembic upgrade head
```

### Debug Mode

Enable detailed logging:
```bash
# In .env
LOG_LEVEL=DEBUG
SQLALCHEMY_ECHO=True
```

---

## Contributing

### Branch Naming Convention
```
feature/description
bugfix/description
hotfix/description
docs/description
```

### Commit Message Format
```
[TYPE] Short description

Longer explanation if needed.

Fixes #issue-number
```

Types: `feature`, `bugfix`, `hotfix`, `docs`, `refactor`, `test`

### Pull Request Process

1. Create feature branch from `main`
2. Make atomic commits
3. Write/update tests
4. Update README if needed
5. Create PR with description
6. Wait for CI/CD + code review
7. Merge to `main`

### Code Review Checklist

- [ ] Code follows project style
- [ ] Tests pass (unit + integration)
- [ ] No security vulnerabilities
- [ ] Documentation updated
- [ ] Performance acceptable

---

## Appendix

### Glossary

| Term | Definition |
|------|-----------|
| **RAG** | Retrieval-Augmented Generation - LLM + vector database combo |
| **Agent** | Autonomous LangGraph-based reasoning system |
| **Embedding** | Dense vector representation of text (384 dims) |
| **Chunk** | Semantic unit of document (one row in Qdrant) |
| **Vector DB** | Qdrant - optimized for nearest-neighbor search |
| **SSE** | Server-Sent Events - unidirectional real-time streaming |
| **Tenant** | Organization/customer isolated from others |
| **JWT** | JSON Web Token - stateless authentication |
| **Celery** | Task queue for async processing |
| **BM25** | Lexical text matching algorithm |
| **Cross-Encoder** | Neural model for ranking relevance |

### Performance Benchmarks (Expected)

| Operation | Latency |
|-----------|---------|
| User Login | 50-100ms |
| Simple RAG Query (cached) | 2-10ms |
| RAG Query (retrieval) | 200-400ms |
| Agent Reasoning (2-3 steps) | 2-5 seconds |
| Document Ingestion (100 pages) | 30-60 seconds |
| Embedding 100 chunks | 100-300ms |

### Resource Requirements

**Minimum (Dev)**
- CPU: 2 cores
- RAM: 4GB
- Disk: 20GB

**Recommended (Prod)**
- CPU: 8+ cores
- RAM: 16GB+
- Disk: 100GB+ (SSD)

---

##Support & Documentation

- **Issues**: Report bugs on GitHub Issues
- **Discussions**: Ask questions in GitHub Discussions
- **Docs**: See `/app/*/README.md` for component-specific docs
- **Architecture**: See `diagrams/` folder for visual architecture
- **API Docs**: Access at `/docs` when server is running

---

**Last Updated**: March 2024  
**Version**: 1.0.0  
**Maintainers**: Atlas AI Team
