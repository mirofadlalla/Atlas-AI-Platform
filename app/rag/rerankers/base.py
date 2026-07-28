from typing import Dict, List, Optional

class Document:
    def __init__(self, content: str, metadata: Dict = None, score: float = 0.0):
        self.content = content
        self.metadata = metadata or {}
        self.score = score
        self.rerank_score = 0.0


class BaseReranker:
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 10
    ) -> List[Document]:
        raise NotImplementedError
