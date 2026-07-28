import logging
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)


class Document:
    def __init__(self, content: str, metadata: Dict = None, score: float = 0.0):
        self.content = content
        self.metadata = metadata or {}
        self.score = score
        self.rerank_score = 0.0


class Reranker:
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 10
    ) -> List[Document]:
        raise NotImplementedError


class CrossEncoderReranker(Reranker):

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
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


class BM25Reranker(Reranker):

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


class HybridReranker(Reranker):

    def __init__(
        self,
        cross_encoder_weight: float = 0.7,
        bm25_weight: float = 0.3,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
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
        self,
        query: str,
        documents: List[Document],
        top_k: int = 10
    ) -> List[Document]:

        if not documents:
            return documents

        try:
            docs_for_ce = [
                Document(d.content, d.metadata, d.score)
                for d in documents
            ]

            docs_for_bm25 = [
                Document(d.content, d.metadata, d.score)
                for d in documents
            ]

            ce_ranked = self.cross_encoder.rerank(
                query,
                docs_for_ce,
                top_k=len(documents)
            )

            bm25_ranked = self.bm25.rerank(
                query,
                docs_for_bm25,
                top_k=len(documents)
            )

            ce_scores = np.array([
                d.rerank_score for d in ce_ranked
            ])

            bm25_scores = np.array([
                d.rerank_score for d in bm25_ranked
            ])

            ce_scores_norm = (
                (ce_scores - ce_scores.min()) /
                (ce_scores.max() - ce_scores.min() + 1e-10)
            )

            bm25_scores_norm = (
                (bm25_scores - bm25_scores.min()) /
                (bm25_scores.max() - bm25_scores.min() + 1e-10)
            )

            doc_content_to_ce_score = {
                d.content: score
                for d, score in zip(ce_ranked, ce_scores_norm)
            }

            doc_content_to_bm25_score = {
                d.content: score
                for d, score in zip(bm25_ranked, bm25_scores_norm)
            }

            for doc in documents:
                ce_score = doc_content_to_ce_score.get(doc.content, 0.0)

                bm25_score = doc_content_to_bm25_score.get(doc.content, 0.0)

                hybrid_score = (
                    self.cross_encoder_weight * ce_score +
                    self.bm25_weight * bm25_score
                )

                doc.rerank_score = hybrid_score

            reranked = sorted(
                documents,
                key=lambda x: x.rerank_score,
                reverse=True
            )

            logger.debug(f"Hybrid reranked {len(documents)} documents")

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Error in hybrid reranking: {e}")
            return documents[:top_k]


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
                f"Unknown strategy: {strategy}, "
                f"defaulting to hybrid"
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
                content=doc.get(
                    'content',
                    doc.get('page_content', '')
                ),
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
                'combined_score': (
                    doc.score + doc.rerank_score
                ) / 2
            })

        return results