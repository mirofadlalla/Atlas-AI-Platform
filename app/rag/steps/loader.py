import os
from pathlib import Path
from typing import List, Dict, Any

from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredHTMLLoader
)
from langchain_core.documents import Document

class DocumentLoader:
    
    @staticmethod
    def load_file(file_path: str,
                   custom_metadata: Dict[str, Any] = None) -> List[Document]:
        """
        Load a file and attach custom metadata (e.g., tenant_id).
        
        Args:
            file_path (str): Path to the file.
            custom_metadata (Dict[str, Any], optional): Metadata to attach to each document.
        
        Returns:
            List[Document]: List of LangChain Document objects.
        """
        path = Path(file_path)
        
        # 1. Check if file exists
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 2. Extract file extension (lowercase for consistency, e.g. .PDF → .pdf)
        extension = path.suffix.lower()

        # 3. Choose appropriate loader based on file type
        if extension == ".txt":
            loader = TextLoader(str(path), encoding="utf-8")  # UTF-8 important for Arabic support
        elif extension == ".pdf":
            loader = PyPDFLoader(str(path))
        elif extension == ".docx":
            loader = UnstructuredWordDocumentLoader(str(path))
        elif extension == ".html":
            loader = UnstructuredHTMLLoader(str(path))
        else:
            raise ValueError(f"[❌] Unsupported file type: {extension}")
        
        # 4. Load file content → returns a list of Document objects
        documents = loader.load()

        # 5. Attach custom metadata (e.g., tenant_id) to each document
        if custom_metadata:
            for doc in documents:
                doc.metadata.update(custom_metadata)

        print(f"[✅] Successfully loaded {len(documents)} pages from {path.name}")
        return documents


# x = DocumentLoader.load_file("E:\\pyDS\\Enterprise Multi-Tenant Agentic RAG Infrastructure\\app\\rag\\data\\Omar_Fadlallah_ML_Engineer.pdf", custom_metadata={"tenant_id": 123})

# print(x)