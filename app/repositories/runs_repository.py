"""
Repository for Runs model database operations.

Implements repository pattern to separate data access logic from business logic.
"""

from sqlalchemy.orm import Session
from app.models.runs import Runs
from typing import List, Optional


class RunsRepository:
    """Repository for managing Runs database operations."""

    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.

        Args:
            db: SQLAlchemy Session for database operations
        """
        self.db = db

    def create(
        self,
        tenant_id: str,
        query: str,
        answer: str,
        latency: float,
        cache_hit: bool = False,
        retrieved_docs_ids: str = "",
    ) -> Runs:
        """
        Create a new run record.

        Args:
            tenant_id: Tenant identifier
            query: The user query
            answer: The generated answer
            latency: Response latency in seconds
            cache_hit: Whether the answer was cached
            retrieved_docs_ids: Comma-separated document IDs used for retrieval

        Returns:
            Created Runs object
        """
        run = Runs(
            tenant_id=tenant_id,
            query=query,
            answer=answer,
            latency=latency,
            cache_hit=cache_hit,
            retrieved_docs_ids=retrieved_docs_ids,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_by_id(self, run_id: str) -> Optional[Runs]:
        """
        Retrieve a run by ID.

        Args:
            run_id: Run identifier

        Returns:
            Runs object or None if not found
        """
        return self.db.query(Runs).filter(Runs.run_id == run_id).first()

    def get_by_tenant(
        self, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> List[Runs]:
        """
        Retrieve runs for a specific tenant.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of Runs objects
        """
        return (
            self.db.query(Runs)
            .filter(Runs.tenant_id == tenant_id)
            .order_by(Runs.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_stats_for_tenant(self, tenant_id: str):
        """
        Get aggregated statistics for a tenant's runs.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with statistics
        """
        from sqlalchemy import func

        stats = (
            self.db.query(
                func.count(Runs.run_id).label("total_runs"),
                func.avg(Runs.latency).label("avg_latency"),
                func.sum(Runs.cache_hit).label("cache_hits"),
            )
            .filter(Runs.tenant_id == tenant_id)
            .first()
        )

        return {
            "total_runs": stats.total_runs or 0,
            "avg_latency": float(stats.avg_latency) if stats.avg_latency else 0,
            "cache_hits": stats.cache_hits or 0,
        }

    def update(self, run_id: str, **kwargs) -> Optional[Runs]:
        """
        Update a run record.

        Args:
            run_id: Run identifier
            **kwargs: Fields to update

        Returns:
            Updated Runs object or None if not found
        """
        run = self.get_by_id(run_id)
        if run:
            for key, value in kwargs.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            self.db.commit()
            self.db.refresh(run)
        return run

    def delete(self, run_id: str) -> bool:
        """
        Delete a run record.

        Args:
            run_id: Run identifier

        Returns:
            True if deleted, False if not found
        """
        run = self.get_by_id(run_id)
        if run:
            self.db.delete(run)
            self.db.commit()
            return True
        return False
