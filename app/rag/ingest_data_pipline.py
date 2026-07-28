import os
import sys
import logging
from pathlib import Path
import time

from app.rag.steps.ingest import main
from app.rag.steps.loader import DocumentLoader
from app.rag.steps.file_tracker import FileTracker 
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class RAGPipeline:
    
    @staticmethod
    def process_file(file_path: str, custom_metadata: dict, db: Session):
        """
        Process a file through the RAG pipeline.
        
        Steps:
        1. Calculate file hash to detect changes
        2. Check if already processed
        3. Load document with error handling
        4. Chunk document with timeout protection
        5. Insert into Qdrant
        6. Track processing status
        
        Args:
            file_path: Path to the file to process
            custom_metadata: Metadata dict with tenant_id, source, author
            db: Database session for tracking
            
        Returns:
            Dict with status, message, and optional details/error
        """
        # Extract tenant_id and file_name for tracking purposes
        tenant_id = str(custom_metadata["tenant_id"])
        file_name = Path(file_path).name
        start_time = time.time()
        
        try:
            # 1. Calculate file hash to detect changes
            logger.warning(f"Checking file hash for: {file_name}")
            file_hash = FileTracker.calculate_file_hash(file_path)
            
            # 2. Check if the file has been processed before with the same hash
            if FileTracker.is_file_processed(tenant_id, file_hash, db):
                msg = f"Skip: File '{file_name}' for tenant {tenant_id} is already processed. No changes detected."
                logger.warning(msg)
                return {"status": "skipped", "message": msg}


            # File is new or has changed, proceed with RAG pipeline
            logger.warning(f"New content detected. Starting RAG pipeline for: {file_name}")
            
            # 3. Mark file as processing (idempotent - supports retries)
            logger.warning(f"File marked as processing: {file_name} (hash: {file_hash[:8]}...)")
            FileTracker.mark_processing(tenant_id, file_name, file_hash, db)
            
            # 4. Load the file with error handling
            logger.info(f"Loading document: {file_name}")
            try:
                documents = DocumentLoader.load_file(file_path, custom_metadata)
                logger.warning(f"Successfully loaded {len(documents)} pages from {file_name}")
            except Exception as load_error:
                error_msg = f"Failed to load file {file_name}: {str(load_error)}"
                logger.error(f"{error_msg}")
                FileTracker.mark_failed(tenant_id, file_hash, db)
                return {"status": "failed", "message": error_msg, "error": str(load_error), "stage": "loading"}
            
            if not documents:
                error_msg = f"File {file_name} loaded but contained no documents"
                logger.error(f"[{error_msg}")
                FileTracker.mark_failed(tenant_id, file_hash, db)
                return {"status": "failed", "message": error_msg, "stage": "validation"}
            
            # 5. Extract text and ingest into Qdrant
            logger.info("Combining document text...")
            full_text = "\n\n".join([doc.page_content for doc in documents])
            logger.info(f"Combined text length: {len(full_text)} characters")
            
            try:
                logger.info(f"Starting ingestion pipeline for {file_name}")
                result = main(full_text, custom_metadata)
                logger.info(f"Ingestion pipeline completed for {file_name}")
            except Exception as ingest_error:
                error_msg = f"Failed to ingest file {file_name}: {str(ingest_error)}"
                logger.error(f"{error_msg}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                FileTracker.mark_failed(tenant_id, file_hash, db)
                return {"status": "failed", "message": error_msg, "error": str(ingest_error), "stage": "ingestion"}
            
            # 6. Mark the file as completed
            logger.info(f"Marking file as completed: {file_name}")
            FileTracker.mark_completed(tenant_id, file_hash, db)
            
            # 7. Record metrics via internal webhook
            try:
                latency = time.time() - start_time
                # For standalone monitoring: Prometheus in Docker reaches host via host.docker.internal
                # For orchestrated: Use service name 'api' in Docker network
                api_host = os.environ.get("API_HOST", "http://host.docker.internal:8000")
                if "localhost" in api_host and not api_host.startswith("http"):
                    api_host = f"http://{api_host}"
                    
                webhook_url = f"{api_host}/api/internal/metrics/record"
                
                # Get chunks created from the result if available
                chunks_created = 0
                if isinstance(result, dict):
                    chunks_created = result.get("chunks_created", result.get("chunks_inserted", 0))
                
                # Determine document type from extension
                doc_type = "unknown"
                if "." in file_name:
                    doc_type = file_name.split(".")[-1].lower()
                    
                payload = {
                    "metric_type": "ingest_run",
                    "tenant_id": tenant_id,
                    "chunks_created": chunks_created,
                    "latency": float(latency),
                    "document_type": doc_type
                }
                
                import requests
                # Fire and forget with short timeout
                resp = requests.post(webhook_url, json=payload, timeout=2.0)
                if resp.status_code == 200:
                    logger.debug(f"Successfully sent ingest metrics for {file_name}")
                else:
                    logger.warning(f"API webhook returned status {resp.status_code}")
            except Exception as metric_error:
                logger.error(f"Error recording ingest metrics via webhook: {metric_error}")
            
            logger.warning(f"File processing complete for: {file_name}")
            return {"status": "success", "message": "File processed and ingested.", "details": result}
        
        except Exception as e:
            # Catch any unexpected errors
            error_msg = f"Unexpected error processing file {file_name}: {str(e)}"
            logger.error(f"{error_msg}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                FileTracker.mark_failed(tenant_id, file_hash, db)
            except:
                pass
            return {"status": "failed", "message": error_msg, "error": str(e), "stage": "unknown"}

