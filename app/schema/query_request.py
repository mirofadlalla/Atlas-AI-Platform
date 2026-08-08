from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for RAG query endpoints."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        strip_whitespace=True,
        description="The user question to answer using the knowledge base (1–2000 characters).",
    )
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
