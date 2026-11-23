"""Tool abstraction and registry for agent actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.agent.core.state import AgentState


@dataclass
class ToolObservation:
    tool: str
    observation: str
    has_data: bool = False


# الكود ده بيمثل Tool Framework في الـ 
# Agent. 
# بدل ما الـ Agent 
# يعرف ينفذ SQL أو Retrieval بنفسه
# ، هو عنده Registry فيه كل الأدوات، وكل أداة لها Interface موحد.  # noqa: E501

# الفكرة العامة كده:

#                  Agent
#                    │
#                    ▼
#             Tool Registry
#           ┌────────┴────────┐
#           │                 │
#           ▼                 ▼
#       SQL Tool       Retrieval Tool
#           │                 │
#           ▼                 ▼
#      SQL Database      Vector DB / RAG

# الميزة إن الـ Agent مش محتاج يعرف تفاصيل كل Tool، هو بس يقول:
# "هاتلي Tool اسمها sql"

# أولاً الـ dataclass
# ToolObservation
# @dataclass
# class ToolObservation:
#     tool: str
#     observation: str
#     has_data: bool = False

# ده مجرد Object لتسجيل إيه اللي حصل بعد تنفيذ الأداة.
# مثلاً

# ToolObservation(
#     tool="sql",
#     observation="Returned 15 rows",
#     has_data=True
# )

# أو

# ToolObservation(
#     tool="retrieval",
#     observation="No relevant documents",
#     has_data=False
# )


@dataclass
class ToolResult:
    observation: str
    has_data: bool = False
    state_updates: dict[str, Any] = field(default_factory=dict)

    def to_observation_record(self, tool_name: str) -> ToolObservation:
        return ToolObservation(
            tool=tool_name,
            observation=self.observation,
            has_data=self.has_data,
        )


# دي نتيجه التول الحقيقه
# مثلاً SQL Tool

# ToolResult(
#     observation="Retrieved 8 employees",
#     has_data=True,
#     state_updates={
#         "last_sql": "...",
#         "sql_result": rows
#     }
# )

# أو Retrieval

# ToolResult(
#     observation="Found 3 documents",
#     has_data=True,
#     state_updates={
#         "retrieval_context": docs
#     }
# )


class AgentTool(ABC):
    name: str
    attempted_key: str
    has_data_key: str

    @abstractmethod
    def run(self, state: AgentState) -> ToolResult: ...

    def _fingerprint(self, state: AgentState) -> dict:
        """Return the dict used for idempotency key building.

        Override in subclasses to include tool-specific inputs.
        The default returns an empty dict so existing tools continue to work.
        """
        return {}

    def safe_run(self, state: AgentState) -> ToolResult:
        """Idempotency-guarded version of run()."""
        from app.agent.core.config import agent_settings

        if not agent_settings.tool_idempotency_enabled:
            return self.run(state)

        from app.agent.tools.idempotency import (
            acquire_lock,
            build_key,
            cache_tool_result,
            fetch_cached_result,
            release_lock,
        )
        import logging

        logger = logging.getLogger(__name__)

        tenant_id = state.get("tenant_id", "")
        run_id = state.get("run_id", "")
        sub_idx = state.get("current_sub_question_index", 0)
        fingerprint = {**self._fingerprint(state), "sub_idx": sub_idx}
        key = build_key(self.name, tenant_id, run_id, fingerprint)

        # 1. Cache hit → return immediately
        cached = fetch_cached_result(key)
        if cached is not None:
            logger.info(
                "Idempotency cache hit for tool=%s key=%s", self.name, key[:12]
            )
            return cached

        # 2. Acquire in-flight lock
        ttl = agent_settings.tool_idempotency_lock_ttl
        if not acquire_lock(key, ttl=ttl):
            logger.warning(
                "Tool %s already in-flight (lock held), falling through to run()",
                self.name,
            )
            return self.run(state)

        try:
            result = self.run(state)
            # 3. Cache result
            result_ttl = getattr(
                agent_settings,
                f"tool_idempotency_{self.name}_ttl",
                agent_settings.tool_idempotency_sql_ttl,
            )
            cache_tool_result(key, result, ttl=result_ttl)
            return result
        finally:
            release_lock(key)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def attempted_keys(self) -> dict[str, str]:
        return {name: tool.attempted_key for name, tool in self._tools.items()}

    def has_data_keys(self) -> dict[str, str]:
        return {name: tool.has_data_key for name, tool in self._tools.items()}


tool_registry = ToolRegistry()
