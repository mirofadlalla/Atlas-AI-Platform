import os
import json
import hashlib
from pathlib import Path

from app.repositories.trakcer_db_file_repositorie import TrackerDBFileRepository

from sqlalchemy.orm import Session


# TRACKER_DB_FILE = "processed_files_db.json"

class FileTracker:
    
    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """
        calculates the SHA-256 hash of a file's content. This is used to uniquely identify files based on their content, regardless of their name or location.
        By hashing the file content, we can detect if a file has changed since the last time
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Cannot hash missing file: {file_path}")
            
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def is_file_processed(tenant_id: int, file_hash: str , db: Session) -> bool:
        """
        Checks if a file with the given hash has already been processed for the specified tenant.
        Returns True if the file is already processed, False otherwise.
        """
        tenant_id = str(tenant_id)  # Ensure tenant_id is a string for consistent database queries
        tracker_repo = TrackerDBFileRepository(db)

        return tracker_repo.is_file_processed(tenant_id, file_hash)
    

    @staticmethod
    def mark_file_as_processed(tenant_id: int, file_name: str, file_hash: str , db: Session):
        """
        Marks a file as processed in the database for the given tenant.
        This function adds a new record to the tracker database with the tenant ID, file name, and file hash.
        """
        tracker_repo = TrackerDBFileRepository(db)
        tenant_id = str(tenant_id)  # Ensure tenant_id is a string for consistent database queries
        tracker_repo.add_processed_file(tenant_id, file_name, file_hash)

        print(f"File tracker updated with new hash: {file_hash}")

    @staticmethod
    def mark_processing(tenant_id: int, file_name: str, file_hash: str, db: Session):
        """
        Marks a file as currently being processed.
        This function creates a new record or updates an existing one with 'processing' status and start time.
        """
        tracker_repo = TrackerDBFileRepository(db)
        tenant_id = str(tenant_id)
        tracker_repo.mark_processing(tenant_id, file_name, file_hash)
        print(f"File marked as processing: {file_name} (hash: {file_hash[:8]}...)")

    @staticmethod
    def mark_completed(tenant_id: int, file_hash: str, db: Session):
        """
        Marks a file as successfully processed.
        """
        tracker_repo = TrackerDBFileRepository(db)
        tenant_id = str(tenant_id)
        tracker_repo.mark_completed(tenant_id, file_hash)
        print(f"File marked as completed: {file_hash[:8]}...")

    @staticmethod
    def mark_failed(tenant_id: int, file_hash: str, db: Session):
        """
        Marks a file as failed processing. This allows retries without re-doing chunking.
        """
        tracker_repo = TrackerDBFileRepository(db)
        tenant_id = str(tenant_id)
        tracker_repo.mark_failed(tenant_id, file_hash)
        print(f"File marked as failed: {file_hash[:8]}...")