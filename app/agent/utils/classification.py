"""Shared question-type classification — single source of truth.

Previously this module maintained its own keyword lists that could contradict
the production router's ``calculate_deterministic_route()`` patterns, leading
to thought-node tool-selection hints that disagreed with the routing decision
already made upstream.

Now ``classify_question_type`` delegates to the same deterministic route
calculator used by the router, mapping its output to ``"data"`` / ``"knowledge"``.
The legacy keyword lists are kept only as a tiebreaker for ambiguous routes
(COMPLEX / DIRECT_QA / GREETING) where the router does not emit a clear
SQL-vs-retrieval signal.
"""

from __future__ import annotations

# Legacy keyword sets — used only as a fallback tiebreaker for ambiguous routes.
_DATA_KEYWORDS = (
    "how many",
    "count",
    "total",
    "sum",
    "average",
    "number of",
    "revenue",
    "sales",
    "statistics",
    "database",
    "كم",          # Arabic: "how many"
    "عدد",         # Arabic: "count/number"
    "مجموع",       # Arabic: "total/sum"
    "متوسط",       # Arabic: "average"
    "إجمالي",      # Arabic: "total"
)

_KNOWLEDGE_KEYWORDS = (
    "what is",
    "explain",
    "describe",
    "how does",
    "why",
    "definition",
    "information",
    "policy",
    "ما هو",       # Arabic: "what is"
    "اشرح",        # Arabic: "explain"
    "وصف",         # Arabic: "describe"
    "لماذا",       # Arabic: "why"
    "تعريف",       # Arabic: "definition"
)

# Router routes that unambiguously signal SQL intent.
_SQL_ROUTES = {"OBVIOUS_SQL", "SIMPLE_SQL"}
# Router routes that unambiguously signal retrieval/knowledge intent.
_RETRIEVAL_ROUTES = {"SIMPLE_RETRIEVAL"}


def classify_question_type(question: str) -> str:
    """
    Return ``"data"`` (SQL) or ``"knowledge"`` (retrieval) for *question*.

    Delegates to the production router's deterministic classifier so the
    thought-node's tool-selection hint is always consistent with the routing
    decision already made upstream.  Falls back to keyword scoring for
    ambiguous routes.
    """
    from app.agent.core.intent_regex_pattern import calculate_deterministic_route

    route = calculate_deterministic_route(question)

    if route in _SQL_ROUTES:
        return "data"
    if route in _RETRIEVAL_ROUTES:
        return "knowledge"

    # Ambiguous route (COMPLEX, DIRECT_QA, GREETING, UNKNOWN) —
    # use keyword scoring as a tiebreaker.
    q = question.lower()
    data_score = sum(kw in q for kw in _DATA_KEYWORDS)
    knowledge_score = sum(kw in q for kw in _KNOWLEDGE_KEYWORDS)
    return "data" if data_score > knowledge_score else "knowledge"


def asks_for_db_data(question: str) -> bool:
    """Return True if the question is most likely answered by a SQL query."""
    return classify_question_type(question) == "data"
