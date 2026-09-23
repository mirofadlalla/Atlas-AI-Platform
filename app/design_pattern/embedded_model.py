"""Environment-aware dense embedding provider."""

from __future__ import annotations

import logging
import os
import threading
from typing import List

import requests
from cachetools import TTLCache
from langchain_core.embeddings import Embeddings

from app.core.config import settings

logger = logging.getLogger(__name__)

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_JINA_MODEL = "jina-embeddings-v5-text-small"


def _to_list(vec) -> List[float]:
    return vec.tolist() if hasattr(vec, "tolist") else list(vec)


class EmbeddedModel(Embeddings):
    """Use Jina AI as the primary provider with BGE-M3 as fallback."""

    _instance = None
    _lock = threading.Lock()

    _query_embedding_cache = TTLCache(maxsize=4_096, ttl=60)
    _query_embedding_cache_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False

        return cls._instance

    def _ensure_initialized(self):
        if self._initialized:
            return

        self.is_production = settings.is_production

        # BGE-M3 configuration
        self.bge_model_name = settings.embedding_model_name

        # Jina configuration
        self.jina_api_key = settings.jina_api_key
        self.jina_enabled = bool(self.jina_api_key)

        # BGE-M3 is available as fallback
        self.bge_enabled = True

        self.batch_size = int(os.environ.get("EMBED_BATCH_SIZE", "32"))
        self.timeout = float(os.environ.get("EMBED_TIMEOUT", "30"))

        self.local_model = None

        self._initialized = True

        logger.info(
            "Embedding provider initialized: "
            "primary=Jina AI model=%s "
            "jina_enabled=%s "
            "fallback=BGE-M3 model=%s",
            _JINA_MODEL,
            self.jina_enabled,
            self.bge_model_name,
        )

    def _call_jina(
        self,
        texts: List[str],
        task: str = "retrieval.passage",
    ) -> List[List[float]]:
        """Call Jina's embedding API."""

        response = requests.post(
            _JINA_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.jina_api_key}",
            },
            json={
                "model": _JINA_MODEL,
                "task": task,
                "normalized": True,
                "input": texts,
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        items = sorted(
            response.json()["data"],
            key=lambda item: item["index"],
        )

        return [item["embedding"] for item in items]

    def _load_bge_model(self) -> None:
        """Load BGE-M3 lazily only when Jina is unavailable."""

        if self.local_model is not None:
            return

        from sentence_transformers import SentenceTransformer
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"

        self.local_model = SentenceTransformer(
            self.bge_model_name,
            device=device,
        )

        logger.info(
            "Loaded Hugging Face embedding model %s on %s",
            self.bge_model_name,
            device,
        )

    def _call_bge_m3(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Generate embeddings using BGE-M3."""

        self._load_bge_model()

        embeddings = self.local_model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=self.batch_size,
        )

        return _to_list(embeddings)

    def _embed_batch(
        self,
        texts: List[str],
        task: str = "retrieval.passage",
    ) -> List[List[float]]:
        """
        Generate embeddings using:

        1. Jina AI — primary provider
        2. BGE-M3 — fallback provider
        """

        # ---------------------------------------------------------
        # 1. PRIMARY: Jina AI
        # ---------------------------------------------------------
        if self.jina_enabled:
            try:
                logger.debug(
                    "Generating embeddings with Jina AI (%s)",
                    _JINA_MODEL,
                )

                return self._call_jina(
                    texts,
                    task=task,
                )

            except Exception:
                logger.exception("Jina AI embedding failed; " "falling back to BGE-M3")

                # Disable Jina for the lifetime of this process
                # after a failure so we don't repeatedly hit a
                # broken API on every batch.
                self.jina_enabled = False

        # ---------------------------------------------------------
        # 2. FALLBACK: BGE-M3
        # ---------------------------------------------------------
        if self.bge_enabled:
            try:
                logger.info("Generating embeddings with BGE-M3 fallback")

                return self._call_bge_m3(texts)

            except Exception:
                logger.exception("BGE-M3 embedding failed")

        # ---------------------------------------------------------
        # 3. Nothing available
        # ---------------------------------------------------------
        raise RuntimeError(
            "No embedding provider is available. "
            "Jina AI failed or is unavailable, "
            "and BGE-M3 fallback also failed."
        )

    def embed_documents(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        self._ensure_initialized()

        if not texts:
            return []

        results: List[List[float]] = []

        for start in range(
            0,
            len(texts),
            self.batch_size,
        ):
            results.extend(
                self._embed_batch(
                    texts[start : start + self.batch_size],
                    task="retrieval.passage",
                )
            )

        return results

    def embed_query(
        self,
        text: str,
    ) -> List[float]:
        self._ensure_initialized()

        cache_key = text.strip()

        # ---------------------------------------------------------
        # Query cache
        # ---------------------------------------------------------
        if cache_key:
            with self._query_embedding_cache_lock:
                cached_vector = self._query_embedding_cache.get(cache_key)

            if cached_vector is not None:
                logger.debug("Reused exact query embedding from local cache")

                return list(cached_vector)

        # ---------------------------------------------------------
        # Jina → BGE fallback
        # ---------------------------------------------------------
        result = self._embed_batch(
            [text],
            task="retrieval.query",
        )

        vector = result[0] if result else []

        # ---------------------------------------------------------
        # Store in cache
        # ---------------------------------------------------------
        if cache_key and vector:
            with self._query_embedding_cache_lock:
                self._query_embedding_cache[cache_key] = tuple(vector)

        return vector
