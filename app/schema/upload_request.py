from pydantic import BaseModel
from typing import Optional, List


class UploadRequest(BaseModel):
    file_path: str
    tenant_id: str
    source: str
    author: str
    recursive: Optional[bool] = False
    file_extensions: Optional[List[str]] = None
