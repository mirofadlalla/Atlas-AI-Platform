from unittest.mock import patch
import pytest

from app.design_pattern.embedded_model import EmbeddedModel


def _configured_model(*, production: bool = True) -> EmbeddedModel:
    model = EmbeddedModel()
    model._initialized = True
    model.is_production = production
    model.bge_enabled = True
    model.jina_enabled = True
    return model


def test_uses_jina_as_primary_provider():
    model = _configured_model()

    with (
        patch.object(model, "_call_jina", return_value=[[0.1, 0.2]]) as jina,
        patch.object(model, "_call_bge_m3") as bge,
    ):
        assert model._embed_batch(["hello"]) == [[0.1, 0.2]]

    jina.assert_called_once_with(["hello"], task="retrieval.passage")
    bge.assert_not_called()


def test_falls_back_to_bge_m3_when_jina_is_unavailable():
    model = _configured_model()

    with (
        patch.object(model, "_call_jina", side_effect=Exception("Jina unavailable")),
        patch.object(model, "_call_bge_m3", return_value=[[0.3, 0.4]]) as bge,
    ):
        assert model._embed_batch(["hello"]) == [[0.3, 0.4]]

    assert model.jina_enabled is False
    bge.assert_called_once_with(["hello"])


def test_raises_when_no_provider_available():
    model = _configured_model()
    model.jina_enabled = False
    model.bge_enabled = False

    with pytest.raises(RuntimeError, match="No embedding provider is available"):
        model._embed_batch(["hello"])
