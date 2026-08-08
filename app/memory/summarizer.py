"""LLM summarization for a session's raw conversation turns."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SessionSummarizer:
    def summarize(self, turns: list[dict[str, str]], tenant_id: str) -> str:
        conversation = "\n".join(f"{turn.get('role', 'user').title()}: {turn.get('content', '')}" for turn in turns)
        if not conversation.strip():
            return ""
        prompt = f"""Summarize this user session in 2-3 factual sentences for future context.
Include user goals, conclusions, and unresolved follow-ups. Do not include chain-of-thought,
credentials, or unsupported claims.\n\nCONVERSATION:\n{conversation[:12000]}"""
        try:
            # Delayed import keeps API startup independent from agent graph setup.
            from app.agent.utils.llm import call_agent_llm

            return call_agent_llm(prompt, tier="generation", tenant_id=tenant_id)["content"].strip()
        except Exception as exc:
            logger.warning("Episode summarization failed: %s", exc)
            return ""
