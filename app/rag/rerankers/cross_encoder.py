import logging
from typing import List
from app.rag.rerankers.base import BaseReranker, Document
from app.core.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker(BaseReranker):

    def __init__(self, model_name: str = None):
        model_name = model_name or settings.cross_encoder_model
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name)
            self.model_name = model_name
            logger.info(f"Loaded cross-encoder model: {model_name}")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 10
    ) -> List[Document]:

        if not self.model or not documents:
            return documents[:top_k]

        try:
            texts = [doc.content for doc in documents]
            query_doc_pairs = [[query, text] for text in texts]
            scores = self.model.predict(query_doc_pairs)

            for doc, score in zip(documents, scores):
                doc.rerank_score = float(score)

            reranked = sorted(
                documents,
                key=lambda x: x.rerank_score,
                reverse=True
            )

            logger.debug(
                f"Reranked {len(documents)} documents "
                f"for query: {query[:50]}... "
                f"Top score: {reranked[0].rerank_score:.4f}"
            )

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in cross-encoder reranking: {e}")
            return documents[:top_k]
