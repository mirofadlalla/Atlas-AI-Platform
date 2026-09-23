import json
import logging
import os
from typing import List, Optional
import requests

from app.rag.rerankers.base import BaseReranker, Document
from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalCrossEncoderReranker(BaseReranker):
    """
    Reranker using a local HuggingFace cross-encoder model via sentence-transformers.
    Downloads and runs the model locally.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.cross_encoder_model
        self.model = None
        try:
            from sentence_transformers import CrossEncoder

            self.model = CrossEncoder(self.model_name)
            logger.info(f"Loaded cross-encoder model: {self.model_name}")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model '{self.model_name}': {e}")
            self.model = None

    def rerank(
        self, query: str, documents: List[Document], top_k: int = 10
    ) -> List[Document]:
        if not self.model or not documents:
            return documents[:top_k]

        try:
            texts = [doc.content for doc in documents]
            query_doc_pairs = [[query, text] for text in texts]
            scores = self.model.predict(query_doc_pairs)

            for doc, score in zip(documents, scores):
                doc.rerank_score = float(score)

            reranked = sorted(documents, key=lambda x: x.rerank_score, reverse=True)

            logger.debug(
                f"Reranked {len(documents)} documents "
                f"for query: {query[:50]}... "
                f"Top score: {reranked[0].rerank_score:.4f}"
            )

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in cross-encoder reranking: {e}")
            return documents[:top_k]


class JinaReranker(BaseReranker):
    """
    Reranker using Jina AI's reranking API (https://api.jina.ai/v1/rerank).
    No local HuggingFace weights or GPU required.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = getattr(settings, "jina_api_key", "") or os.getenv(
                "JINA_API_KEY", ""
            )
        self.model_name = model_name or getattr(
            settings, "jina_reranker_model", "jina-reranker-v3.5"
        )
        self.url = url or getattr(
            settings, "jina_reranker_url", "https://api.jina.ai/v1/rerank"
        )
        self.timeout = timeout
        logger.info(f"Initialized Jina reranker with model: {self.model_name}")

    def rerank(
        self, query: str, documents: List[Document], top_k: int = 10
    ) -> List[Document]:
        if not documents:
            return []

        if not self.api_key:
            logger.error(
                "JINA_API_KEY is not set. Cannot perform Jina reranking. "
                "Please set JINA_API_KEY in your environment or .env file."
            )
            return documents[:top_k]

        try:
            texts = [doc.content for doc in documents]
            top_n = min(top_k, len(documents)) if top_k > 0 else len(documents)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            data = {
                "model": self.model_name,
                "query": query,
                "top_n": top_n,
                "documents": texts,
                "return_documents": False,
            }

            response = requests.post(
                self.url,
                headers=headers,
                data=json.dumps(data),
                timeout=self.timeout,
            )
            response.raise_for_status()
            res_data = response.json()

            results = res_data.get("results", [])
            reranked = []
            for item in results:
                idx = item["index"]
                doc = documents[idx]
                doc.rerank_score = float(item["relevance_score"])
                reranked.append(doc)

            logger.debug(
                f"Jina reranked {len(reranked)} documents for query: {query[:50]}... "
                f"Top score: {reranked[0].rerank_score:.4f}"
                if reranked
                else ""
            )

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in Jina reranking: {e}")
            return documents[:top_k]


class CrossEncoderReranker(BaseReranker):
    """
    Unified reranker that delegates to either LocalCrossEncoderReranker (HuggingFace)
    or JinaReranker (Jina AI API) based on configuration or explicit parameter.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        raw_provider = (
            provider
            or os.getenv("RERANKER_PROVIDER")
            or os.getenv("CROSS_ENCODER_PROVIDER")
            or getattr(settings, "reranker_provider", None)
            or "local"
        )
        self.provider = raw_provider.strip().lower()

        if self.provider in ("jina", "jina-ai", "jina_ai"):
            # Avoid using local cross-encoder model name if passed as default
            if not model_name or "cross-encoder" in model_name:
                resolved_model = getattr(
                    settings, "jina_reranker_model", "jina-reranker-v3.5"
                )
            else:
                resolved_model = model_name

            self._reranker = JinaReranker(
                model_name=resolved_model,
                api_key=api_key,
                timeout=timeout,
            )
        else:
            self.provider = "local"
            resolved_model = model_name or settings.cross_encoder_model
            self._reranker = LocalCrossEncoderReranker(model_name=resolved_model)

    @property
    def model(self):
        """Backward-compatible property accessing the underlying model (if local)."""
        return getattr(self._reranker, "model", None)

    @property
    def model_name(self) -> str:
        return self._reranker.model_name

    def rerank(
        self, query: str, documents: List[Document], top_k: int = 10
    ) -> List[Document]:
        return self._reranker.rerank(query, documents, top_k=top_k)
