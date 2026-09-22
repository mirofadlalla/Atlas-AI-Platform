"""Retrieval tool execution node with CRAG relevance grading."""

import asyncio
import logging

from app.agent.core.config import agent_settings
from app.agent.core.relevance_grader import grade_retrieval_relevance
from app.agent.core.state import AgentState
from app.agent.nodes.base import (
    apply_tool_result,
    emit_node_status,
    emit_thought_chunk,
    run_node,
)
from app.agent.observability.logging import log_node_event
from app.agent.tools.base import ToolResult, tool_registry
from app.agent.tools.retrieval_tool import RetrievalTool, _UNTRUSTED_PREFIX
from app.agent.utils.llm import llm_usage_updates
from app.agent.utils.state_helpers import get_current_question

logger = logging.getLogger(__name__)

tool_registry.register(RetrievalTool())


async def retrieval_node(state: AgentState) -> dict:
    """
    Retrieve documents from the vector database and grade their relevance.

    Flow:
    1. Fetch candidate document chunks via RetrievalTool.
    2. Grade relevance of chunks (CRAG-style pre-filter + LLM grading).
    3. If relevant docs found: set retrieval_has_results = True and populate
       retrieval_context strictly with relevant chunks.
    4. If 0 relevant docs: set retrieval_has_results = False, retrieval_context = None,
       allowing downstream router to fall back to SQL.
    """
    await emit_node_status(
        "retrieval_tool",
        "Document Retrieval",
        "Searching knowledge base and grading relevance...",
    )

    async def _inner(s: AgentState):
        tool = tool_registry.get("retrieval")
        if tool is None:
            raise RuntimeError("Retrieval tool is not registered in the tool registry")

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.run, s),
                timeout=agent_settings.retrieval_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout_s = agent_settings.retrieval_timeout_seconds
            logger.error("Retrieval tool timed out after %.1fs", timeout_s)
            result = ToolResult(
                observation=(
                    f"Error: Document retrieval timed out after {timeout_s:.0f}s. "
                    "The vector store may be under heavy load."
                ),
                has_data=False,
                state_updates={
                    "retrieval_attempted": True,
                    "retrieval_has_results": False,
                    "relevant_docs": [],
                    "retrieval_context": None,
                    "degraded": True,
                    "degraded_reason": f"Retrieval timed out after {timeout_s:.0f}s",
                },
            )

        # ── CRAG Relevance Grading Step ───────────────────────────────────────
        question = get_current_question(s)
        raw_docs = result.state_updates.get("raw_retrieved_docs", [])
        grading_usage: dict = {}

        if result.has_data and raw_docs:
            grading_result = await grade_retrieval_relevance(
                question=question,
                docs=raw_docs,
                tenant_id=s.get("tenant_id"),
            )
            grading_usage = grading_result.usage

            if grading_result.is_relevant:
                formatted = [
                    f"{i}. {doc['content']}..."
                    for i, doc in enumerate(grading_result.relevant_docs, 1)
                ]
                graded_context = _UNTRUSTED_PREFIX + "\n".join(formatted)
                result.has_data = True
                result.observation = (
                    f"Retrieved {len(grading_result.relevant_docs)} relevant document(s) "
                    f"(graded from {len(raw_docs)} candidates):\n{graded_context[:500]}..."
                )
                result.state_updates["retrieval_context"] = graded_context
                result.state_updates["retrieval_has_results"] = True
                result.state_updates["relevant_docs"] = grading_result.relevant_docs
                await emit_thought_chunk(
                    f"\n[Relevance Grader] Graded {len(raw_docs)} chunk(s) -> "
                    f"{len(grading_result.relevant_docs)} relevant chunk(s) accepted.\n"
                )
            else:
                result.has_data = False
                result.observation = (
                    f"No relevant documents found after relevance grading "
                    f"(0/{len(raw_docs)} chunks relevant to question)."
                )
                result.state_updates["retrieval_context"] = None
                result.state_updates["retrieval_has_results"] = False
                result.state_updates["relevant_docs"] = []
                if grading_result.degraded:
                    result.state_updates["degraded"] = True
                    result.state_updates["degraded_reason"] = (
                        grading_result.degraded_reason
                    )
                await emit_thought_chunk(
                    f"\n[Relevance Grader] Graded {len(raw_docs)} candidate chunk(s) -> "
                    f"0 relevant chunks found. Marking retrieval insufficient.\n"
                )
        else:
            result.state_updates["relevant_docs"] = []
            result.state_updates["retrieval_has_results"] = False
            result.state_updates["retrieval_context"] = None

        update = apply_tool_result(s, result, "retrieval")
        if grading_usage:
            update.update(llm_usage_updates(grading_usage, s))

        await emit_thought_chunk(
            f"[Document Retrieval] Process completed. Observation: {result.observation[:300]}\n"
        )
        log_node_event(
            logger, s, "retrieval_tool", "completed", has_data=result.has_data
        )
        return update

    return await run_node("retrieval_tool", state, _inner)
