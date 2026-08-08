# app/services/path_processing_service.py
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from app.design_pattern.upload_factory_pattern.processor_factory import (
    processor_factory,
)
from app.design_pattern.upload_factory_pattern.Interface import PathProcessor


class PathProcessingService:
    """Main service for path processing using factory pattern"""

    def __init__(self, factory=processor_factory):
        self.factory = factory

    def process_path(
        self,
        file_path: str,
        tenant_id: str,
        source: str,
        author: str,
        db: Session,
        recursive: bool = False,
        file_extensions: List[str] = None,
        custom_processor: Optional[PathProcessor] = None,
    ) -> Dict[str, Any]:
        """
        Process a path (file or folder) using the appropriate processor
        """
        path = Path(file_path)

        # Check if path exists
        if not path.exists():
            return {
                "success": False,
                "error": f"Path does not exist: {file_path}",
                "path": file_path,
            }

        # Use custom processor if provided
        if custom_processor and custom_processor.can_handle(path):
            processor = custom_processor
        else:
            # Get processor from factory
            processor = self.factory.get_processor(path)

            # Special case for folder with custom options
            if path.is_dir() and (recursive or file_extensions):
                processor = self.factory.create_folder_processor(
                    recursive=recursive, file_extensions=file_extensions
                )

        if not processor:
            return {
                "success": False,
                "error": f"No processor available for path: {file_path}",
                "path": file_path,
            }

        # Process the path
        try:
            result = processor.process(path, tenant_id, source, author, db)
            return {"success": True, "path": file_path, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e), "path": file_path}

    def register_custom_processor(self, processor: PathProcessor):
        """Register a custom processor"""
        self.factory.register_processor(processor)


# Singleton instance
path_processing_service = PathProcessingService()
