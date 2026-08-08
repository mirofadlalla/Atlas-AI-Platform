# Atlas AI RAG Pipeline - Complete Documentation

**Module**: `app/rag`  
**Purpose**: Retrieval-Augmented Generation pipeline  
**Last Updated**: March 2026

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [3-Tier Caching System](#3-tier-caching-system)
4. [Document Ingestion Pipeline](#document-ingestion-pipeline)
5. [Query Retrieval Pipeline](#query-retrieval-pipeline)
6. [Cross-Encoder Reranking](#cross-encoder-reranking)
7. [File Structure](#file-structure)
8. [API Integration](#api-integration)
9. [Monitoring & Metrics](#monitoring--metrics)
10. [Configuration](#configuration)
11. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The RAG (Retrieval-Augmented Generation) module enables the Atlas AI platform to store, retrieve, and reason over large document collections using state-of-the-art hybrid search and semantic understanding.

### Key Capabilities

✅ **Hybrid Semantic Search**
- Dense embeddings (Sentence Transformers) for semantic similarity
- Sparse embeddings (BM25) for keyword matching
- Combined scoring for best-of-both-worlds retrieval

✅ **Intelligent Caching** ⭐ **NEW**
- Local RAM cache for sub-millisecond repeated queries
- Redis semantic cache with embedding similarity matching (0.2 cosine threshold)
- Database cache for long-term persistence and analytics

✅ **Advanced Reranking**
- Cross-Encoder neural reranking (ms-marco-MiniLM-L-6-v2)
- BM25 lexical scoring as fallback
- Hybrid reranking strategies

✅ **Tenant Isolation**
- Every document tagged with `tenant_id`
- Query results automatically filtered by tenant
- Complete data separation at query time

✅ **Enterprise Features**
- Document deduplication via file hashing
- Semantic chunking with intelligent boundaries
- Processing status tracking
- Comprehensive metrics & monitoring

---

## 🏗️ Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│         User Query / Document Upload                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
   ┌─────────────┐             ┌──────────────┐
   │  INGESTION  │             │  RETRIEVAL   │
   └─────────────┘             └──────────────┘
        │                             │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │      3-TIER CACHE          │
        ├─────────────────────────────┤
        │ 1. RAM (_query_cache)       │
        │ 2. Redis (Semantic Cache)   │
        │ 3. PostgreSQL (Persistent)  │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  VECTOR SEARCH LAYER                │
        ├─────────────────────────────────────┤
        │  Qdrant Hybrid Index:                │
        │  ├─ Dense (Sentence Transformers)   │
        │  └─ Sparse (BM25)                   │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ CROSS-ENCODER RERANKING     │
        │ (ms-marco-MiniLM-L-6-v2)    │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  LLM Synthesis (OpenAI)     │
        │  + Cost Tracking            │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │  Return Result to User          │
        │  Log Metrics to Prometheus      │
        └─────────────────────────────────┘
```

---

## 💾 3-Tier Caching System ⭐ **NEW & IMPORTANT**

The RAG pipeline implements a sophisticated 3-layer caching strategy to minimize latency and reduce costs:

### 1. **Level 1: RAM Cache (In-Memory)**

**Purpose**: Sub-millisecond response time for identical repeated queries

**Implementation** (in `retrivel_data_pipline.py`):
```python
_query_cache = {}              # Dictionary with TTL tracking
_query_cache_ttl = 3600        # 1 hour expiration
```

**How It Works**:
1. When query arrives, compute query hash using `hashlib.md5(query + tenant_id)`
2. Check `_query_cache` dictionary
3. If found AND not expired → return immediately (< 1ms)
4. If not found or expired → proceed to level 2

**Performance**: 
- ✅ Fastest (sub-millisecond)
- ✅ No network overhead
- ❌ Lost on process restart
- ❌ Not shared across workers

**Typical hit rate**: 5-10% (same query repeated within session)

### 2. **Level 2: Redis Semantic Cache**

**Purpose**: Persistent cache across workers with semantic similarity matching

**Technology**: exact-key in-process answer cache; semantic similarity is used
only for document retrieval and long-term memory, never to reuse final answers.

**How It Works**:
1. Generate embedding vector for query (384-dimensional)
2. Call Redis semantic cache with embedding + threshold (default: 0.2 cosine)
3. Redis performs vector similarity search on stored embeddings
4. If match found above threshold → return cached result
5. If no match → proceed to vector database search

**Configuration** (in `retrivel_data_pipline.py`):
```python
from langchain_redis import RedisSemanticCache

redis_cache = RedisSemanticCache(
    redis_url=settings.REDIS_URL_NO_DB,
    embedding=embedding_model,
    score_threshold=0.2  # Cosine similarity threshold
)
```

**Performance**:
- ✅ Semantic matching (not just exact strings)
- ✅ Shared across all workers
- ✅ Persistent across restarts
- ✅ Reduces redundant LLM calls by 60-80%
- ❌ Network roundtrip adds 10-50ms

**Typical hit rate**: 40-60% (semantic similar queries)

**Cost savings**: Eliminates 60-80% of embedding API calls

### 3. **Level 3: PostgreSQL Persistent Cache**

**Purpose**: Long-term storage for analytics, billing, and audit trails

**Storage** (in `Runs` and `CostLog` tables):
- Store query text, embeddings, results, and metrics
- Enable historical analysis and cost breakdown
- Support compliance auditing

**Characteristics**:
- ✅ Long-term persistence
- ✅ Supports analytics queries
- ❌ Slowest (50-200ms per lookup)

**Cache Hit Rates & Performance**:
| Cache Level | Latency | Cost Reduction | Hit Rate |
|------------|---------|---|---|
| RAM Hit | < 1ms | 100% | 5-10% |
| Redis Hit | 10-50ms | 85-95% | 40-60% |
| DB Hit | 50-200ms | 0% (time saved) | 20-40% |
| Cache Miss | 500-2000ms | 0% | 5-20% |

---

## 📥 Document Ingestion Pipeline

### Step-by-Step Flow

```
1. FILE UPLOAD → Assign unique file_id
2. DEDUPLICATION CHECK → MD5 hash, check if processed
3. DOCUMENT LOADING → PDF/TXT/DOCX parsing
4. SEMANTIC CHUNKING → Intelligent splitting (512 tokens, 64 overlap)
5. METADATA ENRICHMENT → Add tenant_id, source, author
6. EMBEDDING GENERATION → Dense (Sentence Transformers) + Sparse (BM25)
7. VECTOR INDEX INSERTION → Upsert to Qdrant hybrid index
8. POSTGRES STORAGE → Store chunks and documents
9. STATUS UPDATE → Mark processing complete
10. ASYNC NOTIFICATION → Websocket update to user
```

**File**: `ingest_data_pipline.py`

### Key Features

- **Deduplication**: Hash-based duplicate detection across uploads
- **Semantic Chunking**: Intelligent sentence/paragraph boundary detection
- **Timeout Protection**: 900-second timeout with token-based fallback
- **Hybrid Embeddings**: Dense (384-dim) + Sparse (BM25) simultaneously
- **Tenant Isolation**: Each tenant's documents completely isolated
- **Multi-format Support**: PDF, TXT, DOCX processing

---

## 🔍 Query Retrieval Pipeline

### Step-by-Step Flow

```
1. USER QUERY → "What was the Q4 revenue?"
2. EMBEDDING GENERATION → Convert to 384-dim vector
3. CHECK CACHING LAYERS → RAM → Redis → Database
4. QDRANT HYBRID SEARCH → Dense + Sparse scoring
5. CROSS-ENCODER RERANKING → Neural fine-grained scoring
6. CHUNK SELECTION → Select top-K (e.g., top-3)
7. LLM GENERATION → Generate answer with context
8. CACHING RESULTS → Store in all 3 cache layers
9. METRICS LOGGING → Push to Prometheus
```

**File**: `retrivel_data_pipline.py`

### Implementation Highlights

**Hybrid Search Scoring**:
```python
hybrid_score = 0.7 * dense_score + 0.3 * sparse_score
```

**Reranking Integration**:
- Takes top-50 from hybrid search
- Cross-encoder provides fine-grained relevance scores (0.0-1.0)
- Returns re-sorted top-3 to LLM

---

## 🎯 Cross-Encoder Reranking

**Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2`

**Purpose**: Refine search results with neural similarity scoring

**How It Works**:
1. Takes (query, chunk) pairs from hybrid search (top-50)
2. Scores each pair with cross-encoder (0.0 = irrelevant, 1.0 = perfect)
3. Re-sorts by refined scores
4. Returns top-K (typically 3) to LLM

**File**: `reranker.py`

**Strategies**:
- `"cross-encoder"` - Neural model only
- `"bm25"` - Keyword matching only  
- `"hybrid"` - Blend both (default)

---

## 📁 File Structure

```
app/rag/
├── README.md                         ← You are here
├── ingest_data_pipline.py           # Document ingestion orchestration
├── retrivel_data_pipline.py         # Query retrieval + 3-tier caching
├── reranker.py                       # Cross-encoder reranking service
│
├── steps/
│   ├── loader.py                    # Document loading (PDF/TXT/DOCX)
│   ├── ingest.py                    # Ingestion sub-steps
│   ├── retriever.py                 # Qdrant retriever initialization
│   ├── file_tracker.py              # Deduplication & MD5 hashing
│   ├── semantic_chunking.py         # Intelligent document chunking
│   └── ...
│
├── data/
│   └── sample.pdf                   # Sample documents for testing
│
└── evaluation/
    ├── eval_queries.py              # Query evaluation suite
    ├── metrics.py                   # BLEU, ROUGE, etc.
    └── datasets/
```

---

## 🔌 API Integration

### Document Ingestion

```bash
POST /api/ingest-rag/upload
Authorization: Bearer <token>

Response: {
  "file_id": "uuid-abc-123",
  "chunks_created": 42,
  "status": "processing"
}
```

### RAG Query

```bash
POST /api/query/search
Authorization: Bearer <token>
Body: {
  "query": "What was Q4 revenue?",
  "use_cache": true,
  "use_reranker": true
}

Response: {
  "answer": "The Q4 revenue was $5.2M...",
  "sources": [...chunks...],
  "cache_hit": false,
  "duration_ms": 234
}
```

---

## 📊 Monitoring & Metrics

**Prometheus Metrics**:
- `atlas_cache_hits_total{level="ram|redis|db"}`
- `atlas_cache_misses_total`
- `atlas_vector_search_duration_seconds`
- `atlas_retrieved_chunks_count`
- `atlas_reranking_queries_total`
- `atlas_llm_cost_usd_total`

**Grafana Dashboards**:
- Cache hit ratio by level
- Vector search latency (p50, p95, p99)
- Documents ingested per tenant
- Cost per query (by tenant)

---

## ⚙️ Configuration

```bash
# .env file
SEMANTIC_CHUNKING_TIMEOUT=900             # seconds
DEFAULT_CHUNK_SIZE=512                    # tokens
DEFAULT_CHUNK_OVERLAP=64                  # tokens
RERANKER_STRATEGY=cross-encoder          # Options: cross-encoder|bm25|hybrid 
REDIS_PASSWORD=atlas_redis_password
CACHE_LEVEL_1_TTL=3600                   # RAM cache TTL (seconds)
CACHE_LEVEL_2_SIMILARITY_THRESHOLD=0.2   # Redis semantic threshold
```

---

## 🐛 Troubleshooting

### Cache not working
- Check Redis: `docker-compose exec redis redis-cli ping`
- Clear cache: `docker-compose exec redis redis-cli FLUSHDB`

### Qdrant returning no results
- Check connection: `curl http://localhost:6333/health`
- Verify documents ingested: `curl http://localhost:6333/collections/documents/points/count`

### High query latency (2000ms+)
- Check metrics: Look for slow steps in vector_search_duration_seconds
- Reduce reranker candidates or disable reranking
- Check LLM API status

---

**Version**: 2.0.0  
**Last Updated**: March 2026  
**Key Feature**: 3-Tier Caching System with Redis Semantic Cache
