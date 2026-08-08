from pathlib import Path
from typing import List, Dict, Any

from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredHTMLLoader,
    CSVLoader,
    UnstructuredMarkdownLoader,
    UnstructuredPowerPointLoader,
    UnstructuredExcelLoader,
)
from langchain_core.documents import Document


# Maps file extension → (loader class, human-readable file_type label)
# file_type is stored as a Qdrant payload field and indexed for fast filtering.
_EXTENSION_MAP: dict[str, tuple] = {
    ".txt": (TextLoader, "text"),
    ".pdf": (PyPDFLoader, "pdf"),
    ".docx": (UnstructuredWordDocumentLoader, "word"),
    ".doc": (UnstructuredWordDocumentLoader, "word"),
    ".html": (UnstructuredHTMLLoader, "html"),
    ".csv": (CSVLoader, "csv"),
    ".md": (UnstructuredMarkdownLoader, "markdown"),
    ".pptx": (UnstructuredPowerPointLoader, "powerpoint"),
    ".ppt": (UnstructuredPowerPointLoader, "powerpoint"),
    ".xlsx": (UnstructuredExcelLoader, "excel"),
    ".xls": (UnstructuredExcelLoader, "excel"),
}


class DocumentLoader:
    @staticmethod
    def load_file(
        file_path: str,
        custom_metadata: Dict[str, Any] = None,
    ) -> List[Document]:
        """
        Load a file and attach rich metadata to every page/chunk.

        Automatically injects the following fields into ``doc.metadata`` so
        they are available as Qdrant payload for indexed filtering:

        - ``file_type``   — normalised type label (``"pdf"``, ``"word"`` …)
        - ``file_name``   — original filename without directory path
        - ``language``    — language tag; defaults to ``"unknown"`` unless the
                            caller supplies it in ``custom_metadata``.

        These fields are also used in ``ensure_payload_indexes()`` in
        ``QdrantRepository`` to create Qdrant payload indexes so that filter
        queries (e.g. ``file_type = "pdf"``) use an index rather than a full
        collection scan.

        Args:
            file_path:       Path to the file on disk.
            custom_metadata: Extra metadata dict (e.g. ``tenant_id``,
                             ``department``, ``language``, ``author``).
                             Values here override auto-detected defaults.

        Returns:
            List of LangChain Document objects with merged metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError:        If the file extension is not supported.
        """
        path = Path(file_path)

        # 1. Existence check
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 2. Resolve extension
        extension = path.suffix.lower()
        if extension not in _EXTENSION_MAP:
            raise ValueError(
                f"Unsupported file type: '{extension}'. "
                f"Supported: {', '.join(sorted(_EXTENSION_MAP))}"
            )

        loader_cls, file_type_label = _EXTENSION_MAP[extension]

        # 3. Construct loader (TextLoader needs encoding kwarg)
        if loader_cls is TextLoader:
            loader = loader_cls(str(path), encoding="utf-8")
        else:
            loader = loader_cls(str(path))

        # 4. Load pages
        documents = loader.load()

        # 5. Build base metadata that will be injected into every chunk.
        #    These are the fields that have Qdrant payload indexes.
        base_metadata: Dict[str, Any] = {
            "file_type": file_type_label,  # indexed KEYWORD field
            "file_name": path.name,  # useful for source attribution
            "language": "unknown",  # caller can override via custom_metadata
        }

        # 6. Merge: base_metadata first, then custom_metadata overrides.
        #    This ensures tenant_id / department / language from the caller
        #    always win over our defaults.
        merged_metadata: Dict[str, Any] = {**base_metadata, **(custom_metadata or {})}

        # 7. Attach merged metadata to every document page
        for doc in documents:
            doc.metadata.update(merged_metadata)

        print(
            f"[✅] Loaded {len(documents)} page(s) from '{path.name}' "
            f"[type={file_type_label}, lang={merged_metadata.get('language', 'unknown')}]"
        )
        return documents
