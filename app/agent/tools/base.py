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

# الكود ده بيمثل Tool Framework في الـ Agent. بدل ما الـ Agent يعرف ينفذ SQL أو Retrieval بنفسه، هو عنده Registry فيه كل الأدوات، وكل أداة لها Interface موحد.

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
    def run(self, state: AgentState) -> ToolResult:
        ...



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
