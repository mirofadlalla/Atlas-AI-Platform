"""Shared question-type classification heuristics."""

DATA_PATTERNS = (
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
)

KNOWLEDGE_PATTERNS = (
    "what is",
    "explain",
    "describe",
    "how does",
    "why",
    "definition",
    "information",
)


def classify_question_type(question: str) -> str:
    q = question.lower()
    data_score = sum(p in q for p in DATA_PATTERNS)
    knowledge_score = sum(p in q for p in KNOWLEDGE_PATTERNS)

    if data_score > knowledge_score:
        return "data"
    if knowledge_score > data_score:
        return "knowledge"
    return "knowledge"


def asks_for_db_data(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in DATA_PATTERNS)
