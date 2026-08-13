"""
Routes for AI Agent endpoints.

Thin HTTP adapter — all business logic lives in AgentController.
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.auth_services.auth_service import get_current_user
from app.controllers.agent_controller import AgentController

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


class AgentRequest(BaseModel):
    """Request model for agent endpoints."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        strip_whitespace=True,
        description="The question for the agent to reason about (1–2000 characters).",
    )
    run_id: str | None = None  # optional idempotency key for retries
    session_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/ask-agent")
async def ask_agent(
    request: AgentRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream agent responses for a question with real-time reasoning visibility.

    Returns Server-Sent Events (SSE) with tool_start / thought / tool_end /
    answer / complete / done / error event types.
    """
    return AgentController.ask_agent_stream(request, current_user, db)


@router.post("/ask-agent-batch")
async def ask_agent_batch(
    request: AgentRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Non-streaming agent endpoint that returns the complete response at once.

    Use when you prefer a single JSON response over SSE streaming.
    """
    return await AgentController.ask_agent_batch(request, current_user, db)
