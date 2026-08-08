from unittest.mock import patch

from app.design_pattern.embedded_model import EmbeddedModel


def test_exact_query_embedding_is_reused():
    """Semantic recall and document retrieval should share one dense vector."""
    model = EmbeddedModel()
    original_initialized = model._initialized
    model._initialized = True
    with model._query_embedding_cache_lock:
        model._query_embedding_cache.clear()

    try:
        with patch.object(
            model, "_embed_batch", return_value=[[0.1, 0.2]]
        ) as embed_batch:
            first = model.embed_query("What is RAG?")
            second = model.embed_query("What is RAG?")

        assert first == [0.1, 0.2]
        assert second == [0.1, 0.2]
        assert embed_batch.call_count == 1
    finally:
        model._initialized = original_initialized
        with model._query_embedding_cache_lock:
            model._query_embedding_cache.clear()
