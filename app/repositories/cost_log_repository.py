"""
Repository for CostLog model database operations.

Implements repository pattern to separate data access logic from business logic.
"""

from sqlalchemy.orm import Session
from app.models.costLog import CostLog
from typing import Optional
from decimal import Decimal


class CostLogRepository:
    """Repository for managing CostLog database operations and cost tracking."""

    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.

        Args:
            db: SQLAlchemy Session for database operations
        """
        self.db = db

    def create(
        self,
        run_id: str,
        input_tokens: int,
        output_tokens: int,
        model_name: str,
        cost_usd: float,
    ) -> CostLog:
        """
        Create a new cost log record.

        Args:
            run_id: Associated run identifier
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            model_name: Name of the model used
            cost_usd: Cost in USD

        Returns:
            Created CostLog object
        """
        cost_log = CostLog(
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            cost_usd=Decimal(str(cost_usd)),
        )
        self.db.add(cost_log)
        self.db.commit()
        self.db.refresh(cost_log)
        return cost_log

    def get_by_id(self, log_id: str) -> Optional[CostLog]:
        """
        Retrieve a cost log by ID.

        Args:
            log_id: Cost log identifier

        Returns:
            CostLog object or None if not found
        """
        return self.db.query(CostLog).filter(CostLog.log_id == log_id).first()

    def get_by_run_id(self, run_id: str) -> Optional[CostLog]:
        """
        Retrieve cost log by run ID.

        Args:
            run_id: Run identifier

        Returns:
            CostLog object or None if not found
        """
        return self.db.query(CostLog).filter(CostLog.run_id == run_id).first()

    def get_cost_summary_for_tenant(self, tenant_id: str):
        """
        Get cost summary for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with cost statistics
        """
        from sqlalchemy import func
        from app.models.runs import Runs

        summary = (
            self.db.query(
                func.sum(CostLog.cost_usd).label("total_cost"),
                func.avg(CostLog.cost_usd).label("avg_cost"),
                func.count(CostLog.log_id).label("total_requests"),
                func.sum(CostLog.input_tokens).label("total_input_tokens"),
                func.sum(CostLog.output_tokens).label("total_output_tokens"),
            )
            .join(Runs)
            .filter(Runs.tenant_id == tenant_id)
            .first()
        )

        return {
            "total_cost_usd": float(summary.total_cost) if summary.total_cost else 0.0,
            "avg_cost_usd": float(summary.avg_cost) if summary.avg_cost else 0.0,
            "total_requests": summary.total_requests or 0,
            "total_input_tokens": summary.total_input_tokens or 0,
            "total_output_tokens": summary.total_output_tokens or 0,
        }

    def get_cost_by_model(self, tenant_id: str):
        """
        Get cost breakdown by model for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with cost by model
        """
        from sqlalchemy import func
        from app.models.runs import Runs

        results = (
            self.db.query(
                CostLog.model_name,
                func.count(CostLog.log_id).label("count"),
                func.sum(CostLog.cost_usd).label("total"),
            )
            .join(Runs)
            .filter(Runs.tenant_id == tenant_id)
            .group_by(CostLog.model_name)
            .all()
        )

        return {
            row.model_name: {"count": row.count, "total_cost_usd": float(row.total)}
            for row in results
        }

    def update(self, log_id: str, **kwargs) -> Optional[CostLog]:
        """
        Update a cost log record.

        Args:
            log_id: Cost log identifier
            **kwargs: Fields to update

        Returns:
            Updated CostLog object or None if not found
        """
        cost_log = self.get_by_id(log_id)
        if cost_log:
            for key, value in kwargs.items():
                if hasattr(cost_log, key):
                    setattr(cost_log, key, value)
            self.db.commit()
            self.db.refresh(cost_log)
        return cost_log

    def delete(self, log_id: str) -> bool:
        """
        Delete a cost log record.

        Args:
            log_id: Cost log identifier

        Returns:
            True if deleted, False if not found
        """
        cost_log = self.get_by_id(log_id)
        if cost_log:
            self.db.delete(cost_log)
            self.db.commit()
            return True
        return False
