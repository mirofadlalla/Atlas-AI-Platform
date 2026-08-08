"""Container-service checks used by the GitHub Actions integration job."""

import os

import psycopg2
import pytest
import redis
from qdrant_client import QdrantClient


pytestmark = pytest.mark.integration


def test_postgresql_connection():
    connection = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASS"],
        dbname=os.environ["POSTGRES_DB"],
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    finally:
        connection.close()


def test_redis_connection():
    client = redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ.get("REDIS_PASSWORD") or None,
        decode_responses=True,
    )
    assert client.ping() is True


def test_qdrant_connection():
    client = QdrantClient(url=os.environ["QDRANT_URL"])
    assert client.get_collections().collections is not None
