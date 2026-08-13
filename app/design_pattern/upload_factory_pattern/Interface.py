# app/processors/base_processor.py
from abc import ABC, abstractmethod
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Dict, Any


class PathProcessor(ABC):
    """Base interface for all path processors"""

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        """Check if this processor can handle the given path"""

    @abstractmethod
    def process(
        self, path: Path, tenant_id: str, source: str, author: str, db: Session
    ) -> Dict[str, Any]:
        """Process the path and return results"""
