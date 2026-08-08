"""LLM-based extraction of durable facts from completed interactions."""

from __future__ import annotations

import json
import logging

from app.agent.utils.llm import call_agent_llm
from app.agent.utils.parsing import extract_first_json_block
from app.memory.semantic_memory import SemanticMemory

logger = logging.getLogger(__name__)


class MemoryExtractor:
    def extract_and_store(
        self, question: str, answer: str, user_id: str, tenant_id: str
    ) -> list[str]:
        if not question.strip() or not answer.strip():
            return []
        prompt = f"""Extract durable memory from this completed interaction. Keep only user preferences,
stable facts, or reusable database/tool hints. Never store secrets, credentials, transient requests,
unsupported claims, or chain-of-thought. Return ONLY JSON:
{{"memories":[{{"content":"...","memory_type":"fact|preference|tool_hint","importance":0.0}}]}}
Use an empty list if nothing is worth retaining.

USER QUESTION: {question}
ASSISTANT ANSWER: {answer}"""
        try:
            response = call_agent_llm(prompt, tier="generation", tenant_id=tenant_id)
            extracted = json.loads(
                extract_first_json_block(response.get("content", ""))
            ).get("memories", [])
        except Exception as exc:
            logger.warning("Semantic memory extraction failed: %s", exc)
            return []

        store = SemanticMemory()
        ids: list[str] = []
        for item in extracted[:5]:
            if not isinstance(item, dict):
                continue
            try:
                memory_id = store.store(
                    str(item.get("content", "")),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    memory_type=str(item.get("memory_type", "fact")),
                    importance=float(item.get("importance", 0.5)),
                )
                if memory_id:
                    ids.append(memory_id)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping invalid extracted semantic memory: %s", exc)
        return ids
