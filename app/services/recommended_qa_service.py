import logging
import threading
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.recommended_qa import RecommendedQA

logger = logging.getLogger(__name__)

MAX_RECOMMENDED_PER_TENANT = 10


class RecommendedQAService:
    """
    Tenant-level in-memory cache for recommended questions and answers.
    Max 10 Q&A pairs per tenant.
    Loaded into memory on server startup and updated via admin API.
    """

    _tenant_cache: Dict[str, List[Dict[str, Any]]] = {}
    _lock = threading.Lock()

    @classmethod
    def load_all_recommended_questions(cls, db: Session) -> None:
        """Load recommended Q&A pairs for all tenants into in-memory cache."""
        try:
            # Ensure table exists
            engine = db.get_bind()
            Base.metadata.create_all(bind=engine, tables=[RecommendedQA.__table__])

            records = (
                db.query(RecommendedQA).order_by(RecommendedQA.created_at.asc()).all()
            )

            new_cache: Dict[str, List[Dict[str, Any]]] = {}
            for rec in records:
                t_id = str(rec.tenant_id)
                if t_id not in new_cache:
                    new_cache[t_id] = []
                if len(new_cache[t_id]) < MAX_RECOMMENDED_PER_TENANT:
                    new_cache[t_id].append(
                        {
                            "id": str(rec.id),
                            "question": rec.question,
                            "answer": rec.answer,
                            "created_at": (
                                rec.created_at.isoformat() if rec.created_at else None
                            ),
                        }
                    )

            with cls._lock:
                cls._tenant_cache = new_cache

            logger.info(
                f"✅ Successfully loaded recommended Q&A in-memory cache for {len(new_cache)} tenants"
            )
        except Exception as exc:
            logger.error(
                f"❌ Error loading recommended Q&A into in-memory cache: {exc}"
            )

    @classmethod
    def _load_tenant(cls, tenant_id: str, db: Session) -> List[Dict[str, Any]]:
        """Load single tenant's recommended Q&A pairs into in-memory cache."""
        try:
            engine = db.get_bind()
            Base.metadata.create_all(bind=engine, tables=[RecommendedQA.__table__])

            records = (
                db.query(RecommendedQA)
                .filter(RecommendedQA.tenant_id == tenant_id)
                .order_by(RecommendedQA.created_at.asc())
                .limit(MAX_RECOMMENDED_PER_TENANT)
                .all()
            )
            items = [
                {
                    "id": str(rec.id),
                    "question": rec.question,
                    "answer": rec.answer,
                    "created_at": (
                        rec.created_at.isoformat() if rec.created_at else None
                    ),
                }
                for rec in records
            ]
            with cls._lock:
                cls._tenant_cache[tenant_id] = items
            return items
        except Exception as exc:
            logger.error(f"Error loading tenant {tenant_id} recommended Q&A: {exc}")
            return []

    @classmethod
    def get_recommended_questions(
        cls, tenant_id: str, db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve tenant's recommended Q&A pairs from in-memory cache."""
        t_id = str(tenant_id)
        with cls._lock:
            if t_id in cls._tenant_cache:
                return list(cls._tenant_cache[t_id])

        if db is not None:
            return cls._load_tenant(t_id, db)

        return []

    @classmethod
    def add_recommended_question(
        cls, tenant_id: str, question: str, answer: str, db: Session
    ) -> Dict[str, Any]:
        """Add recommended Q&A pair for a tenant (max 10 allowed)."""
        t_id = str(tenant_id)
        current_items = cls.get_recommended_questions(t_id, db)

        if len(current_items) >= MAX_RECOMMENDED_PER_TENANT:
            raise ValueError(
                f"Maximum limit of {MAX_RECOMMENDED_PER_TENANT} recommended questions reached for tenant."
            )

        new_qa = RecommendedQA(
            tenant_id=t_id, question=question.strip(), answer=answer.strip()
        )
        db.add(new_qa)
        db.commit()
        db.refresh(new_qa)

        item = {
            "id": str(new_qa.id),
            "question": new_qa.question,
            "answer": new_qa.answer,
            "created_at": new_qa.created_at.isoformat() if new_qa.created_at else None,
        }

        with cls._lock:
            if t_id not in cls._tenant_cache:
                cls._tenant_cache[t_id] = []
            cls._tenant_cache[t_id].append(item)

        logger.info(
            f"Added recommended Q&A '{question[:30]}...' to tenant {t_id} in-memory cache"
        )
        return item

    @classmethod
    def delete_recommended_question(
        cls, tenant_id: str, qa_id: str, db: Session
    ) -> bool:
        """Delete recommended Q&A pair for a tenant."""
        t_id = str(tenant_id)
        record = (
            db.query(RecommendedQA)
            .filter(RecommendedQA.id == qa_id, RecommendedQA.tenant_id == t_id)
            .first()
        )

        if not record:
            return False

        db.delete(record)
        db.commit()

        with cls._lock:
            if t_id in cls._tenant_cache:
                cls._tenant_cache[t_id] = [
                    item for item in cls._tenant_cache[t_id] if item["id"] != str(qa_id)
                ]

        logger.info(
            f"Deleted recommended Q&A {qa_id} for tenant {t_id} from in-memory cache"
        )
        return True
