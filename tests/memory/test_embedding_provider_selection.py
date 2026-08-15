from unittest.mock import patch

from app.design_pattern.embedded_model import EmbeddedModel


def _configured_model(*, production: bool) -> EmbeddedModel:
    model = EmbeddedModel()
    model._initialized = True
    model.is_production = production
    model.bge_enabled = production
    model.jina_enabled = True
    return model


def test_production_uses_bge_m3_before_jina():
    model = _configured_model(production=True)

    with (
        patch.object(model, "_call_bge_m3", return_value=[[0.1, 0.2]]) as bge,
        patch.object(model, "_call_jina") as jina,
    ):
        assert model._embed_batch(["hello"]) == [[0.1, 0.2]]

    bge.assert_called_once_with(["hello"])
    jina.assert_not_called()


def test_production_falls_back_to_jina_when_bge_m3_is_unavailable():
    model = _configured_model(production=True)

    with (
        patch.object(model, "_call_bge_m3", side_effect=OSError("model unavailable")),
        patch.object(model, "_call_jina", return_value=[[0.3, 0.4]]) as jina,
    ):
        assert model._embed_batch(["hello"], task="retrieval.query") == [[0.3, 0.4]]

    assert model.bge_enabled is False
    jina.assert_called_once_with(["hello"], task="retrieval.query")


def test_development_uses_jina_without_loading_bge_m3():
    model = _configured_model(production=False)

    with (
        patch.object(model, "_call_bge_m3") as bge,
        patch.object(model, "_call_jina", return_value=[[0.5, 0.6]]) as jina,
    ):
        assert model._embed_batch(["hello"]) == [[0.5, 0.6]]

    bge.assert_not_called()
    jina.assert_called_once_with(["hello"], task="retrieval.passage")
