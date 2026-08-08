from unittest.mock import MagicMock, patch
import pytest
from app.services.recommended_qa_service import RecommendedQAService, MAX_RECOMMENDED_PER_TENANT
from app.models.recommended_qa import RecommendedQA

def test_recommended_qa_tenant_isolation_and_limit():
    db = MagicMock()
    tenant_1 = "tenant-uuid-1"
    tenant_2 = "tenant-uuid-2"

    # Reset in-memory cache
    RecommendedQAService._tenant_cache = {}

    # Mock DB queries
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    
    # Add question for tenant 1
    with patch.object(db, "add"), patch.object(db, "commit"), patch.object(db, "refresh"):
        item1 = RecommendedQAService.add_recommended_question(
            tenant_id=tenant_1,
            question="Tenant 1 Q1?",
            answer="Tenant 1 A1",
            db=db
        )
        assert item1["question"] == "Tenant 1 Q1?"

    # Check tenant 1 and tenant 2 cache isolation
    t1_questions = RecommendedQAService.get_recommended_questions(tenant_1)
    t2_questions = RecommendedQAService.get_recommended_questions(tenant_2)

    assert len(t1_questions) == 1
    assert len(t2_questions) == 0

    # Fill tenant 1 up to max limit (10 items)
    for i in range(2, 11):
        with patch.object(db, "add"), patch.object(db, "commit"), patch.object(db, "refresh"):
            RecommendedQAService.add_recommended_question(
                tenant_id=tenant_1,
                question=f"Tenant 1 Q{i}?",
                answer=f"Tenant 1 A{i}",
                db=db
            )

    assert len(RecommendedQAService.get_recommended_questions(tenant_1)) == 10

    # Attempting to add 11th question should raise ValueError
    with pytest.raises(ValueError, match="Maximum limit of 10 recommended questions reached"):
        RecommendedQAService.add_recommended_question(
            tenant_id=tenant_1,
            question="Tenant 1 Q11?",
            answer="Tenant 1 A11",
            db=db
        )

def test_query_cache_keys_are_exact_and_history_aware():
    from app.rag.retrivel_data_pipline import RetrievalPipeline

    pipeline = object.__new__(RetrievalPipeline)
    pipeline.tenant_id = "tenant-123"

    same_question = pipeline._build_cache_key("Who is Omar?", "")
    different_question = pipeline._build_cache_key("Where did Segments start?", "")
    same_question_different_history = pipeline._build_cache_key("Who is Omar?", "User: Prior question")

    assert same_question != different_question
    assert same_question != same_question_different_history
