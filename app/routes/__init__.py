"""Routes module.
lazy-loads route modules to avoid circular imports and improve startup time.
"""

from typing import Any

_ROUTE_MAP = {
    "auth_route": "app.routes.auth_route",
    "ingest_rag_route": "app.routes.ingest_rag_route",
    "eval_pipline": "app.routes.eval_pipline",
    "query_route": "app.routes.query_route",
    "agent_route": "app.routes.agent_route",
    "recommended_qa_route": "app.routes.recommended_qa_route",
    "memory_route": "app.routes.memory_route",
}


# This is a lazy-loading mechanism for route modules. When an attribute is accessed on this module, it checks if the attribute name exists in the _ROUTE_MAP. If it does, it dynamically imports the corresponding module and returns it. This helps to avoid circular imports and can improve startup time by only loading route modules when they are actually needed.
def __getattr__(name: str) -> Any:
    if name in _ROUTE_MAP:
        import importlib

        return importlib.import_module(_ROUTE_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_ROUTE_MAP.keys())
