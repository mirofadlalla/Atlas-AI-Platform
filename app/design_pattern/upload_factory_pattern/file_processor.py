# app/processors/file_processor.py
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Dict, Any
from .Interface import PathProcessor
from app.controllers.ingest_rag_controller import IngestController


class FileProcessor(PathProcessor):
    """Processor for single files"""

    def can_handle(self, path: Path) -> bool:
        return path.is_file()

    def process(
        self, path: Path, tenant_id: str, source: str, author: str, db: Session
    ) -> Dict[str, Any]:
        print(f"📄 Processing file: {path.name}")

        result = IngestController.ingest_file(
            file_path=str(path),
            tenant_id=tenant_id,
            source=source,
            author=author,
            db=db,
        )

        return {
            "type": "file",
            "file": path.name,
            "path": str(path),
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "success": result.get("success", False),
        }
