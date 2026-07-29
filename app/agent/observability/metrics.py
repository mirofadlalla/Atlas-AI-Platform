"""Prometheus metrics for agent node execution."""

from prometheus_client import Counter, Histogram

agent_node_executions_total = Counter(
    "atlas_agent_node_executions_total",
    "Agent graph node executions",
    ["node", "status"],
)

agent_node_duration_seconds = Histogram(
    "atlas_agent_node_duration_seconds",
    "Agent node execution duration",
    ["node"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

agent_sql_rows_returned = Histogram(
    "atlas_agent_sql_rows_returned",
    "Rows returned by agent SQL queries",
    buckets=(0, 1, 5, 10, 20, 50, 100, 500, 1000),
)
