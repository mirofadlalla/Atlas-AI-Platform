"""AST-based SQL validation and tenant isolation."""

from __future__ import annotations

import logging
import re
from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy import text

from app.agent.core.config import agent_settings
from app.agent.utils.circuit_breaker import db_circuit_breaker
from app.agent.utils.db_session import agent_db_session

logger = logging.getLogger(__name__)

_FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Merge,
    exp.Command,
)


class SQLValidator:
    @staticmethod
    def validate_and_enforce_tenant(
        sql_query: str,
        tenant_id: str,
        allowed_tables: set[str] | None = None,
        allowed_columns: set[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Parse SQL with sqlglot, enforce SELECT-only + allow-lists, inject
        parameterized tenant predicate. Returns (sql, bind_params).
        """
        cleaned = sql_query.rstrip(";").strip()
        if not cleaned:
            raise ValueError("Empty SQL query")

        if ";" in cleaned:
            raise ValueError("Security violation: multiple SQL statements are not allowed")

        try:
            parsed = sqlglot.parse_one(cleaned, read="postgres")
        except sqlglot.errors.ParseError as exc:
            raise ValueError(f"Invalid SQL: {exc}") from exc

        if not isinstance(parsed, (exp.Select, exp.Union)):
            raise ValueError("Security violation: only SELECT queries are allowed")

        for node in parsed.walk():
            if isinstance(node, _FORBIDDEN_EXPRESSIONS):
                raise ValueError("Security violation: only SELECT queries are allowed")

        tables = {t.name for t in parsed.find_all(exp.Table) if t.name}
        allow_tables = allowed_tables if allowed_tables is not None else agent_settings.allowed_tables
        if allow_tables is not None:
            disallowed = tables - allow_tables
            if disallowed:
                raise ValueError(f"Security violation: table(s) not allowed: {', '.join(sorted(disallowed))}")

        if allowed_columns is not None or agent_settings.allowed_columns is not None:
            allow_cols = allowed_columns if allowed_columns is not None else agent_settings.allowed_columns
            if allow_cols is not None:
                for col in parsed.find_all(exp.Column):
                    if col.name and col.name not in allow_cols and col.name != "tenant_id":
                        raise ValueError(f"Security violation: column not allowed: {col.name}")

        def _inject_tenant(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Select):
                tenant_cond = exp.EQ(
                    this=exp.to_identifier("tenant_id"),
                    expression=exp.Placeholder(this="tenant_id"), # Parameterized Query
                )
                existing = node.args.get("where")
                if existing:
                    node.set("where", exp.Where(this=exp.and_(existing.this, tenant_cond)))
                else:
                    node.set("where", exp.Where(this=tenant_cond))
            return node

        secured = parsed.transform(_inject_tenant)
        sql = secured.sql(dialect="postgres")
        params = {"tenant_id": tenant_id}
        logger.debug("Tenant-enforced SQL prepared")
        return sql, params

    @staticmethod
    def _set_statement_timeout(db) -> None:
        db.execute(
            text(
                f"SET LOCAL statement_timeout = "
                f"'{int(agent_settings.sql_query_timeout_seconds * 1000)}'"
            )
        )

    @staticmethod
    def get_query_cost(sql: str, params: dict[str, Any] | None = None) -> float:
        """Estimate query cost via EXPLAIN. Fail-closed on errors."""
        try:
            cost, _ = SQLValidator.explain_and_execute(sql, params or {}, execute=False)
            return cost
        except Exception as exc:
            logger.warning("Could not estimate SQL cost, failing closed: %s", exc)
            return agent_settings.sql_cost_unknown_default

    @staticmethod
    def explain_and_execute(
        sql: str,
        params: dict[str, Any],
        *,
        execute: bool = True,
    ) -> tuple[float, list[Any]]:
        """
        Single DB session for EXPLAIN (+ optional execute).
        Returns (estimated_cost, rows). Rows empty when execute=False.
        """

        def _run() -> tuple[float, list[Any]]:
            with agent_db_session() as db:
                SQLValidator._set_statement_timeout(db)
                plan = db.execute(text(f"EXPLAIN {sql}"), params).fetchall()
                match = re.search(r"cost=[\d.]+\.\.([\d.]+)", str(plan[0]))
                cost = (
                    float(match.group(1))
                    if match
                    else agent_settings.sql_cost_unknown_default
                )
                if not execute:
                    return cost, []
                rows = list(db.execute(text(sql), params).fetchall())
                return cost, rows

        return db_circuit_breaker.call(_run)

    @staticmethod
    def execute_query(sql: str, params: dict[str, Any]) -> list[Any]:
        _, rows = SQLValidator.explain_and_execute(sql, params, execute=True)
        return rows
