import os
import sys
from pathlib import Path
import logging
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from langchain_redis import RedisSemanticCache
from langchain_core.globals import set_llm_cache, get_llm_cache
from langchain_classic.chains import create_retrieval_chain 
from langchain_classic.chains.combine_documents import create_stuff_documents_chain 
from langchain_classic.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.runs import Runs
from app.models.costLog import CostLog
from app.rag.rerankers import RankingService
from app.repositories.runs_repository import RunsRepository
from app.repositories.cost_log_repository import CostLogRepository
from app.services.rag_services.query_logging_service import trigger_query_logging
from app.core.monitors import (
    cache_hits_total, 
    cache_misses_total,
    vector_search_queries_total,
    vector_search_duration_seconds,
    retrieved_chunks_count,
    reranking_queries_total,
    reranking_duration_seconds
)
from app.core.config import settings  # Import settings for Redis config

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.rag.steps.retriever import get_retriever
from app.services.llm_runner import CustomLocalLLM
from app.design_pattern.embedded_model import EmbeddedModel # Ensure it's LangChain compatible

# Initialize the embedding model singleton once at module load time
_embedding_model = EmbeddedModel()

# Initialize reranker singletons per strategy
_ranking_services = {}

def _get_ranking_service(strategy: str = "hybrid"):
    """Get or create a RankingService singleton for the given strategy."""
    if strategy not in _ranking_services:
        logger.info(f"Initializing RankingService with strategy: {strategy}")
        _ranking_services[strategy] = RankingService(strategy=strategy)
    return _ranking_services[strategy]

# Initialize LLM singleton once at module load time
logger.info("Initializing CustomLocalLLM singleton")
_cached_llm = CustomLocalLLM()
logger.info("CustomLocalLLM singleton ready")

# Query result cache - store results of queries for quick retrieval
_query_cache = {}
_query_cache_ttl = 3600  # 1 hour TTL for query cache

class RetrievalPipeline:
    def __init__(self, tenant_id: int, use_reranker: bool = True, reranker_strategy: str = None, db: Session = None):
        """
        Initialize the retrieval pipeline with optional reranking.
        
        Args:
            tenant_id: Tenant identifier
            use_reranker: Whether to use document reranking
            reranker_strategy: Reranking strategy ('cross-encoder', 'bm25', 'hybrid')
            db: Optional SQLAlchemy Session for saving runs and costs to database
        """
        self.tenant_id = tenant_id
        self.retriever = get_retriever(tenant_id)
        self.use_reranker = use_reranker
        self.db = db
        self.runs_repo = RunsRepository(db) if db else None
        self.cost_repo = CostLogRepository(db) if db else None
        
        # Initialize reranker if enabled - use cached singleton
        if use_reranker:
            self.ranking_service = _get_ranking_service(strategy=reranker_strategy)
        else:
            self.ranking_service = None
        
        # 1. Define the embedding model (Object)
        # Use the singleton instance so Redis can use it for similarity comparison
        self.embedding_model = _embedding_model 

        # 2. Setup Redis Semantic Cache (initialized once at load time)
        # Only set if not already set to avoid reinitializing
        if get_llm_cache() is None:
            logger.info(f"Initializing Redis Semantic Cache at {settings.redis_host}:{settings.redis_port}")
            try:
                import redis
                # Test Redis connection first
                logger.info(f"Testing Redis connection to {settings.REDIS_URL_NO_DB}...")
                redis_client = redis.from_url(settings.REDIS_URL_NO_DB)
                redis_client.ping()
                logger.info("✅ Redis connection verified")
                
                cache = RedisSemanticCache(
                    redis_url=settings.REDIS_URL_NO_DB,
                    embeddings=self.embedding_model,
                    ttl=86400, # one day
                    distance_threshold=0.2
                )
                set_llm_cache(cache)
                logger.info("✅ Redis Semantic Cache initialized successfully - LLM responses will be cached with TTL: 24h, Distance threshold: 0.2")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Redis cache: {e}")
                logger.warning("Continuing without Redis cache - LLM responses will NOT be cached")
                logger.info("Troubleshooting: Ensure Redis is running and accessible at " + settings.REDIS_URL_NO_DB)
                set_llm_cache(None)
        else:
            logger.info("Using existing Redis Semantic Cache")
        
        # 3. Setup Local LLM and Chain - use cached singleton
        self.local_llm = _cached_llm
        
        prompt = ChatPromptTemplate.from_template(
            "Answer the following question based only on the provided context:\n\n"
            "Context: {context}\n\n"
            "Question: {input}\n\n"
            "Answer:"
        )
        
        self.document_chain = create_stuff_documents_chain(self.local_llm, prompt)
        self.qa_chain = create_retrieval_chain(self.retriever, self.document_chain)

    def retrieve(self, query: str, top_k: int = 10, fetch_multiplier: int = 2):
        """
        Retrieve relevant documents for a query with optional reranking.
        
        For better reranking results, fetches more documents initially,
        then reranks down to top_k.
        
        Args:
            query: User query
            top_k: Number of top documents to return
            fetch_multiplier: Multiplier for initial fetch (e.g., 2 means fetch 2x top_k)
            
        Returns:
            List of relevant documents (reranked if enabled)
        """
        start_time = time.time()
        
        # Fetch more docs initially for better reranking (if enabled)
        fetch_count = max(top_k * fetch_multiplier, top_k) if self.use_reranker else top_k
        docs = self.retriever.invoke(query)
        
        retrieval_time = time.time() - start_time
        logger.debug(f"Document retrieval took {retrieval_time:.3f}s, got {len(docs)} documents")
        
        # Track retrieval metrics
        vector_search_queries_total.labels(tenant_id=str(self.tenant_id)).inc()
        vector_search_duration_seconds.observe(retrieval_time)
        retrieved_chunks_count.observe(len(docs))
        
        # Sort by ID to ensure deterministic ordering for caching
        docs = sorted(docs, key=lambda d: d.metadata.get('_id', ''))
        
        # Apply reranking if enabled
        if self.use_reranker and self.ranking_service and docs:
            rerank_start = time.time()
            
            # Convert LangChain documents to format acceptable by ranking service
            doc_dicts = [
                {
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'score': 1.0  # Initial retrieval score
                }
                for doc in docs
            ]
            
            # Rerank documents
            reranked = self.ranking_service.rank(query, doc_dicts, top_k=top_k)
            
            rerank_time = time.time() - rerank_start
            logger.debug(f"Reranking took {rerank_time:.3f}s")
            
            # Track reranking metrics
            reranking_queries_total.labels(reranker_type=self.ranking_service.strategy).inc()
            reranking_duration_seconds.labels(reranker_type=self.ranking_service.strategy).observe(rerank_time)
            
            # Convert back to LangChain Document objects with updated metadata
            from langchain_core.documents import Document

            docs = [
                Document(
                    page_content=doc['content'],
                    metadata={
                        **doc['metadata'],
                        'original_score': doc['original_score'],
                        'rerank_score': doc['rerank_score'],
                        'combined_score': doc['combined_score']
                    }
                )
                for doc in reranked
            ]
        
        return docs[:top_k]
    
    def ask(self, query: str):
        """
        Answer the question using the Cache and the local LLM.
        If the question is similar to a previous one stored in Redis, it will respond immediately.
        Applies reranking if enabled. Tracks and logs run and cost metrics asynchronously.
        """
        start_time = time.time()
        full_answer = ""
        
        # Get reranked documents if reranker is enabled
        docs = self.retrieve(query) if self.use_reranker else self.retriever.invoke(query)
        
        # Stream the document chain response with context
        for chunk in self.document_chain.stream({"input": query, "context": docs}):
            if "answer" in chunk:
                full_answer += chunk["answer"]
                yield chunk["answer"]
        
        # Calculate metrics after streaming completes
        latency = time.time() - start_time
        usage = CustomLocalLLM.last_usage or {}  # Extract token usage from the model
        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)
        retrieved_docs_ids = ",".join([doc.metadata.get('_id', '') for doc in docs])
        
        # Queue background logging (non-blocking)
        if self.db:
            try:
                trigger_query_logging(
                    tenant_id=self.tenant_id,
                    query=query,
                    answer=full_answer,
                    latency=latency,
                    cache_hit=False,
                    retrieved_docs_ids=retrieved_docs_ids,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_name="Qwen2.5-1.5B"
                )
                logger.debug(f"Queued background logging for query: {query[:50]}...")
            except Exception as e:
                logger.error(f"Error queuing background logging: {e}")
    
    def ask_stream(self, query: str):
        """
        Stream the answer to a query with logging of run and cost information.
        
        This method:
        1. Checks query cache for recent identical queries
        2. Retrieves and optionally reranks documents using ranking_service
        3. Streams the answer chunks from the document chain
        4. Tracks latency and token usage
        5. Logs run and cost information to the database (if db session provided)
        
        Three-layer caching:
        1. Local query cache (_query_cache) - stores full query+answer results
        2. Redis Semantic Cache - caches LLM responses for similar queries
        3. Database - logs all queries for analytics
        """
        start_time = time.time()
        full_answer = ""
        cache_hit = False
        cache_source = "NONE"  # Track where the cache hit came from
        
        # Create cache key from query
        cache_key = f"{self.tenant_id}:{hashlib.md5(query.encode()).hexdigest()}"
        
        # Clean up expired entries periodically
        now = time.time()
        expired_keys = [k for k, v in _query_cache.items() if now - v.get('timestamp', 0) > _query_cache_ttl]
        for k in expired_keys:
            _query_cache.pop(k, None)

        # 1. Check local query cache first (fastest)
        if cache_key in _query_cache:
            cached_result = _query_cache[cache_key]
            cache_hit = True
            cache_source = "LOCAL_MEMORY"
            cache_hits_total.labels(cache_type="local_memory").inc()
            logger.info(f"[⚡ CACHE HIT - LOCAL MEMORY] Returning cached result for: {query[:50]}...")
            full_answer = cached_result['answer']
            # Stream the cached answer
            yield full_answer
            # Log the cached query
            latency = time.time() - start_time
            usage = CustomLocalLLM.last_usage or {}
            input_tokens = usage.get("input", 0)
            output_tokens = usage.get("output", 0)
            retrieved_docs_ids = cached_result.get('docs_ids', '')
            if self.db:
                try:
                    trigger_query_logging(
                        tenant_id=self.tenant_id,
                        query=query,
                        answer=full_answer,
                        latency=latency,
                        cache_hit=True,
                        retrieved_docs_ids=retrieved_docs_ids,
                        input_tokens=0,
                        output_tokens=0,
                        model_name="Qwen2.5-1.5B (CACHED)"
                    )
                    logger.debug(f"Logged cached query execution")
                except Exception as e:
                    logger.error(f"Error logging cached query: {e}")
            return
        
        logger.info(f"[🔄 CACHE MISS - LOCAL MEMORY] Generating new answer for: {query[:50]}...")
        
        # 2. Get reranked documents if reranker is enabled
        docs = self.retrieve(query) if self.use_reranker else self.retriever.invoke(query)
        
        # 3. Stream the document chain response with context
        logger.info(f"Starting answer generation for query: {query[:50]}...")
        logger.info(f"Number of context documents: {len(docs)}")
        
        # Track if Redis cache is being used by checking LLM's internal state
        llm_start_time = time.time()
        redis_cache = get_llm_cache()  # Get current cache
        
        for chunk in self.document_chain.stream({"input": query, "context": docs}):
            # Handle different chunk formats from the chain
            if isinstance(chunk, dict):
                # LangChain chains return dictionaries with various keys
                # The last key contains the actual output
                for key, value in chunk.items():
                    if isinstance(value, str) and value.strip():
                        full_answer += value
                        yield value
            elif isinstance(chunk, str):
                # Direct string output
                full_answer += chunk
                yield chunk
        
        # Check if response came from Redis cache
        llm_time = time.time() - llm_start_time
        if llm_time < 1.5 and full_answer and redis_cache:  # Very fast response with Redis available
            logger.info(f"[⚡ POSSIBLE REDIS CACHE HIT] LLM response time: {llm_time:.2f}s")
            cache_source = "REDIS"
            cache_hit = True
            cache_hits_total.labels(cache_type="redis").inc()
        else:
            logger.info(f"[🔄 LLM GENERATED NEW RESPONSE] Response time: {llm_time:.2f}s (Redis available: {redis_cache is not None})")
            cache_source = "LLM_GENERATED"
            cache_hit = False
            cache_misses_total.labels(cache_type="redis").inc()
        
        logger.info(f"Answer generation completed. Length: {len(full_answer)} chars")

        # 4. Calculate metrics after streaming completes
        latency = time.time() - start_time
        usage = CustomLocalLLM.last_usage or {}  # Extract token usage from the model
        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)
        cost = (input_tokens * 0.0000001) + (output_tokens * 0.0000002)
        retrieved_docs_ids = ",".join([doc.metadata.get('_id', '') for doc in docs])
        
        # 5. Cache the result in local memory for future identical queries
        _query_cache[cache_key] = {
            'answer': full_answer,
            'docs_ids': retrieved_docs_ids,
            'timestamp': time.time()
        }
        logger.info(f"✅ Query result cached in local memory")
        
        # 6. Log query metrics
        logger.info(f"Query processed - Latency: {latency:.2f}s, Cache: {cache_source}, Docs: {len(docs)}, Cost: ${cost:.6f}")
        
        # 7. Queue background logging (non-blocking)
        # This happens asynchronously, so the response completes immediately
        if self.db:
            try:
                trigger_query_logging(
                    tenant_id=self.tenant_id,
                    query=query,
                    answer=full_answer,
                    latency=latency,
                    cache_hit=cache_hit,
                    retrieved_docs_ids=retrieved_docs_ids,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_name="Qwen2.5-1.5B"
                )
                logger.debug(f"Queued background logging for query: {query[:50]}...")
            except Exception as e:
                logger.error(f"Error queuing background logging: {e}")

    @property
    def _llm_type(self) -> str:
        return "custom_huggingface_stream"
    

# retrieval_pipeline = RetrievalPipeline(tenant_id="1234")
# retrieved_docs = retrieval_pipeline.retrieve("What was the effective tax rate for the year ended December 31, 2023, following the IRS rule change regarding foreign tax credits?")
# print(retrieved_docs)

# # [Document(metadata={'tenant_id': 123, 'source': 'google.pdf', 'author': 'Omar', '_id': '126f69ef-db44-452c-82c8-842815f504a9', '_collection_name': 'atlas_documents1'}, page_content='Investments Measured at Fair Value on a Nonrecurring Basis\nOur non-marketable equity securities are investments in privately held companies without readily determinable \nmarket values. The carrying value of our non-marketable equity securities is adjusted to fair value upon observable \ntransactions for identical or similar investments of the same issuer or impairment. Non-marketable equity securities \nthat have been remeasured during the period based on observable transactions are classified within Level 2 or Level 3'), Document(metadata={'tenant_id': 123, 'source': 'google.pdf', 'author': 'Omar', '_id': '0a081284-de05-4e2c-b09a-5af2c6d93629', '_collection_name': 'atlas_documents1'}, page_content='measurement alternative") and are measured at cost, less impairment, subject to upward and downward adjustments \nresulting from observable price changes for identical or similar investments of the same issuer. These adjustments \nrequire quantitative assessments of the fair value of our securities, which may require the use of unobservable inputs. Adjustments are determined primarily based on a market approach as of the transaction date and involve the use of \nestimates using the best information available, which may include cash flow projections or other available market data. Non-marketable equity securities are also evaluated for impairment, based on qualitative factors including the \ncompanies\' financial and liquidity position and access to capital resources, among others. When indicators of \nimpairment exist, we prepare quantitative measurements of the fair value of our equity investments using a market \napproach or an income approach, which requires judgment and the use of unobservable inputs, including discount \nrates, investee revenues and costs, and comparable market data of private and public companies, among others. Table of Contents Alphabet Inc.'), Document(metadata={'tenant_id': 123, 'source': 'google.pdf', 'author': 'Omar', '_id': 'c16bfdd1-bdeb-4f4e-812f-f8f997a63186', '_collection_name': 'atlas_documents1'}, page_content='marketable equity securities by $597 million. From time to time, we may enter into derivatives to hedge the market \nprice risk on certain of our marketable equity securities. Our non-marketable equity securities not accounted for under the equity method are adjusted to fair value for \nobservable transactions for identical or similar investments of the same issuer or impairment (referred to as the \nmeasurement alternative). The fair value measured at the time of the observable transaction is not necessarily an \nindication of the current fair value as of the balance sheet date. These investments, especially those that are in the \nearly stages, are inherently risky because the technologies or products these companies have under development are \ntypically in the early phases and may never materialize, and they may experience a decline in financial condition, \nwhich could result in a loss of a substantial part of our investment in these companies. Valuations of our equity \ninvestments in private companies are inherently more complex due to the lack of readily available market data and \nobservable transactions at lower valuations could result in significant losses. In addition, global economic conditions \ncould result in additional volatility. The success of our investment in any private company is also typically dependent on \nthe likelihood of our ability to realize appreciation in the value of investments through liquidity events such as public \nofferings, acquisitions, private sales or other market events.'), Document(metadata={'tenant_id': 123, 'source': 'google.pdf', 'author': 'Omar', '_id': 'c10ea4d4-23fa-42a9-b526-b4c1cbbf0375', '_collection_name': 'atlas_documents1'}, page_content='Equity Investment Risk\nOur marketable and non-marketable equity securities are subject to a wide variety of market-related risks that \ncould substantially reduce or increase the fair value of our holdings. Our marketable equity securities are publicly traded stocks or funds and our non-marketable equity securities are \ninvestments in privately held companies, some of which are in the startup or development stages. We record marketable equity securities not accounted for under the equity method at fair value based on readily \ndeterminable market values, of which publicly traded stocks and mutual funds are subject to market price volatility, and \nrepresent $5.2 billion  and $6.0 billion  of our investments as of December 31, 2022  and 2023, respectively. A \nhypothetical adverse price change of 10% on our December 31, 2023  balance would decrease the fair value of'), Document(metadata={'tenant_id': 123, 'source': 'google.pdf', 'author': 'Omar', '_id': 'f9e9f49c-2d41-42fc-9b01-b971c4280e77', '_collection_name': 'atlas_documents1'}, page_content='See Note 7 for further details on OI&E. The carrying values for marketable and non-marketable equity securities are summarized below (in millions):\nAs of December 31, 2022 As of December 31, 2023\nMarketable \nEquity \nSecurities\nNon-Marketable \nEquity \nSecurities Total\nMarketable \nEquity \nSecurities\nNon-Marketable \nEquity \nSecurities Total\nTotal initial cost $ 5,764 $ 16,157 $ 21,921 $ 5,418 $ 17,616 $ 23,034 \nCumulative net \ngain (loss)(1)  (608)  12,372  11,764  555  11,150  11,705 \nCarrying value $ 5,156 $ 28,529 $ 33,685 $ 5,973 $ 28,766 $ 34,739 \n(1) Non-marketable equity securities cumulative net gain (loss) is comprised of $16.8 billion  gains and $4.5 billion  losses \n(including impairments) as of December 31, 2022 and $18.1 billion gains and $6.9 billion losses (including impairments) as of \nDecember 31, 2023. Gains and Losses on Marketable and Non-marketable Equity Securities\nGains and losses (including impairments), net, for marketable and non-marketable equity securities included in \nOI&E are summarized below (in millions):\nYear Ended December 31,\n 2021 2022 2023\nRealized net gain (loss) on equity securities sold during the \nperiod $ 1,196 $ (442) $ 690 \nUnrealized net gain (loss) on marketable equity securities  1,335  (3,242)  790 \nUnrealized net gain (loss) on non-marketable equity securities(1)  9,849  229  (1,088) \nTotal gain (loss) on equity securities in other income \n(expense), net $ 12,380 $ (3,455) $ 392 \n(1) Unrealized gain (loss) on non-marketable equity securities accounted for under the measurement alternative is comprised of \n$10.0 billion, $3.3 billion, and $1.8 billion of upward adjustments as of December 31, 2021, 2022, and 2023, respectively, and')]

# for doc in retrieved_docs:
#     print(doc.metadata['_id'])  # Print the first 200 characters of each retrieved document



# if __name__ == "__main__":
#     pipeline = RetrievalPipeline(tenant_id="1234")
    
#     query = "What level in the fair value hierarchy do debt securities get classified in?"
    
#     # connect to Redis : First call will compute the answer and store it in Redis it will take 
#     # result1 = pipeline.ask(query)
#     # print(result1, end="", flush=True)

#     for chunk in pipeline.ask_stream(query):
#         print(chunk , end="" , flush=True)
    
#     print("--- Second Call (Cached from Redis) ---")
#     for chunk in pipeline.ask_stream(query):
#         print(chunk, end="", flush=True)
#     print("\n")