import logging
from typing import List
from app.rag.rerankers.base import BaseReranker, Document

logger = logging.getLogger(__name__)


class BM25Reranker(BaseReranker):

    def __init__(self):
        try:
            from rank_bm25 import BM25Okapi
            self.BM25Okapi = BM25Okapi
            logger.info("BM25 reranker initialized")
        except ImportError:
            logger.error(
                "rank-bm25 not installed. "
                "Install with: pip install rank-bm25"
            )
            self.BM25Okapi = None

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 10
    ) -> List[Document]:

        if not self.BM25Okapi or not documents:
            return documents[:top_k]

        try:
            tokenized_docs = [
                doc.content.lower().split()
                for doc in documents
            ]

            bm25 = self.BM25Okapi(tokenized_docs)
            query_tokens = query.lower().split()
            scores = bm25.get_scores(query_tokens)

            for doc, score in zip(documents, scores):
                doc.rerank_score = float(score)

            reranked = sorted(
                documents,
                key=lambda x: x.rerank_score,
                reverse=True
            )

            logger.debug(f"BM25 reranked {len(documents)} documents")
            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in BM25 reranking: {e}")
            return documents[:top_k]
