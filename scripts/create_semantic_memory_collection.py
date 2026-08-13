"""Initialize Atlas AI's semantic-memory collection and payload indexes."""

from app.memory.semantic_memory import SemanticMemory

if __name__ == "__main__":
    memory = SemanticMemory()
    # Reuse the configured embedding model so vector size always matches it.
    vector_size = len(memory.embedding_model.embed_query("initialize semantic memory"))
    memory._ensure_collection(vector_size)
    print(f"Semantic memory collection '{memory.collection_name}' is ready.")
