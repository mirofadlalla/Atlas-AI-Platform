"""Structured logging helpers for agent runs."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.core.state import AgentState


def get_agent_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_node_event(
    logger: logging.Logger,
    state: AgentState,
    node: str,
    event: str,
    **extra: Any,
) -> None:
    payload = {
        "run_id": state.get("run_id"),
        "tenant_id": state.get("tenant_id"),
        "node": node,
        "event": event,
        **extra,
    }
    logger.info("%s %s", node, event, extra={"agent": payload})
