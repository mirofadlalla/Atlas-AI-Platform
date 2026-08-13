"""Privacy controls for the memory subsystem.

Thin HTTP adapter — all business logic lives in MemoryController.
"""

from fastapi import APIRouter, Depends

from app.services.auth_services.auth_service import get_current_user
from app.controllers.memory_controller import MemoryController

router = APIRouter(prefix="/memory", tags=["memory"])


@router.delete("/clear")
async def clear_memory(current_user=Depends(get_current_user)):
    """Clear all memories owned by the authenticated user."""
    return MemoryController.clear_memory(current_user)
