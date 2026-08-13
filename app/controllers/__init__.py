"""
Controllers package.

Controller classes are listed in __all__ for discoverability, but are NOT
imported eagerly at package level. Each controller should be imported
directly from its module to avoid heavy transitive imports (e.g. MLflow,
torch) being pulled in at test/startup time unnecessarily.

Usage:
    from app.controllers.query_controller import QueryController
    from app.controllers.auth_controller import AuthController
"""

__all__ = [
    "AuthController",
    "IngestController",
    "QueryController",
    "AgentController",
    "EvalController",
    "MemoryController",
    "RecommendedQAController",
    "InternalMetricsController",
]
