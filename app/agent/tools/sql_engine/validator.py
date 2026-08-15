"""AST-based SQL validation and tenant isolation.

                        LLM generates SQL
                            │
                            ▼
                        validate_and_enforce_tenant()
                            │
                            ├── Empty?
                            ├── Multiple statements?
                            ├── SELECT only?
                            ├── Forbidden operations?
                            ├── Allowed tables?
                            ├── Allowed columns?
                            └── Inject tenant_id
                            │
                            ▼
                        secured SQL + params
                            │
                            ▼
                        EXPLAIN query
                            │
                            ├── Cost acceptable?
                            │
                            ▼
                        Execute query
                            │
                            ▼
                        Rows

Why sql Glot
sqlglot يحول SQL إلى AST — Abstract Syntax Tree.
SELECT name FROM users WHERE age > 20
Select
├── Column(name)
├── From
│   └── Table(users)
└── Where
    └── GT
        ├── Column(age)
        └── Literal(20)
"""

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
    def _add_tenant_where(select_node: exp.Select) -> None:
        """
        Inject ``tenant_id = :tenant_id`` into a SELECT node's WHERE clause in-place.

        If a WHERE clause already exists it is ANDed with the new predicate so
        existing filters are preserved.
        """
        tenant_cond = exp.EQ(
            this=exp.to_identifier("tenant_id"),
            expression=exp.Placeholder(this="tenant_id"),  # parameterized — safe
        )
        existing = select_node.args.get("where")
        if existing:
            select_node.set(
                "where", exp.Where(this=exp.and_(existing.this, tenant_cond))
            )
        else:
            select_node.set("where", exp.Where(this=tenant_cond))

    @staticmethod
    def _inject_tenant_top_level(node: exp.Expression) -> None:
        """
        Inject the tenant predicate only into the top-level SELECT branch(es).

        - **Simple SELECT** → inject directly.
        - **UNION / UNION ALL / INTERSECT / EXCEPT** → recurse into each
          branch (left / right), which are themselves either SELECT or nested
          set-operation nodes.
        - **Subqueries inside FROM** are intentionally skipped.  Those inner
          tables are protected by the ``allowed_tables`` allow-list and the
          outer branch's injected predicate.  Injecting into a derived-table
          SELECT would add ``WHERE tenant_id = :tenant_id`` to a result-set
          that may not expose a ``tenant_id`` column, causing a runtime error.
        """
        if isinstance(node, exp.Select):
            SQLValidator._add_tenant_where(node)
        elif isinstance(node, exp.Union):
            # Recurse into left and right branches only — not into their
            # subquery children.
            left = node.args.get("this")
            right = node.args.get("expression")
            if left is not None:
                SQLValidator._inject_tenant_top_level(left)
            if right is not None:
                SQLValidator._inject_tenant_top_level(right)

    @staticmethod
    def validate_and_enforce_tenant(
        sql_query: str,
        tenant_id: str,
        allowed_tables: set[str] | None = None,
        allowed_columns: set[str] | None = None,
        inject_tenant_filter: bool = True,
        dialect: str = "postgres",
    ) -> tuple[str, dict[str, Any]]:
        """
        Parse SQL with sqlglot, enforce SELECT-only + allow-lists, inject
        parameterized tenant predicate. Returns (sql, bind_params).
        """
        cleaned = sql_query.rstrip(";").strip()
        if not cleaned:
            raise ValueError("Empty SQL query")

        if ";" in cleaned:
            raise ValueError(
                "Security violation: multiple SQL statements are not allowed"
            )

        try:
            parsed = sqlglot.parse_one(cleaned, read=dialect)
        except sqlglot.errors.ParseError as exc:
            raise ValueError(f"Invalid SQL: {exc}") from exc

        if not isinstance(
            parsed, (exp.Select, exp.Union)
        ):  # root must be select or union
            raise ValueError("Security violation: only SELECT queries are allowed")

        for node in (
            parsed.walk()
        ):  # امشي داخل الشجرة كلها، ولو لقيت أي operation خطيرة ارفضها.
            if isinstance(node, _FORBIDDEN_EXPRESSIONS):
                raise ValueError("Security violation: only SELECT queries are allowed")

        tables = {t.name for t in parsed.find_all(exp.Table) if t.name}
        allow_tables = (
            allowed_tables
            if allowed_tables is not None
            else agent_settings.allowed_tables
        )
        if allow_tables is not None:
            disallowed = tables - allow_tables
            if disallowed:
                raise ValueError(
                    f"Security violation: table(s) not allowed: {', '.join(sorted(disallowed))}"
                )

        if allowed_columns is not None or agent_settings.allowed_columns is not None:
            allow_cols = (
                allowed_columns
                if allowed_columns is not None
                else agent_settings.allowed_columns
            )
            if allow_cols is not None:
                for col in parsed.find_all(exp.Column):
                    if (
                        col.name
                        and col.name not in allow_cols
                        and col.name != "tenant_id"
                    ):
                        raise ValueError(
                            f"Security violation: column not allowed: {col.name}"
                        )

        # Inject tenant predicate only into the top-level SELECT branch(es).
        # Using _inject_tenant_top_level instead of sqlglot's transform() avoids
        # recursing into derived-table subqueries — which would add a WHERE on a
        # tenant_id column that the subquery result-set may not expose, causing a
        # runtime SQL error.  Both branches of any UNION/UNION ALL are covered.
        if inject_tenant_filter:
            SQLValidator._inject_tenant_top_level(parsed)
        if not parsed.args.get("limit"):
            parsed.set(
                "limit",
                exp.Limit(expression=exp.Literal.number(agent_settings.sql_max_rows)),
            )
        sql = parsed.sql(dialect=dialect)
        params = {"tenant_id": tenant_id} if inject_tenant_filter else {}
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
