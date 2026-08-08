"""Agent module for enterprise RAG system."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "agent_app":
        from app.agent.core.graph import agent_app

        return agent_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["agent_app"]
