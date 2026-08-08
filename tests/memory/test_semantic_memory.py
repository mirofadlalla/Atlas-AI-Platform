from types import SimpleNamespace

from app.memory.semantic_memory import SemanticMemory


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, _query):
        return [0.1, 0.2]


class FakeQdrant:
    def __init__(self):
        self.exists = False
        self.created_config = None
        self.filters = []
        self.points = []

    def collection_exists(self, _collection):
        return self.exists

    def create_collection(self, collection_name, vectors_config):
        self.exists = True
        self.created_config = vectors_config

    def create_payload_index(self, **_kwargs):
        pass

    def upsert(self, collection_name, points):
        self.points.extend(points)

    def query_points(self, **kwargs):
        self.filters.append(kwargs["query_filter"])
        return SimpleNamespace(
            points=[SimpleNamespace(payload={"content": "Prefers Arabic"})]
        )


def test_store_creates_named_dense_vector_collection():
    client = FakeQdrant()
    memory = SemanticMemory(client=client, embedding_model=FakeEmbeddings())

    memory_id = memory.store("Prefers Arabic", "user-1", "tenant-1", "preference", 2.0)

    assert memory_id
    assert "dense" in client.created_config
    assert client.points[0].payload["importance"] == 1.0
    assert client.points[0].payload["tenant_id"] == "tenant-1"


def test_recall_filters_by_both_tenant_and_user():
    client = FakeQdrant()
    client.exists = True
    memory = SemanticMemory(client=client, embedding_model=FakeEmbeddings())

    assert memory.recall("language", "user-1", "tenant-1") == ["Prefers Arabic"]

    conditions = client.filters[0].must
    assert {(condition.key, condition.match.value) for condition in conditions} == {
        ("tenant_id", "tenant-1"),
        ("user_id", "user-1"),
    }
