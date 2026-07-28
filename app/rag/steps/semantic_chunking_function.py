import hashlib
import logging
import threading
import time
import uuid
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document

from app.models.uuid import uuid_pk

logger = logging.getLogger(__name__)

class SemanticChunkingFunction:
    
    @staticmethod
    def process_document(text: str, metadata: dict, use_semantic_chunking: bool = True, timeout: int = 300):
        """
        Process a document into chunks using token-based and optionally semantic chunking.
        
        Returns:
            List of Document objects with chunks
        """
        
        logger.info("Step 1: Creating initial token-based chunks...")

        token_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=50
        )
        initial_docs = token_splitter.create_documents([text], metadatas=[metadata]) # => List[Document] 
        logger.info(f"Created {len(initial_docs)} initial token-based chunks")

        # Only skip semantic chunking when explicitly disabled or single chunk
        try:
            from app.core.config import settings
            timeout = getattr(settings, "semantic_chunking_timeout", 900)
        except Exception:
            timeout = 900

        if not use_semantic_chunking or len(initial_docs) <= 1:
            logger.info("Skipping semantic chunking (size ≤1 or disabled)")
            return initial_docs

        logger.info("Step 2: Initializing embedding model for semantic chunking...")
        try:

            from app.design_pattern.embedded_model import EmbeddedModel
            embedding_model = EmbeddedModel()
            logger.info("Embedding model initialized successfully")
        except Exception as e:

            logger.error(f"Failed to initialize embedding model: {e}")
            logger.warning("Falling back to token-based chunking only")
            return initial_docs

        logger.info("Step 3: Performing semantic chunking using embeddings... (this may take a few minutes for large documents)")
        
        # Run semantic chunking with timeout
        result_holder = {'result': None, 'error': None}
        
        def run_semantic_chunking():
            try:
                semantic_splitter = SemanticChunker(
                    embeddings=embedding_model,
                    breakpoint_threshold_type="percentile",
                    breakpoint_threshold_amount=90
                )
                final_docs = semantic_splitter.split_documents(initial_docs)
                result_holder['result'] = final_docs
            except Exception as e:
                result_holder['error'] = e
        
        # Execute with timeout (use config timeout)
        thread = threading.Thread(target=run_semantic_chunking, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            logger.error(f"Semantic chunking timed out after {timeout}s")
            logger.warning("Falling back to token-based chunking")
            return initial_docs
        
        if result_holder['error']:
            logger.error(f"Semantic chunking failed: {result_holder['error']}")
            logger.warning("Falling back to token-based chunking")
            return initial_docs
        
        final_docs = result_holder['result']
        
        if final_docs is None:
            logger.warning("Semantic chunking returned None, using token-based chunks")
            return initial_docs
        
        logger.info(f"Semantic chunking complete - Created {len(final_docs)} final chunks")
        logger.info(f"Token-based: {len(initial_docs)} → Semantic: {len(final_docs)}")
        
        return final_docs

    @staticmethod
    def generate_chunk_id(text: str, tenant_id: int, source: str) -> str:
        """
        Generate a stable chunk ID based on the content and metadata.
        This ensures that the same chunk will always get the same ID, which helps with deduplication and tracking.
        Must be a valid UUID string for Qdrant.
        """
        unique_string = f"{tenant_id}_{source}_{text}"
        hash_bytes = hashlib.md5(unique_string.encode('utf-8')).digest()
        chunk_id = str(uuid.UUID(bytes=hash_bytes))
        logger.debug(f"Generated chunk ID: {chunk_id} for tenant_id: {tenant_id}, source: {source}")
        return chunk_id














# from sklearn.metrics.pairwise import cosine_similarity

# import numpy as np 

# import os
# import re

# def split_into_sentences(text: str):
#     sentences = re.split(r'(?<=[.!?]) +', text)
#     return [s.strip() for s in sentences if s.strip()]


# def semantic_chunk(docs, chunk_size=512, overlap=50, threshold=0.75):

#     sentences = split_into_sentences(docs)

#     if not sentences:
#         return []
    
#     model = EmbeddedModel()
#     embeddings  = model.encode(sentences)

#     chunks = []
#     current_chunk = [sentences[0]]
#     current_embedding = [embeddings[0]]

#     for i in range(1,len(sentences)):

#         centriod = np.mean(current_embedding)
#         sim = cosine_similarity(
#             centriod,
#             embeddings[i]
#         )[0][0]

#     if sim > threshold:
#         current_chunk.append(sentences[i])
#         current_embedding.append(embeddings[i])

#     else :
#         chunks.append(" ".join(current_chunk))
#         current_chunk = [sentences[1]]
#         current_embedding = [embeddings[1]]
    
#     if current_chunk :
#         chunks.append(" ".join(current_chunk))

#     return chunks

# text = """
# Machine learning is a subset of artificial intelligence.
# It allows systems to learn from data.
# Deep learning is a specialized type of machine learning.
# Pizza is one of the most popular foods in the world.
# Neural networks are inspired by the human brain.
# """

# chunks = semantic_chunk(text, threshold=0.7)

# for i, c in enumerate(chunks):
#     print(f"\nChunk {i+1}:\n{c}")


