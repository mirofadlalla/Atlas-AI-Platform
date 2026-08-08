from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.agent.utils.state_helpers import create_initial_state


def test_create_initial_state_accepts_run_id():
    custom_run_id = "test-run-id-12345"
    state = create_initial_state("test question", "tenant-1", run_id=custom_run_id)
    assert state["run_id"] == custom_run_id


def test_ask_agent_passes_run_id_and_emits_degraded_fields():
    import app.routes.agent_route as agent_route
    from fastapi import FastAPI
    from app.services.auth_services.auth_service import get_current_user
    from app.core.db import get_db

    test_app = FastAPI()
    test_app.include_router(agent_route.router)

    mock_user = MagicMock()
    mock_user.tenant_id = "tenant-123"

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_db] = lambda: MagicMock()

    client = TestClient(test_app)

    async def mock_astream_events(inputs, version):
        assert inputs.get("run_id") == "my-custom-run-id"
        # Yield finish event with degraded info
        yield {
            "event": "on_chain_end",
            "name": "finish",
            "data": {
                "output": {
                    "final_answer": "Test answer",
                    "degraded": True,
                    "degraded_reason": "Test degradation reason",
                    "step_count": 2,
                }
            },
        }

    with (
        patch.object(
            agent_route.agent_app.__class__,
            "astream_events",
            side_effect=mock_astream_events,
        ),
        patch("app.routes.agent_route.trigger_agent_logging"),
    ):
        response = client.post(
            "/agent/ask-agent",
            json={"question": "What is x?", "run_id": "my-custom-run-id"},
        )

        assert response.status_code == 200
        events_text = response.text
        assert "Test answer" in events_text
        assert '"degraded": true' in events_text
        assert '"degraded_reason": "Test degradation reason"' in events_text


def test_ask_agent_returns_cached_run():
    import app.routes.agent_route as agent_route
    from fastapi import FastAPI
    from app.services.auth_services.auth_service import get_current_user
    from app.core.db import get_db

    test_app = FastAPI()
    test_app.include_router(agent_route.router)

    mock_user = MagicMock()
    mock_user.tenant_id = "tenant-123"

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_db] = lambda: MagicMock()

    client = TestClient(test_app)

    cached_data = {
        "final_answer": "Cached answer",
        "degraded": False,
        "degraded_reason": None,
    }

    with patch(
        "app.routes.agent_route.get_cached_run_result", return_value=cached_data
    ):
        response = client.post(
            "/agent/ask-agent",
            json={"question": "What is x?", "run_id": "cached-run-123"},
        )

        assert response.status_code == 200
        events_text = response.text
        assert "Cached answer" in events_text
        assert '"type": "complete"' in events_text
        assert '"type": "done"' in events_text
