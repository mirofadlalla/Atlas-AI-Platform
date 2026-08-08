import logging
from typing import List
import numpy as np

from app.rag.rerankers.base import BaseReranker, Document
from app.rag.rerankers.cross_encoder import CrossEncoderReranker
from app.rag.rerankers.bm25 import BM25Reranker

logger = logging.getLogger(__name__)


class HybridReranker(BaseReranker):
    def __init__(
        self,
        cross_encoder_weight: float = 0.7,
        bm25_weight: float = 0.3,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
    ):
        self.cross_encoder_weight = cross_encoder_weight
        self.bm25_weight = bm25_weight

        self.cross_encoder = CrossEncoderReranker(cross_encoder_model)
        self.bm25 = BM25Reranker()

        logger.info(
            f"Hybrid reranker initialized - "
            f"CE weight: {cross_encoder_weight}, "
            f"BM25 weight: {bm25_weight}"
        )

    def rerank(
        self, query: str, documents: List[Document], top_k: int = 10
    ) -> List[Document]:
        if not documents:
            return documents

        try:
            docs_for_ce = [Document(d.content, d.metadata, d.score) for d in documents]

            docs_for_bm25 = [
                Document(d.content, d.metadata, d.score) for d in documents
            ]

            ce_ranked = self.cross_encoder.rerank(
                query, docs_for_ce, top_k=len(documents)
            )

            bm25_ranked = self.bm25.rerank(query, docs_for_bm25, top_k=len(documents))

            ce_scores = np.array([d.rerank_score for d in ce_ranked])

            bm25_scores = np.array([d.rerank_score for d in bm25_ranked])

            ce_scores_norm = (ce_scores - ce_scores.min()) / (
                ce_scores.max() - ce_scores.min() + 1e-10
            )

            bm25_scores_norm = (bm25_scores - bm25_scores.min()) / (
                bm25_scores.max() - bm25_scores.min() + 1e-10
            )

            doc_content_to_ce_score = {
                d.content: score for d, score in zip(ce_ranked, ce_scores_norm)
            }

            doc_content_to_bm25_score = {
                d.content: score for d, score in zip(bm25_ranked, bm25_scores_norm)
            }

            for doc in documents:
                ce_score = doc_content_to_ce_score.get(doc.content, 0.0)
                bm25_score = doc_content_to_bm25_score.get(doc.content, 0.0)

                hybrid_score = (
                    self.cross_encoder_weight * ce_score + self.bm25_weight * bm25_score
                )

                doc.rerank_score = hybrid_score

            reranked = sorted(documents, key=lambda x: x.rerank_score, reverse=True)

            logger.debug(f"Hybrid reranked {len(documents)} documents")
            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in hybrid reranking: {e}")
            return documents[:top_k]
