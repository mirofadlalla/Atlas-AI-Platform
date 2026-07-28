# app/processors/processor_factory.py
from pathlib import Path
from typing import List, Optional
from .Interface import PathProcessor
from .file_processor import FileProcessor
from .folder_processor import FolderProcessor

class PathProcessorFactory:
    """Factory for creating appropriate path processors"""
    
    def __init__(self):
        self._processors = []
        self._register_default_processors()
    
    def _register_default_processors(self):
        """Register default processors"""
        self.register_processor(FileProcessor())
        self.register_processor(FolderProcessor())
        # self.register_processor(CustomProcessor())
    
    def register_processor(self, processor: PathProcessor):
        """Register a new processor"""
        self._processors.append(processor)
    
    def get_processor(self, path: Path) -> Optional[PathProcessor]:
        """Get the appropriate processor for the given path"""
        for processor in self._processors:
            if processor.can_handle(path):
                return processor
        return None
    
    def create_folder_processor(self, recursive: bool = False, file_extensions: List[str] = None) -> FolderProcessor:
        """Create a customized folder processor"""
        return FolderProcessor(recursive=recursive, file_extensions=file_extensions)


# Singleton instance
processor_factory = PathProcessorFactory()