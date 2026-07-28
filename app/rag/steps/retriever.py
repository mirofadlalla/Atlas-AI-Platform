import os
import sys
import logging
from pathlib import Path

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_SYMLINKS"] = "1"

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client import models
from app.design_pattern.embedded_model import EmbeddedModel
from app.core.config import settings

logger = logging.getLogger(__name__)

qdrant_client = QdrantClient(
    url=settings.qdrant_url
)

sparse_embeddings = FastEmbedSparse(model_name=settings.sparse_embedding_model)

# Cache the embedding model singleton at module level
_embedding_model = EmbeddedModel()
_retrievers_cache = {}

def get_retriever(tenant_id: int):
    """
    Get or create a retriever for the specified tenant.
    Uses cached embedding model singleton and caches retrievers per tenant.
    """
    # Return cached retriever if available
    if tenant_id in _retrievers_cache:
        logger.info(f"Using cached retriever for tenant: {tenant_id}")
        return _retrievers_cache[tenant_id]
    
    logger.info(f"Creating new retriever for tenant: {tenant_id}")
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        collection_name=settings.qdrant_collection_name,
        
        embedding=_embedding_model,  # Use singleton instance
        vector_name="dense",
        
        sparse_embedding=sparse_embeddings,
        sparse_vector_name="sparse",
        
        retrieval_mode=RetrievalMode.HYBRID,
        
        content_payload_key="content", 
        metadata_payload_key="payload" 
    )

    retriever = vectorstore.as_retriever(
        search_kwargs={
            # "k": 5,
            "filter": models.Filter(
                must=[
                    models.FieldCondition(
                        key="payload.tenant_id", 
                        match=models.MatchValue(value=tenant_id)
                    )
                ]
            )
        }
    )
    
    # Cache the retriever
    _retrievers_cache[tenant_id] = retriever
    return retriever

# if __name__ == "__main__":
#     retriever = get_retriever(123)
#     relevant_docs = retriever.invoke("What is machine learning?") 
    
#     print("\n--- Retrieved Documents ---")
#     for i, doc in enumerate(relevant_docs):
#         print(f"Doc {i+1}: {doc.page_content}")
#         print(f"Metadata: {doc.metadata}\n")

