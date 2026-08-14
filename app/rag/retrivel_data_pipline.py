import threading
import logging
import hashlib
import time
from cachetools import TTLCache

create_retrieval_chain = None
create_stuff_documents_chain = None

try:
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
except (ImportError, ModuleNotFoundError):
    try:
        from langchain.chains.retrieval import create_retrieval_chain
        from langchain.chains.combine_documents import create_stuff_documents_chain
    except (ImportError, ModuleNotFoundError):
        try:
            from langchain_classic.chains import create_retrieval_chain
            from langchain_classic.chains.combine_documents.stuff import (
                create_stuff_documents_chain,
            )
        except (ImportError, ModuleNotFoundError):
            pass

if create_stuff_documents_chain is None:

    def create_stuff_documents_chain(llm, prompt):
        class _StuffChain:
            def __init__(self, llm, prompt):
                self.llm = llm
                self.prompt = prompt

            def invoke(self, input_dict):
                docs = input_dict.get("context", [])
                if isinstance(docs, list):
                    context_str = "\n\n".join(
                        doc.page_content if hasattr(doc, "page_content") else str(doc)
                        for doc in docs
                    )
                else:
                    context_str = str(docs)
                user_input = input_dict.get("input", "")
                if hasattr(self.prompt, "format_messages"):
                    messages = self.prompt.format_messages(
                        context=context_str, input=user_input
                    )
                    return self.llm.invoke(messages)
                elif hasattr(self.prompt, "format"):
                    text = self.prompt.format(context=context_str, input=user_input)
                    return self.llm.invoke(text)
                return self.llm.invoke(
                    f"Context:\n{context_str}\n\nQuestion: {user_input}\nAnswer:"
                )

        return _StuffChain(llm, prompt)


if create_retrieval_chain is None:

    def create_retrieval_chain(retriever, document_chain):
        class _RetrievalChain:
            def __init__(self, retriever, doc_chain):
                self.retriever = retriever
                self.doc_chain = doc_chain

            def invoke(self, input_dict):
                query = input_dict.get("input", "")
                docs = self.retriever.invoke(query)
                res = self.doc_chain.invoke({"context": docs, "input": query})
                ans = res.content if hasattr(res, "content") else str(res)
                return {"input": query, "context": docs, "answer": ans}

        return _RetrievalChain(retriever, document_chain)


try:
    from langchain_core.prompts import ChatPromptTemplate
except (ImportError, ModuleNotFoundError):
    from langchain.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.monitors import (
    cache_hits_total,
    reranking_duration_seconds,
    reranking_queries_total,
    retrieved_chunks_count,
    vector_search_duration_seconds,
    vector_search_queries_total,
)
from app.design_pattern.embedded_model import EmbeddedModel
from app.memory.working_memory import WorkingMemory
from app.rag.rerankers import RankingService
from app.repositories.cost_log_repository import CostLogRepository
from app.repositories.runs_repository import RunsRepository
from app.rag.steps.retriever import get_retriever
from app.services.llm_runner import CustomLocalLLM
from app.services.rag_services.query_logging_service import trigger_query_logging

logger = logging.getLogger(__name__)

# Initialize the embedding model singleton once at module load time
_embedding_model = EmbeddedModel()

# Initialize reranker singletons per strategy
_ranking_services = {}
_ranking_services_lock = threading.Lock()

# "BM25" : boj


def _get_ranking_service(strategy: str = "hybrid"):
    """Get or create a RankingService singleton for the given strategy (thread-safe)."""
    if strategy not in _ranking_services:
        with _ranking_services_lock:
            # Double-checked locking to avoid duplicate initialization under concurrency
            if strategy not in _ranking_services:
                logger.info(f"Initializing RankingService with strategy: {strategy}")
                _ranking_services[strategy] = RankingService(strategy=strategy)
    return _ranking_services[strategy]


# Initialize LLM singleton once at module load time
logger.info("Initializing CustomLocalLLM singleton")
_cached_llm = CustomLocalLLM()
logger.info("CustomLocalLLM singleton ready")

# ---------------------------------------------------------------------------
# FIX #4 (Thread-safety / TTL): local query cache using cachetools.TTLCache
# instead of a plain dict. TTLCache handles expiry + is safe to guard with a
# single lock for read/write/evict operations (plain dict + manual TTL loop
# was not atomic under concurrent requests).
# Cache keys already include tenant_id (see _build_cache_key), so this cache
# was NOT the tenant-isolation bug -- only the Redis semantic cache was.
# ---------------------------------------------------------------------------
_QUERY_CACHE_MAXSIZE = 10_000
_QUERY_CACHE_TTL_SECONDS = 3600  # 1 hour TTL
_query_cache = TTLCache(maxsize=_QUERY_CACHE_MAXSIZE, ttl=_QUERY_CACHE_TTL_SECONDS)
_query_cache_lock = threading.Lock()


def build_query_cache_key(
    tenant_id: str | int,
    query: str,
    chat_history: str = "",
    user_id: str | int | None = None,
    session_id: str | None = None,
) -> str:
    """Build an exact-answer cache key for the complete request scope.

    The RAG answer can depend on short-term conversation history, semantic
    memories, and episodic memories.  Those memories are user-scoped, and
    short-term history is session-scoped, so final answers must not be shared
    across either boundary.
    """
    cache_input = "\n".join(
        (
            f"tenant={tenant_id}",
            f"user={user_id or ''}",
            f"session={session_id or ''}",
            f"query={query.strip()}",
            f"history={chat_history}",
        )
    )
    return f"{tenant_id}:{hashlib.md5(cache_input.encode()).hexdigest()}"


def get_local_query_cache(cache_key: str):
    """Read the thread-safe, self-expiring local final-answer cache."""
    with _query_cache_lock:
        return _query_cache.get(cache_key)


def set_local_query_cache(cache_key: str, value: dict) -> None:
    """Write the thread-safe, self-expiring local final-answer cache."""
    with _query_cache_lock:
        _query_cache[cache_key] = value


def serialize_retrieved_documents(documents) -> list[dict]:
    """Return the public document shape used by both /ask and /retrieve."""
    return [
        {
            "id": document.metadata.get("_id", ""),
            "content": document.page_content[:500],
            "metadata": document.metadata,
            "source": document.metadata.get("source", "unknown"),
        }
        for document in documents
    ]


# Token pricing now lives in settings (see FIX #7) so it can be updated in one
# place if the underlying model or provider pricing changes.
_DEFAULT_INPUT_TOKEN_COST = 0.0000001
_DEFAULT_OUTPUT_TOKEN_COST = 0.0000002
_INPUT_TOKEN_COST = getattr(
    settings, "QWEN_INPUT_TOKEN_COST", _DEFAULT_INPUT_TOKEN_COST
)
_OUTPUT_TOKEN_COST = getattr(
    settings, "QWEN_OUTPUT_TOKEN_COST", _DEFAULT_OUTPUT_TOKEN_COST
)


class RetrievalPipeline:
    def __init__(
        self,
        tenant_id: int,
        use_reranker: bool = False,
        reranker_strategy: str = None,
        db: Session = None,
    ):
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

        # Semantic retrieval is appropriate for documents and memories, but
        # not for final answers: similar questions may have different answers.
        self.embedding_model = _embedding_model

        # Setup Local LLM and Chain - use cached singleton
        self.local_llm = _cached_llm

        prompt = ChatPromptTemplate.from_template(
            "Answer the following question based only on the assembled context:\n\n"
            "{context}\n\n"
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
        fetch_count = (
            max(top_k * fetch_multiplier, top_k) if self.use_reranker else top_k
        )

        # -----------------------------------------------------------
        # FIX #2: fetch_count was computed but never actually passed to
        # the retriever, so the reranker was always working off the
        # retriever's default k (5), regardless of fetch_multiplier.
        # We now explicitly request fetch_count documents.
        #
        # LangChain's VectorStoreRetriever accepts a `k` override via
        # invoke()'s kwargs, which gets merged into search_kwargs for
        # this call only (it does not mutate the cached, shared
        # retriever instance).
        # -----------------------------------------------------------
        try:
            docs = self.retriever.invoke(query, k=fetch_count)
        except TypeError:
            # Fallback for retriever implementations that don't accept
            # a `k` override on invoke() -- rebuild search_kwargs safely
            # without mutating the shared/cached retriever.
            base_kwargs = dict(getattr(self.retriever, "search_kwargs", {}) or {})
            base_kwargs["k"] = fetch_count
            docs = self.retriever.vectorstore.as_retriever(
                search_kwargs=base_kwargs
            ).invoke(query)

        retrieval_time = time.time() - start_time
        logger.debug(
            f"Document retrieval took {retrieval_time:.3f}s, got {len(docs)} documents"
        )

        # Track retrieval metrics
        vector_search_queries_total.labels(tenant_id=str(self.tenant_id)).inc()
        vector_search_duration_seconds.observe(retrieval_time)
        retrieved_chunks_count.observe(len(docs))

        # Sort by ID to ensure deterministic ordering for caching
        docs = sorted(docs, key=lambda d: d.metadata.get("_id", ""))

        # Apply reranking if enabled
        if self.use_reranker and self.ranking_service and docs:
            rerank_start = time.time()

            # Convert LangChain documents to format acceptable by ranking service
            doc_dicts = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": 1.0,  # Initial retrieval score
                }
                for doc in docs
            ]

            # Rerank documents
            reranked = self.ranking_service.rank(query, doc_dicts, top_k=top_k)

            rerank_time = time.time() - rerank_start
            logger.debug(f"Reranking took {rerank_time:.3f}s")

            # Track reranking metrics
            reranking_queries_total.labels(
                reranker_type=self.ranking_service.strategy
            ).inc()
            reranking_duration_seconds.labels(
                reranker_type=self.ranking_service.strategy
            ).observe(rerank_time)

            # Convert back to LangChain Document objects with updated metadata
            from langchain_core.documents import Document

            docs = [
                Document(
                    page_content=doc["content"],
                    metadata={
                        **doc["metadata"],
                        "original_score": doc["original_score"],
                        "rerank_score": doc["rerank_score"],
                        "combined_score": doc["combined_score"],
                    },
                )
                for doc in reranked
            ]

        return docs[:top_k]

    # -------------------------------------------------------------------
    # FIX #5: shared internal helper used by both ask() and ask_stream()
    # so retrieval + local caching + logging logic exists in ONE place.
    # -------------------------------------------------------------------
    def _build_cache_key(
        self,
        query: str,
        chat_history: str = "",
        user_id: str | int | None = None,
        session_id: str | None = None,
    ) -> str:
        return build_query_cache_key(
            self.tenant_id, query, chat_history, user_id, session_id
        )

    def _get_cached(self, cache_key: str):
        return get_local_query_cache(cache_key)

    def _set_cached(self, cache_key: str, value: dict):
        set_local_query_cache(cache_key, value)

    def _log_run(
        self,
        query,
        full_answer,
        latency,
        cache_hit,
        retrieved_docs_ids,
        input_tokens,
        output_tokens,
        model_name,
    ):
        if not self.db:
            return
        try:
            # Trigger background logging task without blocking.
            trigger_query_logging(
                tenant_id=self.tenant_id,
                query=query,
                answer=full_answer,
                latency=latency,
                cache_hit=cache_hit,
                retrieved_docs_ids=retrieved_docs_ids,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=model_name,
            )
            logger.debug(f"Queued background logging for query: {query[:50]}...")
        except Exception as e:
            logger.error(f"Error queuing background logging: {e}")

    def _stream_answer(
        self,
        query: str,
        use_local_cache: bool = True,
        chat_history: str = "",
        user_id: str | int | None = None,
        session_id: str | None = None,
        cache_key: str | None = None,
        cache_checked: bool = False,
        documents=None,
    ):
        """
        Core streaming implementation shared by ask() and ask_stream().

        Yields answer chunks and, once exhausted, has already queued
        background logging as a side effect (mirrors previous behavior).

        Args:
            query: user question
            use_local_cache: whether to check/populate the local in-memory
                query cache (ask_stream() opts in; ask() previously did not,
                kept as an explicit flag rather than duplicated logic)
        """
        start_time = time.time()
        full_answer = ""
        cache_hit = False
        cache_source = "NONE"
        cache_key = cache_key or self._build_cache_key(
            query, chat_history, user_id, session_id
        )

        # 1. Check local query cache first (fastest) -- FIX #4: TTLCache is
        # self-expiring and access is guarded by a lock, so no manual
        # expired-key sweep and no race condition under concurrent requests.
        if use_local_cache and not cache_checked:
            cached_result = self._get_cached(cache_key)
            if cached_result is not None:
                cache_hit = True
                cache_source = "LOCAL_MEMORY"
                cache_hits_total.labels(cache_type="local_memory").inc()
                logger.info(
                    f"[⚡ CACHE HIT - LOCAL MEMORY] Returning cached result for: {query[:50]}..."
                )
                full_answer = cached_result["answer"]
                yield full_answer

                latency = time.time() - start_time
                retrieved_docs_ids = cached_result.get("docs_ids", "")
                self._log_run(
                    query,
                    full_answer,
                    latency,
                    True,
                    retrieved_docs_ids,
                    0,
                    0,
                    "Qwen2.5-1.5B (CACHED)",
                )
                return

            logger.info(
                f"[🔄 CACHE MISS - LOCAL MEMORY] Generating new answer for: {query[:50]}..."
            )

        # 2. Retrieve documents, then assemble only the highest-priority
        # context that fits the configured model window.
        docs = documents if documents is not None else self.retrieve(query)

        logger.info(f"Starting answer generation for query: {query[:50]}...")
        logger.info(f"Number of context documents: {len(docs)}")

        working_memory = WorkingMemory(settings.llm_context_window_tokens)
        assembled_context = (
            working_memory.add(
                "conversation context", chat_history, priority=2, max_tokens=1600
            )
            .add(
                "retrieved documents",
                "\n\n".join(doc.page_content for doc in docs),
                priority=5,
                max_tokens=5600,
            )
            .assemble()
        )
        logger.info(
            "Generating fresh answer tenant=%s question=%s context_tokens=%s sources=%s",
            self.tenant_id,
            query[:50],
            working_memory.tokens_used,
            working_memory.context_sources,
        )

        from langchain_core.documents import Document

        for chunk in self.document_chain.stream(
            {"input": query, "context": [Document(page_content=assembled_context)]}
        ):
            if isinstance(chunk, dict):
                for key, value in chunk.items():
                    if isinstance(value, str) and value.strip():
                        full_answer += value
                        yield value
            elif isinstance(chunk, str):
                full_answer += chunk
                yield chunk
        logger.info(f"Answer generation completed. Length: {len(full_answer)} chars")

        # Calculate metrics after streaming completes
        latency = time.time() - start_time
        usage = getattr(CustomLocalLLM, "last_usage", {}) or {}
        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)
        # FIX #7: pricing pulled from settings (with a safe fallback) instead
        # of being hardcoded inline, so a model/pricing change only needs to
        # be updated in one place (app.core.config.settings).
        cost = (input_tokens * _INPUT_TOKEN_COST) + (output_tokens * _OUTPUT_TOKEN_COST)
        retrieved_docs_ids = ",".join([doc.metadata.get("_id", "") for doc in docs])

        if use_local_cache:
            self._set_cached(
                cache_key,
                {
                    "answer": full_answer,
                    "docs_ids": retrieved_docs_ids,
                    "documents": serialize_retrieved_documents(docs),
                    "timestamp": time.time(),
                },
            )
            logger.info("✅ Query result cached in local memory")

        logger.info(
            f"Query processed - Latency: {latency:.2f}s, Cache: {cache_source}, "
            f"Docs: {len(docs)}, Cost: ${cost:.6f}"
        )

        self._log_run(
            query,
            full_answer,
            latency,
            cache_hit,
            retrieved_docs_ids,
            input_tokens,
            output_tokens,
            "Qwen2.5-1.5B",
        )

    def ask(
        self,
        query: str,
        chat_history: str = "",
        user_id: str | int | None = None,
        session_id: str | None = None,
        cache_key: str | None = None,
        cache_checked: bool = False,
        documents=None,
    ):
        """
        Answer the question using the Cache and the local LLM.

        Shares the exact-key local caching and logging path with ask_stream().
        """
        yield from self._stream_answer(
            query,
            use_local_cache=True,
            chat_history=chat_history,
            user_id=user_id,
            session_id=session_id,
            cache_key=cache_key,
            cache_checked=cache_checked,
            documents=documents,
        )

    def ask_stream(
        self,
        query: str,
        chat_history: str = "",
        user_id: str | int | None = None,
        session_id: str | None = None,
        cache_key: str | None = None,
        cache_checked: bool = False,
        documents=None,
    ):
        """
        Stream the answer to a query with logging of run and cost information.

        Uses exact-key in-process caching. Different questions always generate
        a fresh answer, even when their embeddings or document context overlap.
        """
        yield from self._stream_answer(
            query,
            use_local_cache=True,
            chat_history=chat_history,
            user_id=user_id,
            session_id=session_id,
            cache_key=cache_key,
            cache_checked=cache_checked,
            documents=documents,
        )

    @property
    def _llm_type(self) -> str:
        return "custom_huggingface_stream"
