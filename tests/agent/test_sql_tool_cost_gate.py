from unittest.mock import patch
from app.agent.tools.sql_tool import SQLTool
from app.agent.core.config import agent_settings


def test_sql_tool_pre_execute_cost_gate_blocks_high_cost():
    sql_tool = SQLTool()
    state = {
        "question": "select all users",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
    }

    with (
        patch(
            "app.agent.tools.sql_tool.generate_sql", return_value="SELECT * FROM users"
        ),
        patch(
            "app.agent.tools.sql_tool.SQLValidator.validate_and_enforce_tenant",
            return_value=(
                "SELECT * FROM users WHERE tenant_id = :tenant_id",
                {"tenant_id": "00000000-0000-0000-0000-000000000001"},
            ),
        ),
        patch(
            "app.agent.tools.sql_tool.SQLValidator.explain_and_execute"
        ) as mock_explain_exec,
    ):
        # Explain call returns high cost
        mock_explain_exec.return_value = (
            agent_settings.sql_max_allowed_cost + 100.0,
            [],
        )

        result = sql_tool.run(state)

        # Check that explain_and_execute was called once with execute=False
        assert mock_explain_exec.call_count == 1
        assert mock_explain_exec.call_args_list[0].kwargs.get("execute") is False
        assert "too expensive" in result.observation
        assert result.state_updates["sql_has_results"] is False


def test_sql_tool_pre_execute_cost_gate_allows_low_cost():
    sql_tool = SQLTool()
    state = {
        "question": "select active users",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
    }

    with (
        patch(
            "app.agent.tools.sql_tool.generate_sql", return_value="SELECT * FROM users"
        ),
        patch(
            "app.agent.tools.sql_tool.SQLValidator.validate_and_enforce_tenant",
            return_value=(
                "SELECT * FROM users WHERE tenant_id = :tenant_id",
                {"tenant_id": "00000000-0000-0000-0000-000000000001"},
            ),
        ),
        patch(
            "app.agent.tools.sql_tool.SQLValidator.explain_and_execute"
        ) as mock_explain_exec,
    ):
        # First call (execute=False) returns cost 10.0, second call (execute=True) returns cost 10.0, rows
        mock_explain_exec.side_effect = [
            (10.0, []),
            (10.0, [{"id": 1, "name": "Alice"}]),
        ]

        result = sql_tool.run(state)

        # Check that explain_and_execute was called twice: first with execute=False, then with execute=True
        assert mock_explain_exec.call_count == 2
        assert mock_explain_exec.call_args_list[0].kwargs.get("execute") is False
        assert mock_explain_exec.call_args_list[1].kwargs.get("execute") is True
        assert result.has_data is True
