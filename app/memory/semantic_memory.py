"""Tenant- and user-isolated semantic long-term memory in Qdrant."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import uuid4

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.design_pattern.embedded_model import EmbeddedModel

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = {"fact", "preference", "tool_hint"}


class SemanticMemory:
    """Stores durable, relevant memories with strict tenant and user filters."""

    def __init__(
        self, client=None, embedding_model=None, collection_name: str | None = None
    ) -> None:
        self.client = client or QdrantClient(url=settings.qdrant_url)
        self.embedding_model = embedding_model or EmbeddedModel()
        self.collection_name = collection_name or settings.semantic_memory_collection

    def _ensure_collection(self, vector_size: int) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=vector_size, distance=models.Distance.COSINE
                    )
                },
            )
        for field_name, schema in {
            "tenant_id": models.PayloadSchemaType.KEYWORD,
            "user_id": models.PayloadSchemaType.KEYWORD,
            "memory_type": models.PayloadSchemaType.KEYWORD,
            "importance": models.PayloadSchemaType.FLOAT,
        }.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception as exc:
                logger.debug("Semantic memory index was not created: %s", exc)

    def store(
        self,
        fact: str,
        user_id: str | int,
        tenant_id: str | int,
        memory_type: str = "fact",
        importance: float = 0.5,
        dedup_similarity_threshold: float = 0.88,
    ) -> str | None:
        """Embed and persist a fact, preference, or reusable tool hint with deduplication."""
        fact = fact.strip()
        if not fact:
            return None
        if memory_type not in _ALLOWED_TYPES:
            raise ValueError(f"Unsupported semantic memory type: {memory_type}")
        vector = self.embedding_model.embed_documents([fact])[0]
        self._ensure_collection(len(vector))

        # Perform deduplication check against existing user memories
        try:
            existing = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                using="dense",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=str(tenant_id)),
                        ),
                        models.FieldCondition(
                            key="user_id", match=models.MatchValue(value=str(user_id))
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
            )
            points = getattr(existing, "points", existing)
            if points:
                top_match = points[0]
                score = float(getattr(top_match, "score", 0.0))
                existing_content = (
                    (top_match.payload or {}).get("content", "").strip().lower()
                )
                if (
                    score >= dedup_similarity_threshold
                    or existing_content == fact.lower()
                ):
                    logger.info(
                        "Deduplicated semantic memory tenant=%s user=%s match_id=%s score=%.2f -> Skipping insert",
                        tenant_id,
                        user_id,
                        top_match.id,
                        score,
                    )
                    return str(top_match.id)
        except Exception as exc:
            logger.debug("Semantic memory deduplication lookup skipped: %s", exc)

        memory_id = str(uuid4())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=memory_id,
                    vector={"dense": vector},
                    payload={
                        "content": fact[:4000],
                        "tenant_id": str(tenant_id),
                        "user_id": str(user_id),
                        "memory_type": memory_type,
                        "importance": max(0.0, min(float(importance), 1.0)),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            ],
        )
        logger.info(
            "Stored semantic memory id=%s tenant=%s user=%s type=%s importance=%.2f",
            memory_id,
            tenant_id,
            user_id,
            memory_type,
            max(0.0, min(float(importance), 1.0)),
        )
        return memory_id

    def recall(
        self,
        query: str,
        user_id: str | int,
        tenant_id: str | int,
        top_k: int | None = None,
        memory_type: str | None = None,
    ) -> list[str]:
        """Recall relevant memories only from the requesting user's tenant scope."""
        if not query.strip():
            return []
        if memory_type is not None and memory_type not in _ALLOWED_TYPES:
            raise ValueError(f"Unsupported semantic memory type: {memory_type}")
        try:
            if not self.client.collection_exists(self.collection_name):
                return []

            must_conditions = [
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value=str(tenant_id))
                ),
                models.FieldCondition(
                    key="user_id", match=models.MatchValue(value=str(user_id))
                ),
            ]
            if memory_type is not None:
                must_conditions.append(
                    models.FieldCondition(
                        key="memory_type", match=models.MatchValue(value=memory_type)
                    )
                )

            response = self.client.query_points(
                collection_name=self.collection_name,
                query=self.embedding_model.embed_query(query),
                using="dense",
                query_filter=models.Filter(must=must_conditions),
                limit=top_k or settings.semantic_memory_top_k,
                with_payload=True,
            )
            points = getattr(response, "points", response)
            ranked = sorted(
                (
                    point
                    for point in points
                    if point.payload and point.payload.get("content")
                ),
                key=lambda point: float(getattr(point, "score", 0.0))
                * (0.5 + 0.5 * float(point.payload.get("importance", 0.5))),
                reverse=True,
            )
            memories = [point.payload["content"] for point in ranked]
            logger.info(
                "Recalled %s semantic memories (type=%s) for tenant=%s user=%s",
                len(memories),
                memory_type or "any",
                tenant_id,
                user_id,
            )
            return memories
        except Exception as exc:
            logger.warning(
                "Semantic memory recall failed; continuing without it: %s", exc
            )
            return []

    def forget(self, memory_id: str, user_id: str | int, tenant_id: str | int) -> bool:
        """Delete a memory only after verifying the caller owns it."""
        try:
            existing = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id],
                with_payload=True,
                with_vectors=False,
            )
            if not existing:
                return False
            payload = existing[0].payload or {}
            if payload.get("tenant_id") != str(tenant_id) or payload.get(
                "user_id"
            ) != str(user_id):
                return False
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[memory_id]),
            )
            return True
        except Exception as exc:
            logger.warning("Semantic memory forget failed: %s", exc)
            return False

    def clear_user(self, user_id: str | int, tenant_id: str | int) -> bool:
        """Remove all durable semantic memories owned by one user."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant_id",
                                match=models.MatchValue(value=str(tenant_id)),
                            ),
                            models.FieldCondition(
                                key="user_id",
                                match=models.MatchValue(value=str(user_id)),
                            ),
                        ]
                    )
                ),
            )
            return True
        except Exception as exc:
            logger.warning("Semantic memory clear failed: %s", exc)
            return False

    def prune_low_importance(self, threshold: float) -> bool:
        """Remove globally low-value semantic memories in the scheduled task."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="importance", range=models.Range(lt=threshold)
                            )
                        ]
                    )
                ),
            )
            return True
        except Exception as exc:
            logger.warning("Semantic memory prune failed: %s", exc)
            return False
