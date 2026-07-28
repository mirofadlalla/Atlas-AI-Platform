import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, SparseVectorParams, PointStruct
from fastembed import SparseTextEmbedding 
from app.design_pattern.embedded_model import EmbeddedModel
from app.core.config import settings

_global_dense_model = None
_global_sparse_model = None

def get_shared_dense_model():
    global _global_dense_model
    if _global_dense_model is None:
        _global_dense_model = EmbeddedModel()
    return _global_dense_model

def get_shared_sparse_model():
    global _global_sparse_model
    if _global_sparse_model is None:
        _global_sparse_model = SparseTextEmbedding(model_name=settings.sparse_embedding_model)
    return _global_sparse_model

class QdrantRepository:
    def __init__(self, url: str = None):
        # Initialize Qdrant client from settings if url not provided
        qdrant_url = url or settings.qdrant_url
        self.client = QdrantClient(url=qdrant_url)
        
        # Share global model singletons for hybrid embeddings
        self.dense_model = get_shared_dense_model()
        self.sparse_model = get_shared_sparse_model()

    def create_collection(self, collection_name: str, vector_size: int = 1024):
        # Create collection if it does not exist
        if not self.client.collection_exists(collection_name):
            self.client.recreate_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(size=vector_size, distance=Distance.COSINE)
                },  
                sparse_vectors_config={
                    "sparse": SparseVectorParams()
                }
            )
            print(f"Collection '{collection_name}' created for Hybrid Search.")

    def add_hybrid_documents(self, collection_name: str, documents: list[dict]):
        """
        Add hybrid documents (Dense + Sparse embeddings) to Qdrant.
        
        documents: List of dictionaries
        Example: [{"text": "Machine learning is...", "metadata": {"tenant_id": 123}}]
        """
        if not documents:
            return

        # extract point IDs from incoming documents to check for duplicates
        point_ids = [doc.get("id") for doc in documents]

        # 2. 
        # Retrieve existing points from Qdrant to check for duplicates (based on IDs)
        try:
            existing_points = self.client.retrieve(
                collection_name=collection_name,
                ids=point_ids,
                with_payload=False,
                with_vectors=False
            )
            # Create a set of existing IDs for O(1) lookups
            existing_ids = {point.id for point in existing_points}
        except Exception as e:
            print(f"Error checking existing IDs: {e}")
            existing_ids = set()

        # 3. Filter out documents that already exist in Qdrant to avoid redundant embeddings
        new_documents = [doc for doc in documents if doc.get("id") not in existing_ids]

        # 4. If no new documents, skip embedding and insertion to save resources
        if not new_documents:
            print(f"All {len(documents)} chunks already exist in Qdrant. Skipping embedding to save resources.")
            return

        print(f"Found {len(new_documents)} new chunks out of {len(documents)}. Generating embeddings...")

        # 5. Generate Dense and Sparse embeddings for new documents only
        texts = [doc["text"] for doc in new_documents]
        dense_vectors = self.dense_model.embed_documents(texts)
        sparse_vectors = list(self.sparse_model.embed(texts)) 

        points = []
        for i in range(len(new_documents)):
            point_id = new_documents[i].get("id")
            
            payload = {
                "content": new_documents[i]["text"],       
                "payload": new_documents[i]["metadata"]    
            }
            
            vector = {
                "dense": dense_vectors[i],
                "sparse": {
                    "indices": sparse_vectors[i].indices.tolist(),
                    "values": sparse_vectors[i].values.tolist()
                }
            }
            
            points.append(
                PointStruct(id=point_id, payload=payload, vector=vector)
            )

        # 6. Insert new points into Qdrant
        self.client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f"[✅] {len(points)} NEW Hybrid documents added to '{collection_name}'.")


    def delete_collection(self, collection_name: str):
        # Delete collection if exists
        if self.client.collection_exists(collection_name):
            self.client.delete_collection(collection_name)
            print(f"[✅] Collection '{collection_name}' deleted from Qdrant.")
        else:
            print(f"[ℹ️] Collection '{collection_name}' does not exist in Qdrant.")


    def list_collections(self):
        # List all collections in Qdrant
        collections = self.client.get_collections()
        return [col.name for col in collections.collections]


    def search(self, collection_name: str, query_vector: list, top_k: int = 5):
        # Perform search in Qdrant collection
        results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k
        )
        return results
    
    # get all points in a collection (for debugging or evaluation purposes)
    def get_all_points(self, collection_name: str):
        try:
            points = self.client.retrieve(
                collection_name=collection_name,
                with_payload=True,
                with_vectors=False
            )
            return points
        except Exception as e:
            print(f"[⚠️] Error retrieving points: {e}")
            return []
        

# ps = QdrantRepository()
# points = ps.get_all_points("atlas_documents1")
# print(f"Total points in collection: {len(points)}")

# print("Sample point:", points[0] if points else "No points found")


