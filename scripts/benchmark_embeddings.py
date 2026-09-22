#!/usr/bin/env python3
"""
Embedding Provider Benchmark — Atlas-AI Platform
=================================================

Measures latency and resource usage for:
  A. Jina AI embeddings (remote API)
  B. BGE-M3 embeddings (local SentenceTransformer on CPU)

Usage
-----
  # Benchmark both providers (requires JINA_API_KEY in env or .env):
  python scripts/benchmark_embeddings.py --provider both

  # Benchmark only BGE-M3 on CPU:
  python scripts/benchmark_embeddings.py --provider bge-m3

  # Benchmark only Jina AI:
  python scripts/benchmark_embeddings.py --provider jina

  # Use a larger batch and more iterations:
  python scripts/benchmark_embeddings.py --provider both --batch-size 64 --iterations 20

  # Save results to JSON:
  python scripts/benchmark_embeddings.py --provider both --output results.json

Notes
-----
- This script is SAFE to run in production: it uses synthetic benchmark texts
  and does NOT read from or write to any database, Qdrant, or Redis.
- API keys are read from the environment or .env file.  They are NEVER printed
  to stdout, logs, or the JSON output.
- BGE-M3 always runs on CPU when torch.cuda.is_available() is False.
- Cold-start time includes model download from HuggingFace on the first run.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import time
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Attempt to load .env before reading settings so the script works standalone
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:
    pass  # python-dotenv not available; rely on shell environment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark")

# ---------------------------------------------------------------------------
# Benchmark texts
# ---------------------------------------------------------------------------
_SAMPLE_TEXTS = [
    "What are the key features of the Atlas AI platform?",
    "Explain how multi-tenant RAG pipelines improve data isolation.",
    "Describe the embedding model selection strategy used in production.",
    "How does Qdrant store and retrieve dense vector embeddings efficiently?",
    "What are the tradeoffs between Jina AI and local BGE-M3 embeddings?",
    "Explain the role of Celery workers in asynchronous document ingestion.",
    "How does LangGraph orchestrate multi-step agentic reasoning chains?",
    "What security controls enforce tenant data isolation in the RAG system?",
    "How are Alembic migrations applied safely during rolling deployments?",
    "What Prometheus metrics are exposed by the FastAPI application?",
    "Summarise the CI/CD pipeline for the Atlas AI backend service.",
    "Describe CPU-only inference with PyTorch and SentenceTransformers.",
    "What is the P95 embedding latency target for production workloads?",
    "How does Redis cache short-term conversation memory for each tenant?",
    "Explain how chunking strategy affects RAG retrieval precision.",
    "What monitoring dashboards are available in the Grafana stack?",
]

_SINGLE_QUERY = "What is the Atlas AI Platform?"


# ---------------------------------------------------------------------------
# Resource snapshot helpers
# ---------------------------------------------------------------------------


def _memory_mb() -> Optional[float]:
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        return None


def _cpu_percent() -> Optional[float]:
    try:
        import psutil

        return psutil.Process(os.getpid()).cpu_percent(interval=0.1)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    frac = k - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


def _stats(samples: List[float]) -> Dict[str, float]:
    if not samples:
        return {}
    return {
        "min_ms": round(min(samples) * 1000, 2),
        "max_ms": round(max(samples) * 1000, 2),
        "mean_ms": round(statistics.mean(samples) * 1000, 2),
        "p50_ms": round(_percentile(samples, 50) * 1000, 2),
        "p95_ms": round(_percentile(samples, 95) * 1000, 2),
        "stddev_ms": (
            round(statistics.stdev(samples) * 1000, 2) if len(samples) > 1 else 0.0
        ),
        "n": len(samples),
    }


# ---------------------------------------------------------------------------
# Jina AI benchmark
# ---------------------------------------------------------------------------


def benchmark_jina(
    iterations: int,
    batch_size: int,
    batch_texts: List[str],
) -> Dict[str, Any]:
    import requests

    jina_api_key = os.environ.get("JINA_API_KEY", "")
    if not jina_api_key:
        return {"error": "JINA_API_KEY not set — skipping Jina benchmark"}

    _JINA_URL = "https://api.jina.ai/v1/embeddings"
    _JINA_MODEL = "jina-embeddings-v5-text-small"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jina_api_key}",
        # ⚠️  API key is NEVER logged or included in results
    }

    def _call(texts: List[str], task: str = "retrieval.passage") -> float:
        t0 = time.perf_counter()
        resp = requests.post(
            _JINA_URL,
            headers=headers,
            json={
                "model": _JINA_MODEL,
                "task": task,
                "normalized": True,
                "input": texts,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return time.perf_counter() - t0

    logger.info("[Jina] Warming up (1 call) …")
    try:
        _call([_SINGLE_QUERY], task="retrieval.query")
    except Exception as exc:
        return {"error": f"Jina warmup failed: {exc}"}

    logger.info("[Jina] Single-query latency (%d iterations) …", iterations)
    single_samples: List[float] = []
    for i in range(iterations):
        try:
            single_samples.append(_call([_SINGLE_QUERY], task="retrieval.query"))
        except Exception as exc:
            logger.warning("[Jina] Single-query iteration %d failed: %s", i, exc)

    logger.info(
        "[Jina] Batch latency (%d texts, %d iterations) …", len(batch_texts), iterations
    )
    batch_samples: List[float] = []
    for i in range(iterations):
        try:
            batch_samples.append(_call(batch_texts[:batch_size]))
        except Exception as exc:
            logger.warning("[Jina] Batch iteration %d failed: %s", i, exc)

    return {
        "provider": "jina-ai",
        "model": _JINA_MODEL,
        "single_query": _stats(single_samples),
        "batch": {
            **_stats(batch_samples),
            "batch_size": min(batch_size, len(batch_texts)),
            "num_texts": min(batch_size, len(batch_texts)),
        },
        "memory_mb_after": _memory_mb(),
    }


# ---------------------------------------------------------------------------
# BGE-M3 (SentenceTransformer / CPU) benchmark
# ---------------------------------------------------------------------------


def benchmark_bge_m3(
    model_name: str,
    iterations: int,
    batch_size: int,
    batch_texts: List[str],
) -> Dict[str, Any]:
    try:
        from sentence_transformers import SentenceTransformer
        import torch
    except ImportError as exc:
        return {"error": f"sentence-transformers or torch not installed: {exc}"}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(
        "[BGE-M3] torch version=%s  CUDA=%s  device=%s",
        torch.__version__,
        torch.cuda.is_available(),
        device,
    )

    mem_before = _memory_mb()

    logger.info("[BGE-M3] Loading model '%s' on %s (cold-start) …", model_name, device)
    t_load_start = time.perf_counter()
    try:
        model = SentenceTransformer(model_name, device=device)
    except Exception as exc:
        return {"error": f"Model load failed: {exc}"}
    cold_start_s = time.perf_counter() - t_load_start
    mem_after_load = _memory_mb()
    logger.info("[BGE-M3] Model loaded in %.2f s", cold_start_s)

    def _encode(texts: List[str]) -> float:
        t0 = time.perf_counter()
        model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=False,
        )
        return time.perf_counter() - t0

    logger.info("[BGE-M3] Single-query latency (%d iterations) …", iterations)
    single_samples: List[float] = []
    for i in range(iterations):
        try:
            single_samples.append(_encode([_SINGLE_QUERY]))
        except Exception as exc:
            logger.warning("[BGE-M3] Single-query iteration %d failed: %s", i, exc)

    logger.info(
        "[BGE-M3] Batch latency (%d texts, %d iterations) …",
        len(batch_texts),
        iterations,
    )
    batch_samples: List[float] = []
    for i in range(iterations):
        try:
            batch_samples.append(_encode(batch_texts[:batch_size]))
        except Exception as exc:
            logger.warning("[BGE-M3] Batch iteration %d failed: %s", i, exc)

    return {
        "provider": "bge-m3-cpu",
        "model": model_name,
        "device": device,
        "torch_version": torch.__version__,
        "cold_start_s": round(cold_start_s, 3),
        "memory_mb_before_load": mem_before,
        "memory_mb_after_load": mem_after_load,
        "memory_mb_delta": round((mem_after_load or 0) - (mem_before or 0), 1),
        "single_query": _stats(single_samples),
        "batch": {
            **_stats(batch_samples),
            "batch_size": min(batch_size, len(batch_texts)),
            "num_texts": min(batch_size, len(batch_texts)),
        },
        "memory_mb_after": _memory_mb(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Jina AI and/or BGE-M3 embedding providers",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        choices=["jina", "bge-m3", "both"],
        default="both",
        help="Which embedding provider(s) to benchmark",
    )
    parser.add_argument(
        "--model",
        default="BAAI/bge-m3",
        help="HuggingFace model name for BGE-M3 benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of latency measurement iterations per test",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Number of texts per batch (max = len(sample texts))",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save JSON results (optional, prints to stdout otherwise)",
    )
    return parser.parse_args()


def _print_summary(result: Dict[str, Any]) -> None:
    provider = result.get("provider", "unknown")
    if "error" in result:
        logger.error("[%s] ERROR: %s", provider, result["error"])
        return

    logger.info("=" * 60)
    logger.info("  Provider : %s", provider)
    logger.info("  Model    : %s", result.get("model", "N/A"))
    if "device" in result:
        logger.info(
            "  Device   : %s (torch %s)",
            result["device"],
            result.get("torch_version", "?"),
        )
    if "cold_start_s" in result:
        logger.info("  Cold-start model load : %.3f s", result["cold_start_s"])
    if result.get("memory_mb_delta"):
        logger.info("  Memory delta (load)   : %.1f MB", result["memory_mb_delta"])

    sq = result.get("single_query", {})
    if sq:
        logger.info(
            "  Single-query  mean=%s ms  p50=%s ms  p95=%s ms  (n=%s)",
            sq.get("mean_ms"),
            sq.get("p50_ms"),
            sq.get("p95_ms"),
            sq.get("n"),
        )

    b = result.get("batch", {})
    if b:
        logger.info(
            "  Batch(%s texts) mean=%s ms  p50=%s ms  p95=%s ms  (n=%s)",
            b.get("num_texts"),
            b.get("mean_ms"),
            b.get("p50_ms"),
            b.get("p95_ms"),
            b.get("n"),
        )
    logger.info("=" * 60)


def main() -> None:
    args = _parse_args()
    batch_texts = _SAMPLE_TEXTS  # use all 16 sample texts

    results: List[Dict[str, Any]] = []

    if args.provider in ("bge-m3", "both"):
        logger.info(
            ">>> Starting BGE-M3 benchmark (iterations=%d, batch_size=%d) <<<",
            args.iterations,
            args.batch_size,
        )
        bge_result = benchmark_bge_m3(
            model_name=args.model,
            iterations=args.iterations,
            batch_size=args.batch_size,
            batch_texts=batch_texts,
        )
        _print_summary(bge_result)
        results.append(bge_result)

    if args.provider in ("jina", "both"):
        logger.info(
            ">>> Starting Jina AI benchmark (iterations=%d, batch_size=%d) <<<",
            args.iterations,
            args.batch_size,
        )
        jina_result = benchmark_jina(
            iterations=args.iterations,
            batch_size=args.batch_size,
            batch_texts=batch_texts,
        )
        _print_summary(jina_result)
        results.append(jina_result)

    output = {"benchmark_results": results}

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        logger.info("Results saved to %s", args.output)
    else:
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
