import time
from unittest.mock import MagicMock, patch

from cachetools import TTLCache
import pytest
from app.services.recommended_qa_service import RecommendedQAService


def test_recommended_qa_tenant_isolation_and_limit():
    db = MagicMock()
    tenant_1 = "tenant-uuid-1"
    tenant_2 = "tenant-uuid-2"

    # Reset in-memory cache
    RecommendedQAService._tenant_cache = {}

    # Mock DB queries
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    # Add question for tenant 1
    with (
        patch.object(db, "add"),
        patch.object(db, "commit"),
        patch.object(db, "refresh"),
    ):
        item1 = RecommendedQAService.add_recommended_question(
            tenant_id=tenant_1, question="Tenant 1 Q1?", answer="Tenant 1 A1", db=db
        )
        assert item1["question"] == "Tenant 1 Q1?"

    # Check tenant 1 and tenant 2 cache isolation
    t1_questions = RecommendedQAService.get_recommended_questions(tenant_1)
    t2_questions = RecommendedQAService.get_recommended_questions(tenant_2)

    assert len(t1_questions) == 1
    assert len(t2_questions) == 0

    # Fill tenant 1 up to max limit (10 items)
    for i in range(2, 11):
        with (
            patch.object(db, "add"),
            patch.object(db, "commit"),
            patch.object(db, "refresh"),
        ):
            RecommendedQAService.add_recommended_question(
                tenant_id=tenant_1,
                question=f"Tenant 1 Q{i}?",
                answer=f"Tenant 1 A{i}",
                db=db,
            )

    assert len(RecommendedQAService.get_recommended_questions(tenant_1)) == 10

    # Attempting to add 11th question should raise ValueError
    with pytest.raises(
        ValueError, match="Maximum limit of 10 recommended questions reached"
    ):
        RecommendedQAService.add_recommended_question(
            tenant_id=tenant_1, question="Tenant 1 Q11?", answer="Tenant 1 A11", db=db
        )


def test_query_cache_keys_are_exact_and_history_aware():
    from app.rag.retrivel_data_pipline import RetrievalPipeline

    pipeline = object.__new__(RetrievalPipeline)
    pipeline.tenant_id = "tenant-123"

    same_question = pipeline._build_cache_key("Who is Omar?", "", "user-a", "session-a")
    different_question = pipeline._build_cache_key(
        "Where did Segments start?", "", "user-a", "session-a"
    )
    same_question_different_history = pipeline._build_cache_key(
        "Who is Omar?", "User: Prior question", "user-a", "session-a"
    )
    same_question_different_user = pipeline._build_cache_key(
        "Who is Omar?", "", "user-b", "session-a"
    )
    same_question_different_session = pipeline._build_cache_key(
        "Who is Omar?", "", "user-a", "session-b"
    )

    assert same_question != different_question
    assert same_question != same_question_different_history
    assert same_question != same_question_different_user
    assert same_question != same_question_different_session

    other_tenant = object.__new__(RetrievalPipeline)
    other_tenant.tenant_id = "tenant-456"
    assert same_question != other_tenant._build_cache_key(
        "Who is Omar?", "", "user-a", "session-a"
    )


def test_stream_cache_hit_skips_retrieval_and_generation():
    """The shared streaming helper must exit before touching RAG dependencies."""
    from app.rag.retrivel_data_pipline import RetrievalPipeline

    pipeline = object.__new__(RetrievalPipeline)
    pipeline.tenant_id = "tenant-123"
    pipeline.retriever = MagicMock()
    pipeline.document_chain = MagicMock()
    pipeline._log_run = MagicMock()
    cache_key = pipeline._build_cache_key("What is RAG?", "", "user-a", "session-a")
    pipeline._set_cached(cache_key, {"answer": "Cached answer", "docs_ids": "doc-1"})

    with patch("app.rag.retrivel_data_pipline.cache_hits_total"):
        chunks = list(
            pipeline.ask_stream(
                "What is RAG?",
                user_id="user-a",
                session_id="session-a",
                cache_key=cache_key,
            )
        )

    assert chunks == ["Cached answer"]
    pipeline.retriever.invoke.assert_not_called()
    pipeline.document_chain.stream.assert_not_called()
    pipeline._log_run.assert_called_once()


def test_local_query_cache_entries_expire(monkeypatch):
    import app.rag.retrivel_data_pipline as pipeline_module

    short_lived_cache = TTLCache(maxsize=10, ttl=0.01)
    monkeypatch.setattr(pipeline_module, "_query_cache", short_lived_cache)
    pipeline_module.set_local_query_cache("expiry-key", {"answer": "temporary"})

    assert pipeline_module.get_local_query_cache("expiry-key") == {
        "answer": "temporary"
    }
    time.sleep(0.02)
    assert pipeline_module.get_local_query_cache("expiry-key") is None
