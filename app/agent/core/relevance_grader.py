"""
Corrective RAG (CRAG) Relevance Grader for Retrieval Path.

State Semantics:
- `retrieval_has_results`: True ONLY if retrieved chunks pass similarity pre-filter
  and LLM relevance grading.
- `relevant_docs`: Filtered list of doc dicts that survived pre-filter and LLM grading.
- `retrieval_context`: Formatted string built exclusively from `relevant_docs` (None if 0 relevant).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.core.config import agent_settings
from app.agent.utils.llm import async_call_agent_llm_stream
from app.agent.utils.parsing import extract_first_json_block

logger = logging.getLogger(__name__)


@dataclass
class GradingResult:
    """Result of 2-stage retrieval relevance evaluation."""

    is_relevant: bool
    relevant_docs: list[dict[str, Any]]
    raw_docs: list[dict[str, Any]]
    pre_filtered_count: int
    graded_indices: list[int]
    degraded: bool = False
    degraded_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def pre_filter_docs(
    docs: list[dict[str, Any]], floor: float = 0.0
) -> list[dict[str, Any]]:
    """
    Stage 1: Discard chunks below a similarity score floor with 0 LLM calls.

    If a doc does not have a score attribute, it is kept by default.
    """
    if floor <= 0.0:
        return list(docs)

    surviving: list[dict[str, Any]] = []
    for doc in docs:
        score = doc.get("score")
        if score is None or float(score) >= floor:
            surviving.append(doc)
    return surviving


def build_grading_prompt(question: str, docs: list[dict[str, Any]]) -> str:
    """Build structured prompt for LLM relevance classification."""
    formatted_chunks = []
    for idx, doc in enumerate(docs, 1):
        content = doc.get("content", "").strip()
        formatted_chunks.append(f"[{idx}] {content}")

    chunks_text = "\n\n".join(formatted_chunks)

    return (
        f"You are an expert retrieval relevance grader.\n"
        f"Evaluate whether any of the following retrieved document chunks contain factual "
        f"information that is relevant and useful for answering the user's question.\n\n"
        f'User Question: "{question}"\n\n'
        f"Retrieved Document Chunks:\n"
        f"{chunks_text}\n\n"
        f"Instructions:\n"
        f"1. Identify the 1-based index numbers of chunks that contain relevant facts or direct answers.\n"
        f"2. If NONE of the chunks contain relevant information for the question, return an empty list: [].\n"
        f"3. Return ONLY a JSON object with this exact structure:\n"
        f"{{\n"
        f'  "relevant_indices": [1, 2],\n'
        f'  "reasoning": "Brief explanation of why chunks are or are not relevant"\n'
        f"}}"
    )


async def grade_retrieval_relevance(
    question: str,
    docs: list[dict[str, Any]],
    tenant_id: str | int | None = None,
) -> GradingResult:
    """
    2-Stage Relevance Grader:
    1. Pre-filter by similarity score floor (deterministic, 0 LLM calls).
    2. LLM grading (fast/cheap tier) with structured JSON output.

    Fail-safe: On any LLM or parsing failure, fails closed (is_relevant=False)
    so execution smoothly falls through to the SQL path without false hallucination.
    """
    if not docs:
        return GradingResult(
            is_relevant=False,
            relevant_docs=[],
            raw_docs=[],
            pre_filtered_count=0,
            graded_indices=[],
        )

    # ── Stage 1: Deterministic Pre-filter ─────────────────────────────────────
    score_floor = agent_settings.retrieval_score_floor
    surviving_docs = pre_filter_docs(docs, floor=score_floor)
    pre_filtered_count = len(docs) - len(surviving_docs)

    if not surviving_docs:
        logger.info(
            "All %d candidate doc(s) filtered out by score floor (%.2f). Skipping LLM grading.",
            len(docs),
            score_floor,
        )
        return GradingResult(
            is_relevant=False,
            relevant_docs=[],
            raw_docs=docs,
            pre_filtered_count=pre_filtered_count,
            graded_indices=[],
        )

    # If grading is disabled via configuration, accept all surviving docs
    if not agent_settings.retrieval_grading_enabled:
        return GradingResult(
            is_relevant=True,
            relevant_docs=surviving_docs,
            raw_docs=docs,
            pre_filtered_count=pre_filtered_count,
            graded_indices=list(range(1, len(surviving_docs) + 1)),
        )

    # ── Stage 2: LLM Relevance Grading ───────────────────────────────────────
    prompt = build_grading_prompt(question, surviving_docs)
    tier = "routing"  # Uses fast/cheap model tier

    try:
        response_dict = await async_call_agent_llm_stream(
            prompt=prompt,
            tier=tier,
            tenant_id=str(tenant_id) if tenant_id is not None else None,
            event_type="stream_thought_chunk",
        )

        raw_content = response_dict.get("content", "")
        parsed = json.loads(extract_first_json_block(raw_content))
        raw_indices = parsed.get("relevant_indices", [])

        # Validate and sanitize 1-based indices
        valid_indices: list[int] = []
        for idx in raw_indices:
            try:
                i = int(idx)
                if 1 <= i <= len(surviving_docs) and i not in valid_indices:
                    valid_indices.append(i)
            except (ValueError, TypeError):
                continue

        relevant_docs = [surviving_docs[i - 1] for i in valid_indices]
        is_relevant = len(relevant_docs) > 0

        logger.info(
            "Relevance grading finished: %d/%d surviving chunks judged relevant (valid indices: %s)",
            len(relevant_docs),
            len(surviving_docs),
            valid_indices,
        )

        return GradingResult(
            is_relevant=is_relevant,
            relevant_docs=relevant_docs,
            raw_docs=docs,
            pre_filtered_count=pre_filtered_count,
            graded_indices=valid_indices,
            usage=response_dict,
        )

    except Exception as exc:
        # Fail-safe behavior: do NOT fail open (which would reintroduce the bug).
        # Fail closed (is_relevant=False) so the graph falls back to SQL if applicable.
        logger.warning(
            "LLM relevance grading failed: %s; failing safe (marking retrieval not relevant)",
            exc,
            exc_info=True,
        )
        return GradingResult(
            is_relevant=False,
            relevant_docs=[],
            raw_docs=docs,
            pre_filtered_count=pre_filtered_count,
            graded_indices=[],
            degraded=True,
            degraded_reason=f"LLM relevance grading failed: {exc}",
        )
