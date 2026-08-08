from app.models.TRACKER_DB_FILE import TRACKER_DB_FILE

from sqlalchemy.orm import Session
from datetime import datetime


class TrackerDBFileRepository:
    """
    Repository for managing processed files in the tracker database.
    This repository provides methods to add new processed file records and check if a file has already been processed based on its hash.
    It interacts with the TRACKER_DB_FILE model to perform database operations related to file tracking.
    """

    def __init__(self, db: Session):
        self.db = db

    # Add a new processed file record to the database
    def add_processed_file(self, tenant_id: str, file_name: str, file_hash: str):
        new_record = TRACKER_DB_FILE(
            tenant_id=tenant_id,
            file_name=file_name,
            file_hash=file_hash,
        )
        self.db.add(new_record)
        self.db.commit()
        self.db.refresh(new_record)
        return new_record

    # Check if a file with the given hash has already been successfully processed for the specified tenant
    def is_file_processed(self, tenant_id: str, file_hash: str) -> bool:
        record = (
            self.db.query(TRACKER_DB_FILE)
            .filter_by(
                tenant_id=tenant_id,
                file_hash=file_hash,
                status="completed",  # Only skip if status is 'completed'
            )
            .first()
        )
        return record is not None

    def mark_processing(self, tenant_id: str, file_name: str, file_hash: str):
        """Mark a file as currently being processed."""
        record = (
            self.db.query(TRACKER_DB_FILE)
            .filter_by(tenant_id=tenant_id, file_hash=file_hash)
            .first()
        )

        if not record:
            # Create new record with processing status
            record = TRACKER_DB_FILE(
                tenant_id=tenant_id,
                file_name=file_name,
                file_hash=file_hash,
                status="processing",
                started_at=datetime.utcnow(),
            )
            self.db.add(record)
        else:
            # Update existing record
            record.status = "processing"
            record.started_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_completed(self, tenant_id: str, file_hash: str):
        """Mark a file as successfully processed."""
        record = (
            self.db.query(TRACKER_DB_FILE)
            .filter_by(tenant_id=tenant_id, file_hash=file_hash)
            .first()
        )

        if record:
            record.status = "completed"
            record.completed_at = datetime.utcnow()
            record.processed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(record)

        return record

    def mark_failed(self, tenant_id: str, file_hash: str):
        """Mark a file as failed processing."""
        record = (
            self.db.query(TRACKER_DB_FILE)
            .filter_by(tenant_id=tenant_id, file_hash=file_hash)
            .first()
        )

        if record:
            record.status = "failed"
            record.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(record)

        return record
