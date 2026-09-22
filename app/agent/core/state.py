from __future__ import annotations

from typing import TypedDict


class SubAnswer(TypedDict):
    question: str
    answer: str


class AgentState(TypedDict, total=False):
    question: str
    tenant_id: str
    user_id: str
    session_id: str | None
    conversation_history: list[dict[str, str]]
    recalled_memories: list[str]
    episode_context: str
    working_memory_tokens: int
    context_sources: list[str]
    run_id: str
    start_time: float

    # Fast Hybrid Routing & Memory Flags
    intent: str | None
    needs_short_term: bool
    needs_semantic: bool
    needs_episodic: bool
    direct_response: str | None

    thought: str | None
    thoughts: list[str]
    last_action: str | None
    observation: str | None
    observation_history: list[str]

    last_sql: str | None
    sql_result: str | None
    sql_attempted: bool
    sql_has_results: bool

    # Retrieval & CRAG relevance grading state
    # retrieval_has_results: True ONLY when retrieved chunks pass similarity pre-filter and LLM relevance grading
    # retrieval_context: Formatted string containing ONLY relevant_docs (None if 0 relevant)
    # relevant_docs: Filtered list of doc dicts that survived pre-filter and LLM grading
    retrieval_context: str | None
    retrieval_attempted: bool
    retrieval_has_results: bool
    relevant_docs: list[dict] | None

    step_count: int
    total_step_count: int
    total_cost: float
    llm_cost_usd: float
    input_tokens: int
    output_tokens: int

    final_answer: str | None
    degraded: bool
    degraded_reason: str | None
    data_sources: list[str]
    action_history: list[str]
    tool_observations: list[dict[str, str | bool]]

    original_question: str | None
    sub_questions: list[str]
    sub_answers: list[SubAnswer]
    current_sub_question_index: int
