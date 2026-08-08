# app/processors/folder_processor.py
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from .Interface import PathProcessor
from app.controllers.ingest_rag_controller import IngestController


class FolderProcessor(PathProcessor):
    """Processor for folders containing multiple files"""

    def __init__(self, recursive: bool = False, file_extensions: List[str] = None):
        self.recursive = recursive
        self.file_extensions = file_extensions or []

    def can_handle(self, path: Path) -> bool:
        return path.is_dir()

    def _should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed based on extensions"""
        if not file_path.is_file():
            return False
        if not self.file_extensions:
            return True
        return file_path.suffix.lower() in [ext.lower() for ext in self.file_extensions]

    def process(
        self, path: Path, tenant_id: str, source: str, author: str, db: Session
    ) -> Dict[str, Any]:
        print(f"📁 Processing folder: {path.name}")

        # Get all files
        if self.recursive:
            files = list(path.rglob("*"))
        else:
            files = list(path.glob("*"))

        # Filter files
        files = [f for f in files if self._should_process_file(f)]

        print(f"Found {len(files)} files to process")

        results = []
        for file in files:
            print(f"  - {file.name}")
            result = IngestController.ingest_file(
                file_path=str(file),
                tenant_id=tenant_id,
                source=source,
                author=author,
                db=db,
            )
            results.append(
                {
                    "file": file.name,
                    "path": str(file),
                    "task_id": result.get("task_id"),
                    "status": result.get("status"),
                    "success": result.get("success", False),
                }
            )

        return {
            "type": "folder",
            "name": path.name,
            "path": str(path),
            "recursive": self.recursive,
            "files_processed": len(results),
            "results": results,
        }
