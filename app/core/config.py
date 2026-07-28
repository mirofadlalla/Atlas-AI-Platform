from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    postgres_user : str = "postgres"
    postgres_pass : str = "1234"
    postgres_host : str = "localhost"
    postgres_port : int = 5432
    postgres_db : str =  ""
    hf_api : str = ""
    api_secret_key : str = ""
    
    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = "atlas_redis_password"
    redis_db: int = 0

    # Timeout in seconds for semantic chunking step (then fallback to token-based if exceeded)
    semantic_chunking_timeout: int = 900
    # Timeout in seconds for each embedding API request
    embedding_request_timeout: float = 120.0

    # Qdrant & RAG settings
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "atlas_documents1"
    sparse_embedding_model: str = "Qdrant/bm25"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    # LLM Cost Settings (per token)
    QWEN_INPUT_TOKEN_COST : float = 0.0001
    QWEN_OUTPUT_TOKEN_COST : float = 0.0001

    class Config:
        env_file = '.env'
        extra = "ignore"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_pass}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def REDIS_URL(self) -> str:
        """Return Redis URL with proper authentication"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def REDIS_URL_NO_DB(self) -> str:
        """Return Redis URL without database number (for semantic cache)"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/0"
    
settings = Settings()

