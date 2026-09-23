import json
from unittest.mock import MagicMock, patch
import pytest

from app.rag.rerankers.base import Document
from app.rag.rerankers.cross_encoder import (
    CrossEncoderReranker,
    JinaReranker,
    LocalCrossEncoderReranker,
)
from app.rag.rerankers.service import RankingService
from app.rag.rerankers.hybrid import HybridReranker
from app.core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# JinaReranker tests
# ─────────────────────────────────────────────────────────────────────────────


def test_jina_reranker_payload_and_ranking():
    reranker = JinaReranker(
        model_name="jina-reranker-v3.5",
        api_key="test-jina-key-123",
        url="https://api.jina.ai/v1/rerank",
    )

    docs = [
        Document(content="doc 0: sensitive skin care"),
        Document(content="doc 1: makeup trends and neon colors"),
        Document(content="doc 2: organic aloe vera skincare"),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "model": "jina-reranker-v3.5",
        "results": [
            {"index": 2, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.85},
            {"index": 1, "relevance_score": 0.12},
        ],
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        reranked = reranker.rerank(
            query="Organic skincare products for sensitive skin",
            documents=docs,
            top_k=2,
        )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args[0][0] == "https://api.jina.ai/v1/rerank"
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-jina-key-123"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

        payload = json.loads(call_kwargs["data"])
        assert payload["model"] == "jina-reranker-v3.5"
        assert payload["query"] == "Organic skincare products for sensitive skin"
        assert payload["top_n"] == 2
        assert payload["documents"] == [d.content for d in docs]
        assert payload["return_documents"] is False

    assert len(reranked) == 2
    assert reranked[0].content == "doc 2: organic aloe vera skincare"
    assert reranked[0].rerank_score == pytest.approx(0.95)
    assert reranked[1].content == "doc 0: sensitive skin care"
    assert reranked[1].rerank_score == pytest.approx(0.85)


def test_jina_reranker_missing_api_key_degrades_gracefully():
    reranker = JinaReranker(api_key="")
    docs = [Document(content="doc 1"), Document(content="doc 2")]

    with patch("requests.post") as mock_post:
        result = reranker.rerank("query", docs, top_k=1)
        mock_post.assert_not_called()

    # Gracefully returns docs without crashing
    assert len(result) == 1
    assert result[0].content == "doc 1"


def test_jina_reranker_api_failure_degrades_gracefully():
    reranker = JinaReranker(api_key="valid-key")
    docs = [Document(content="doc 1"), Document(content="doc 2")]

    with patch("requests.post", side_effect=Exception("Connection timed out")):
        result = reranker.rerank("query", docs, top_k=2)

    assert len(result) == 2
    assert result[0].content == "doc 1"


def test_jina_reranker_empty_documents():
    reranker = JinaReranker(api_key="valid-key")
    assert reranker.rerank("query", []) == []


# ─────────────────────────────────────────────────────────────────────────────
# LocalCrossEncoderReranker tests
# ─────────────────────────────────────────────────────────────────────────────


def test_local_cross_encoder_rerank():
    with patch("sentence_transformers.CrossEncoder") as mock_ce_cls:
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.2, 0.9]
        mock_ce_cls.return_value = mock_model

        reranker = LocalCrossEncoderReranker(model_name="test-model")
        docs = [Document(content="text A"), Document(content="text B")]

        result = reranker.rerank("test query", docs, top_k=2)

        mock_model.predict.assert_called_once_with(
            [
                ["test query", "text A"],
                ["test query", "text B"],
            ]
        )
        assert len(result) == 2
        assert result[0].content == "text B"
        assert result[0].rerank_score == pytest.approx(0.9)
        assert result[1].content == "text A"
        assert result[1].rerank_score == pytest.approx(0.2)


# ─────────────────────────────────────────────────────────────────────────────
# CrossEncoderReranker provider dispatch tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cross_encoder_dispatches_to_jina_via_param():
    reranker = CrossEncoderReranker(
        provider="jina",
        api_key="test-key",
        model_name="jina-reranker-v3.5",
    )
    assert isinstance(reranker._reranker, JinaReranker)
    assert reranker.provider == "jina"
    assert reranker.model_name == "jina-reranker-v3.5"


def test_cross_encoder_dispatches_to_local_via_param():
    with patch("sentence_transformers.CrossEncoder"):
        reranker = CrossEncoderReranker(
            provider="local",
            model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
        )
        assert isinstance(reranker._reranker, LocalCrossEncoderReranker)
        assert reranker.provider == "local"


def test_cross_encoder_dispatches_to_jina_via_settings():
    with patch.object(settings, "reranker_provider", "jina"):
        reranker = CrossEncoderReranker(api_key="test-key")
        assert isinstance(reranker._reranker, JinaReranker)
        assert reranker.provider == "jina"
        assert reranker.model_name == "jina-reranker-v3.5"


def test_cross_encoder_dispatches_to_jina_via_env_var(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "jina")
    with patch.object(settings, "reranker_provider", "local"):
        # Explicit env var test when settings was local
        pass

    monkeypatch.setenv("RERANKER_PROVIDER", "jina")
    reranker = CrossEncoderReranker(provider=None, api_key="test-key")
    assert reranker.provider == "jina"
    assert isinstance(reranker._reranker, JinaReranker)


def test_cross_encoder_dispatches_to_jina_via_cross_encoder_provider_env(monkeypatch):
    monkeypatch.delenv("RERANKER_PROVIDER", raising=False)
    monkeypatch.setenv("CROSS_ENCODER_PROVIDER", "jina")
    with patch.object(settings, "reranker_provider", ""):
        reranker = CrossEncoderReranker(provider=None, api_key="test-key")
        assert reranker.provider == "jina"
        assert isinstance(reranker._reranker, JinaReranker)


# ─────────────────────────────────────────────────────────────────────────────
# RankingService and Hybrid integration tests
# ─────────────────────────────────────────────────────────────────────────────


def test_ranking_service_with_jina_strategy():
    service = RankingService(strategy="jina")
    assert isinstance(service.reranker, CrossEncoderReranker)
    assert service.reranker.provider == "jina"


def test_ranking_service_rank_with_jina():
    service = RankingService(strategy="jina")
    docs = [{"content": "Doc 1"}, {"content": "Doc 2"}]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"index": 1, "relevance_score": 0.88},
            {"index": 0, "relevance_score": 0.44},
        ],
    }

    with patch.object(service.reranker._reranker, "api_key", "test-key"), patch(
        "requests.post", return_value=mock_response
    ):
        ranked = service.rank("test query", docs, top_k=2)

    assert len(ranked) == 2
    assert ranked[0]["content"] == "Doc 2"
    assert ranked[0]["rerank_score"] == pytest.approx(0.88)
    assert ranked[1]["content"] == "Doc 1"
    assert ranked[1]["rerank_score"] == pytest.approx(0.44)


def test_hybrid_reranker_uses_jina_when_configured():
    with patch.object(settings, "reranker_provider", "jina"):
        hybrid = HybridReranker()
        assert isinstance(hybrid.cross_encoder, CrossEncoderReranker)
        assert hybrid.cross_encoder.provider == "jina"
