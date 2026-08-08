"""Core agent components."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "AgentState":
        from app.agent.core.state import AgentState

        return AgentState
    elif name == "route_action":
        from app.agent.core.router import route_action

        return route_action
    elif name == "agent_app":
        from app.agent.core.graph import agent_app

        return agent_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AgentState", "agent_app", "route_action"]
