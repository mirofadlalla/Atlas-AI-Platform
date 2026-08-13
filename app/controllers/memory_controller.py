"""
Memory controller.

Handles privacy controls and clearing of all memory subsystems for a user.
"""

import logging

from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ShortTermMemory

logger = logging.getLogger(__name__)


class MemoryController:
    """Controller for all /memory endpoints."""

    @staticmethod
    def clear_memory(current_user) -> dict:
        """
        Clear all memories (short-term, semantic, episodic) for the authenticated user.

        Returns:
            dict with success flag and counts of cleared records per memory type.
        """
        tenant_id = str(current_user.tenant_id)
        user_id = str(current_user.id)

        short_term_cleared = ShortTermMemory().clear_all(tenant_id, user_id)
        semantic_cleared = SemanticMemory().clear_user(user_id, tenant_id)
        episodes_cleared = EpisodicMemory().clear_user(user_id, tenant_id)

        logger.info(
            f"Memory cleared - user={user_id} tenant={tenant_id} "
            f"short_term={short_term_cleared} semantic={semantic_cleared} episodes={episodes_cleared}"
        )

        return {
            "success": True,
            "short_term_sessions_cleared": short_term_cleared,
            "semantic_cleared": semantic_cleared,
            "episodes_cleared": episodes_cleared,
        }
