import os
import sys
from pathlib import Path

from app.repositories.qdrant import QdrantRepository
from app.rag.steps.semantic_chunking_function import SemanticChunkingFunction
from app.core.config import settings

def main(text : str , my_metadata : dict):
    import logging
    logger = logging.getLogger(__name__)
    
    if not text or len(text.strip()) == 0:
        logger.error("Input text is empty")
        raise ValueError("Cannot chunk empty text")
    
    repo = QdrantRepository()
    collection_name = settings.qdrant_collection_name
    repo.create_collection(collection_name) 

    logger.info("Chunking text...")
    logger.warning("Chunking text...")
    
    # Initialize embeddings before chunking
    logger.info("Initializing embedding model for semantic chunking...")
    
    try:
        chunks_with_metadata = SemanticChunkingFunction.process_document(text, my_metadata)
    except Exception as e:
        logger.error(f"Chunking failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    
    if not chunks_with_metadata:
        logger.error("Chunking resulted in empty chunks")
        raise ValueError("Chunking produced no chunks")
    
    logger.info(f"Chunking complete - Created {len(chunks_with_metadata)} chunks")
    logger.warning(f"Chunking complete - Created {len(chunks_with_metadata)} chunks")
    print(f"Chunking complete - Created {len(chunks_with_metadata)} chunks")

    logger.info("Preparing chunks for insertion into Qdrant...")
    data_to_insert = []
    for idx, doc in enumerate(chunks_with_metadata):
        try:
            # Generate a stable chunk ID based on the content and metadata
            chunk_id = SemanticChunkingFunction.generate_chunk_id(
                text=doc.page_content,
                tenant_id=my_metadata["tenant_id"],
                source=my_metadata["source"]
            )
            
            data_to_insert.append({
                "id": chunk_id,
                "text": doc.page_content,
                "metadata": doc.metadata
            })
            
            if (idx + 1) % 10 == 0:
                logger.debug(f"Prepared {idx + 1}/{len(chunks_with_metadata)} chunks for insertion")
        except Exception as e:
            logger.error(f"Error preparing chunk {idx}: {e}")
            continue
    
    if not data_to_insert:
        logger.error("No valid chunks to insert after preparation")
        raise ValueError("No valid chunks to insert")
    
    logger.info(f"Inserting {len(data_to_insert)} chunks into Qdrant collection...")
    try:
        repo.add_hybrid_documents(collection_name, data_to_insert)
    except Exception as e:
        logger.error(f"Failed to insert chunks into Qdrant: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    
    logger.info(f"Successfully inserted {len(data_to_insert)} chunks into Qdrant")
    logger.warning(f"Successfully inserted {len(data_to_insert)} chunks into Qdrant")
    print(f"Successfully inserted {len(data_to_insert)} chunks into Qdrant")
    
    return {
        "status": "success",
        "chunks_created": len(chunks_with_metadata),
        "chunks_inserted": len(data_to_insert),
        "collection": collection_name
    }


# if __name__ == "__main__":
#     # Simple Test
#     text = """
#     Machine learning is a subset of artificial intelligence.
#     It allows systems to learn from data.
#     Deep learning is a specialized type of machine learning.
#     Pizza is one of the most popular foods in the world.
#     Neural networks are inspired by the human brain.
#     """

#     my_metadata = {
#         "tenant_id": 123,
#         "source": "machine_learning_intro.txt",
#         "author": "Omar"
#     }
#     main(text,my_metadata)




# # 4. طباعة النتيجة عشان تتأكد
# print(chunks_with_metadata)