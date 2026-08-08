from pathlib import Path
from app.controllers.ingest_rag_controller import IngestController

from sqlalchemy.orm import Session


def process_upload(
    file_path: str, tenant_id: str, source: str, author: str, db: Session
):
    path = Path(file_path)

    if not path.exists():
        return {"error": f"Path does not exist: {file_path}"}

    results = []

    if path.is_file():
        # Single file
        print(f"📄 Processing file: {path.name}")
        result = IngestController.ingest_file(
            file_path=str(path),
            tenant_id=tenant_id,
            source=source,
            author=author,
            db=db,
        )
        results.append(
            {
                "file": path.name,
                "task_id": result.get("task_id"),
                "status": result.get("status"),
            }
        )

    elif path.is_dir():
        # All files in folder
        print(f"📁 Processing folder: {path.name}")
        for file in path.iterdir():
            if file.is_file():
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
                        "task_id": result.get("task_id"),
                        "status": result.get("status"),
                    }
                )

    return {"message": f"Processed {len(results)} files", "results": results}
