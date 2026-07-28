import logging
from typing import List, Dict

from app.rag.rerankers.base import Document
from app.rag.rerankers.cross_encoder import CrossEncoderReranker
from app.rag.rerankers.bm25 import BM25Reranker
from app.rag.rerankers.hybrid import HybridReranker

logger = logging.getLogger(__name__)


class RankingService:

    def __init__(self, strategy: str = "hybrid"):
        self.strategy = strategy

        if strategy == "cross-encoder":
            self.reranker = CrossEncoderReranker()
        elif strategy == "bm25":
            self.reranker = BM25Reranker()
        elif strategy == "hybrid":
            self.reranker = HybridReranker()
        else:
            logger.warning(
                f"Unknown strategy: {strategy}, defaulting to hybrid"
            )
            self.reranker = HybridReranker()

    def rank(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10
    ) -> List[Dict]:

        doc_objects = [
            Document(
                content=doc.get('content', doc.get('page_content', '')),
                metadata=doc.get('metadata', {}),
                score=doc.get('score', 0.0)
            )
            for doc in documents
        ]

        reranked_docs = self.reranker.rerank(
            query,
            doc_objects,
            top_k
        )

        results = []
        for doc in reranked_docs:
            results.append({
                'content': doc.content,
                'metadata': doc.metadata,
                'original_score': doc.score,
                'rerank_score': doc.rerank_score,
                'combined_score': (doc.score + doc.rerank_score) / 2
            })

        return results
