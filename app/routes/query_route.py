"""
Routes for RAG query/answer endpoints.

Thin HTTP adapter — all business logic lives in QueryController.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.schema.query_request import QueryRequest
from app.services.auth_services.auth_service import get_current_user
from app.controllers.query_controller import QueryController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query")


@router.post("/ask")
async def ask_question(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Answer a user question using the RAG pipeline with streaming SSE response."""
    rate_limit(
        user_id=str(current_user.id), role=current_user.role, endpoint="/query/ask"
    )
    return QueryController.ask(request, current_user, db)


@router.post("/retrieve")
async def retrieve_documents(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve relevant documents for a query without generating an answer."""
    rate_limit(
        user_id=str(current_user.id), role=current_user.role, endpoint="/query/retrieve"
    )
    return QueryController.retrieve(request, current_user, db)


@router.get("/cost-analytics")
async def get_cost_analytics(
    current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get cost analytics for the current tenant."""
    return QueryController.get_cost_analytics(current_user, db)


@router.get("/runs")
async def get_runs(
    current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all query runs for the current tenant."""
    return QueryController.get_runs(current_user, db)
