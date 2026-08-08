"""Privacy controls for the memory subsystem."""

from fastapi import APIRouter, Depends

from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ShortTermMemory
from app.services.auth_services.auth_service import get_current_user

router = APIRouter(prefix="/memory", tags=["memory"])


@router.delete("/clear")
async def clear_memory(current_user=Depends(get_current_user)):
    """Clear all memories owned by the authenticated user."""
    tenant_id = str(current_user.tenant_id)
    user_id = str(current_user.id)
    short_term_cleared = ShortTermMemory().clear_all(tenant_id, user_id)
    semantic_cleared = SemanticMemory().clear_user(user_id, tenant_id)
    episodes_cleared = EpisodicMemory().clear_user(user_id, tenant_id)
    return {
        "success": True,
        "short_term_sessions_cleared": short_term_cleared,
        "semantic_cleared": semantic_cleared,
        "episodes_cleared": episodes_cleared,
    }
