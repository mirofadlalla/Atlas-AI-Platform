"""
Embedding Model — priority chain:
  1. Jina AI API  (jina-embeddings-v5-text-small) — primary, cloud
  2. ngrok vLLM   (fine-tuned model on remote device) — secondary, local net
  3. SentenceTransformers (BGE-M3 / MiniLM) — final local fallback

All configuration is read from settings / .env.
"""
import os
import threading
import logging
from typing import List

import requests
from langchain_core.embeddings import Embeddings

from app.core.config import settings

logger = logging.getLogger(__name__)

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_JINA_MODEL = "jina-embeddings-v5-text-small"


def _to_list(vec) -> List[float]:
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return list(vec)


class EmbeddedModel(Embeddings):
    """
    Singleton embedding model with three-tier fallback:
      1. Jina AI REST API
      2. ngrok-served fine-tuned vLLM endpoint  (REMOTE_EMBED_URL / settings)
      3. Local SentenceTransformers model
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    # ------------------------------------------------------------------ #
    #  Initialisation                                                       #
    # ------------------------------------------------------------------ #

    def _ensure_initialized(self):
        if self._initialized:
            return
        # Jina AI
        self.jina_api_key = settings.jina_api_key
        self.jina_enabled = bool(self.jina_api_key)

        # ngrok / vLLM fine-tuned model (secondary)
        self.remote_url = settings.remote_embed_url  # e.g. https://xxx.ngrok-free.dev
        self.remote_enabled = bool(self.remote_url)

        self.batch_size = int(os.environ.get("EMBED_BATCH_SIZE", "32"))
        self.timeout = float(os.environ.get("EMBED_TIMEOUT", "30"))
        self.local_model = None
        self._initialized = True

        logger.info(
            "EmbeddedModel init — Jina: %s | ngrok: %s | local fallback: enabled",
            "✓" if self.jina_enabled else "✗",
            self.remote_url if self.remote_enabled else "✗",
        )

    # ------------------------------------------------------------------ #
    #  Tier 1 — Jina AI                                                     #
    # ------------------------------------------------------------------ #

    def _call_jina(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        """Call Jina AI embeddings API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.jina_api_key}",
        }
        payload = {
            "model": _JINA_MODEL,
            "task": task,
            "normalized": True,
            "input": texts,
        }
        resp = requests.post(_JINA_URL, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # Jina returns: {"data": [{"embedding": [...], "index": 0}, ...]}
        sorted_items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_items]

    # ------------------------------------------------------------------ #
    #  Tier 2 — ngrok vLLM endpoint                                         #
    # ------------------------------------------------------------------ #

    def _call_remote_embed(self, texts: List[str]) -> List[List[float]]:
        """Call the ngrok-served fine-tuned vLLM /embed endpoint."""
        url = self.remote_url.rstrip("/") + "/embed"
        resp = requests.post(url, json={"texts": texts}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("embeddings", [])

    # ------------------------------------------------------------------ #
    #  Tier 3 — Local SentenceTransformers fallback                         #
    # ------------------------------------------------------------------ #

    def _load_local_model(self):
        if self.local_model is None:
            from sentence_transformers import SentenceTransformer
            import torch
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.local_model = SentenceTransformer("BAAI/bge-m3", device=device)
                logger.info("Loaded local embedding model (BGE-M3) on %s", device)
            except Exception:
                logger.exception("BGE-M3 failed, falling back to all-MiniLM-L6-v2")
                self.local_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    def _call_local(self, texts: List[str]) -> List[List[float]]:
        self._load_local_model()
        emb = self.local_model.encode(texts, normalize_embeddings=True, batch_size=self.batch_size)
        return _to_list(emb)

    # ------------------------------------------------------------------ #
    #  Core batch embedding with fallback chain                             #
    # ------------------------------------------------------------------ #

    def _embed_batch(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        """Try Jina → ngrok → local, in order."""
        # --- Tier 1: Jina ---
        if self.jina_enabled:
            try:
                return self._call_jina(texts, task=task)
            except Exception:
                logger.exception("Jina AI embedding failed, trying ngrok vLLM...")
                self.jina_enabled = False  # disable for this session to avoid repeated failures

        # --- Tier 2: ngrok vLLM ---
        if self.remote_enabled:
            try:
                return self._call_remote_embed(texts)
            except Exception:
                logger.exception("ngrok vLLM embedding failed, falling back to local model...")
                self.remote_enabled = False

        # --- Tier 3: Local model ---
        return self._call_local(texts)

    # ------------------------------------------------------------------ #
    #  LangChain interface                                                  #
    # ------------------------------------------------------------------ #

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self._ensure_initialized()
        if not texts:
            return []
        results: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i: i + self.batch_size]
            results.extend(self._embed_batch(batch, task="retrieval.passage"))
        return results

    def embed_query(self, text: str) -> List[float]:
        self._ensure_initialized()
        result = self._embed_batch([text], task="retrieval.query")
        return result[0] if result else []
