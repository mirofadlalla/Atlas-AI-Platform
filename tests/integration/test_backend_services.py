"""Container-service checks used by the GitHub Actions integration job."""

import os

import psycopg2
import pytest
import redis
from qdrant_client import QdrantClient

pytestmark = pytest.mark.integration


def test_postgresql_connection():
    if "POSTGRES_PORT" not in os.environ or "POSTGRES_HOST" not in os.environ:
        pytest.skip("POSTGRES integration environment variables not set")
    connection = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASS") or os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    finally:
        connection.close()


def test_redis_connection():
    if "REDIS_HOST" not in os.environ or "REDIS_PORT" not in os.environ:
        pytest.skip("REDIS integration environment variables not set")
    client = redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ.get("REDIS_PASSWORD") or None,
        decode_responses=True,
    )
    assert client.ping() is True


def test_qdrant_connection():
    if "QDRANT_URL" not in os.environ:
        pytest.skip("QDRANT_URL integration environment variable not set")
    client = QdrantClient(url=os.environ["QDRANT_URL"])
    assert client.get_collections().collections is not None
