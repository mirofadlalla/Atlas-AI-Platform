"""Tool abstraction and registry for agent actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.agent.core.state import AgentState


@dataclass
class ToolResult:
    observation: str
    has_data: bool = False
    state_updates: dict[str, Any] = field(default_factory=dict)


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
