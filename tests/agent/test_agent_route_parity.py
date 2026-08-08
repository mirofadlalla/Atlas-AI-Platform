import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.agent.utils.state_helpers import create_initial_state


def test_create_initial_state_accepts_run_id():
    custom_run_id = "test-run-id-12345"
    state = create_initial_state("test question", "tenant-1", run_id=custom_run_id)
    assert state["run_id"] == custom_run_id


def test_ask_agent_passes_run_id_and_emits_degraded_fields():
    from app.routes.agent_route import router
    from fastapi import FastAPI
    from app.services.auth_services.auth_service import get_current_user
    from app.core.db import get_db

    test_app = FastAPI()
    test_app.include_router(router)

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
        patch(
            "app.routes.agent_route.agent_app.astream_events",
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

        # Parse SSE events from output
        lines = [
            line for line in events_text.split("\n\n") if line.startswith("data: ")
        ]
        parsed_events = [json.loads(line.replace("data: ", "")) for line in lines]

        complete_event = next(e for e in parsed_events if e.get("type") == "complete")
        assert complete_event["degraded"] is True
        assert complete_event["degraded_reason"] == "Test degradation reason"

        done_event = next(e for e in parsed_events if e.get("type") == "done")
        assert done_event["degraded"] is True
        assert done_event["degraded_reason"] == "Test degradation reason"


def test_ask_agent_returns_cached_run():
    from app.routes.agent_route import router
    from fastapi import FastAPI
    from app.services.auth_services.auth_service import get_current_user
    from app.core.db import get_db

    test_app = FastAPI()
    test_app.include_router(router)

    mock_user = MagicMock()
    mock_user.tenant_id = "tenant-123"

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_db] = lambda: MagicMock()

    client = TestClient(test_app)

    cached_data = {
        "final_answer": "Cached answer text",
        "degraded": True,
        "degraded_reason": "Cached degraded reason",
    }

    with patch(
        "app.routes.agent_route.get_cached_run_result", return_value=cached_data
    ):
        response = client.post(
            "/agent/ask-agent",
            json={"question": "What is x?", "run_id": "cached-run-id"},
        )

        assert response.status_code == 200
        events_text = response.text
        lines = [
            line for line in events_text.split("\n\n") if line.startswith("data: ")
        ]
        parsed_events = [json.loads(line.replace("data: ", "")) for line in lines]

        complete_event = next(e for e in parsed_events if e.get("type") == "complete")
        assert complete_event["final_answer"] == "Cached answer text"
        assert complete_event["degraded"] is True
        assert complete_event["degraded_reason"] == "Cached degraded reason"
