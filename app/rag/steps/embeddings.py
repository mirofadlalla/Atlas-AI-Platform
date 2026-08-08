from langchain_community.embeddings import HuggingFaceEmbeddings

# embedding model
embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
