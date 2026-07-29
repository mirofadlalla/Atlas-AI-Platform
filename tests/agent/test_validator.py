import pytest

from app.agent.tools.sql_engine.validator import SQLValidator


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM users",
        "SELECT 1; DROP TABLE users",
        "UPDATE users SET name='x'",
    ],
)
def test_validator_rejects_non_select(sql):
    with pytest.raises(ValueError):
        SQLValidator.validate_and_enforce_tenant(sql, "00000000-0000-0000-0000-000000000001")


def test_validator_injects_parameterized_tenant_predicate():
    sql, params = SQLValidator.validate_and_enforce_tenant(
        "SELECT id FROM orders WHERE status = 'open'",
        "00000000-0000-0000-0000-000000000001",
    )
    assert ":tenant_id" in sql
    assert params["tenant_id"] == "00000000-0000-0000-0000-000000000001"
    assert "00000000" not in sql  # no string interpolation of tenant id


def test_validator_adds_where_when_missing():
    sql, _ = SQLValidator.validate_and_enforce_tenant(
        "SELECT count(*) FROM users",
        "00000000-0000-0000-0000-000000000001",
    )
    assert "tenant_id" in sql.lower()
    assert ":tenant_id" in sql
