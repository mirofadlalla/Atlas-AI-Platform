"""
Routes for RAG query/answer endpoints.

Implements query processing with streaming responses, rate limiting, and cost tracking.
Records metrics to Prometheus and database for monitoring and analytics.
"""
import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.schema.query_request import QueryRequest
from app.rag.retrivel_data_pipline import RetrievalPipeline
from app.services.mlflow_service import MLflowService
from app.services.rag_services.query_logging_service import trigger_query_logging
from app.services.auth_services.auth_service import get_current_user
from app.memory.short_term_memory import ConversationTurn, ShortTermMemory

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/query",
)


@router.post("/ask")
async def ask_question(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Answer a user question using the RAG pipeline with streaming response.
    
    This endpoint:
    1. Applies rate limiting based on user role
    2. Logs query metrics to MLflow
    3. Generates answer using RetrievalPipeline
    4. Tracks latency and costs
    5. Saves run and cost information to database
    
    Args:
        request: QueryRequest with user query
        current_user: Current user ID
        tenant_id: Tenant identifier
        db: Database session
        
    Returns:
        StreamingResponse with answer chunks
        
    Raises:
        HTTPException: If query processing fails
    """
    tenant_id: str = str(current_user.tenant_id)

    # Apply rate limiting (user gets standard limit)
    rate_limit(
        user_id=str(current_user.id),
        role=current_user.role,
        endpoint="/query/ask"
    )
    
    # Always end any active run from previous requests
    try:
        import mlflow
        mlflow.end_run()
    except:
        pass
    
    mlflow_run_id = None
    
    try:
        # Start MLflow run for this query
        mlflow_run_id = MLflowService.start_run(
            experiment_name=MLflowService.DEFAULT_EXPERIMENT_QUERY,
            run_name=f"query_{tenant_id}_{time.time()}",
            tags={
                'tenant_id': tenant_id,
                'user_id': current_user or 'anonymous',
                'endpoint': '/query/ask'
            }
        )
        
        # Log query parameters (only if run started successfully)
        if mlflow_run_id:
            import mlflow
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("query_length", len(request.query))
            mlflow.log_param("user_id", current_user or "anonymous")
        
        memory = ShortTermMemory()
        user_id = str(current_user.id)
        history = memory.load(tenant_id, user_id, request.session_id)
        chat_history = "\n".join(
            f"{turn.get('role', 'user').title()}: {turn.get('content', '')}"
            for turn in history
        )

        # Create pipeline for this tenant with database session for automatic logging
        pipeline = RetrievalPipeline(tenant_id=tenant_id, db=db)
        
        # Start timing
        start_time = time.time()
        
        async def answer_generator():
            """
            Generator that yields answer chunks while tracking metrics.
            
            Automatically logs query execution to:
            - MLflow for experiment tracking
            - Database (runs and costs) for analytics
            - Prometheus for monitoring and alerting
            """
            nonlocal mlflow_run_id
            
            full_answer = ""
            latency = 0
            cost_usd = 0.0
            input_tokens = 0
            output_tokens = 0
            cache_hit = False
            retrieved_docs_ids = ""
            
            try:
                # Stream answer chunks from the RAG pipeline
                for chunk in pipeline.ask_stream(query=request.query, chat_history=chat_history):
                    full_answer += chunk
                    yield chunk

                memory.save(tenant_id, user_id, request.session_id, ConversationTurn("user", request.query, ""))
                memory.save(tenant_id, user_id, request.session_id, ConversationTurn("assistant", full_answer, ""))
                
                # Calculate total latency
                latency = time.time() - start_time
                
                # Extract token usage from LLM for cost calculation
                try:
                    from app.services.llm_runner import CustomLocalLLM
                    usage = CustomLocalLLM.last_usage or {}
                    input_tokens = usage.get("input", 0)
                    output_tokens = usage.get("output", 0)
                    cost_usd = (input_tokens * 0.0000001) + (output_tokens * 0.0000002)
                except Exception as token_error:
                    logger.warning(f"Could not extract token usage: {token_error}")
                
                # Log metrics to MLflow
                if mlflow_run_id:
                    import mlflow
                    try:
                        mlflow.log_metric("latency_seconds", latency)
                        mlflow.log_metric("cost_usd", cost_usd)
                        mlflow.log_metric("input_tokens", input_tokens)
                        mlflow.log_metric("output_tokens", output_tokens)
                        mlflow.log_metric("answer_length", len(full_answer))
                    except Exception as mlflow_error:
                        logger.error(f"Error logging to MLflow: {mlflow_error}")
                
                logger.info(
                    f"Query completed - Tenant: {tenant_id}, User: {current_user}, "
                    f"Latency: {latency:.2f}s, Cost: ${cost_usd:.6f}"
                )
                
                # Trigger background logging to database and Prometheus metrics
                try:
                    # Also record metrics directly to Prometheus (fallback if webhook fails)
                    from app.core.monitors import (
                        llm_queries_total,
                        query_pipeline_duration_seconds,
                        llm_tokens_consumed,
                        llm_tokens_generated,
                        api_calls_cost_total
                    )
                    llm_queries_total.labels(tenant_id=tenant_id, model_name="Qwen2.5-1.5B").inc()
                    query_pipeline_duration_seconds.labels(pipeline_stage="total").observe(latency)
                    llm_tokens_consumed.labels(tenant_id=tenant_id, model_name="Qwen2.5-1.5B").inc(input_tokens + output_tokens)
                    llm_tokens_generated.labels(tenant_id=tenant_id, model_name="Qwen2.5-1.5B").inc(output_tokens)
                    api_calls_cost_total.labels(tenant_id=tenant_id, service="llm").inc(cost_usd)
                    
                    trigger_query_logging(
                        tenant_id=tenant_id,
                        query=request.query,
                        answer=full_answer,
                        latency=latency,
                        cache_hit=cache_hit,
                        retrieved_docs_ids=retrieved_docs_ids,
                        input_tokens=int(input_tokens),
                        output_tokens=int(output_tokens),
                        model_name="Qwen2.5-1.5B"
                    )
                except Exception as logging_error:
                    logger.error(f"Error triggering query logging: {logging_error}")
                
            except Exception as e:
                logger.error(f"Error during query streaming: {e}", exc_info=True)
                yield f"\n\nError: {str(e)}"
            
            finally:
                # End MLflow run
                if mlflow_run_id:
                    try:
                        MLflowService.end_run(status="FINISHED")
                    except Exception as mlflow_end_error:
                        logger.error(f"Error ending MLflow run: {mlflow_end_error}")
        
        return StreamingResponse(answer_generator(), media_type="text/plain")
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        # End the run if it was started
        if mlflow_run_id:
            MLflowService.end_run(status="FAILED")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your query. Please try again.",
        )


@router.post("/retrieve")
async def retrieve_documents(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve relevant documents for a query without generating an answer.
    
    This endpoint:
    1. Applies rate limiting
    2. Retrieves relevant documents from the vector database
    3. Returns document metadata and content
    
    Args:
        request: QueryRequest with user query
        current_user: Current user ID
        tenant_id: Tenant identifier
        db: Database session
        
    Returns:
        List of retrieved documents with relevance scores
    """
    tenant_id: str = str(current_user.tenant_id)

    # Apply rate limiting
    rate_limit(
        user_id=str(current_user.id),
        role=current_user.role,
        endpoint="/query/retrieve"
    )
    
    try:
        # Create pipeline for this tenant
        pipeline = RetrievalPipeline(tenant_id=tenant_id)
        
        # Retrieve documents
        documents = pipeline.retrieve(query=request.query)
        
        # Format response
        doc_results = []
        for doc in documents:
            doc_results.append({
                "id": doc.metadata.get("_id", ""),
                "content": doc.page_content[:500],  # First 500 chars
                "metadata": doc.metadata,
                "source": doc.metadata.get("source", "unknown")
            })
        
        logger.info(
            f"Documents retrieved - Tenant: {tenant_id}, Query: {request.query[:50]}, "
            f"Documents found: {len(doc_results)}"
        )
        
        return {
            "query": request.query,
            "documents_count": len(doc_results),
            "documents": doc_results
        }
        
    except Exception as e:
        logger.error(f"Error retrieving documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving documents. Please try again.",
        )

@router.get("/cost-analytics")
async def get_cost_analytics(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get cost analytics for the current tenant.
    
    Returns:
        dict: Cost breakdown by model, date, and total costs
    """
    tenant_id: str = str(current_user.tenant_id)

    try:
        from app.models.costLog import CostLog
        from app.models.runs import Runs
        from sqlalchemy import func
        
        # Query total cost and token usage with proper joins
        cost_data = db.query(
            func.sum(CostLog.cost_usd).label('total_cost'),
            func.sum(CostLog.input_tokens).label('total_input_tokens'),
            func.sum(CostLog.output_tokens).label('total_output_tokens'),
            CostLog.model_name
        ).join(
            Runs, CostLog.run_id == Runs.run_id
        ).filter(
            Runs.tenant_id == tenant_id
        ).group_by(CostLog.model_name).all()
        
        analytics = {
            "total_cost": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_model": []
        }
        
        for row in cost_data:
            if row.total_cost:
                analytics["total_cost"] += float(row.total_cost)
            if row.total_input_tokens:
                analytics["total_input_tokens"] += int(row.total_input_tokens)
            if row.total_output_tokens:
                analytics["total_output_tokens"] += int(row.total_output_tokens)
            
            analytics["by_model"].append({
                "model": row.model_name,
                "cost": float(row.total_cost) if row.total_cost else 0.0,
                "input_tokens": int(row.total_input_tokens) if row.total_input_tokens else 0,
                "output_tokens": int(row.total_output_tokens) if row.total_output_tokens else 0
            })
        
        logger.info(f"Cost analytics retrieved for tenant: {tenant_id}")
        return analytics
        
    except Exception as e:
        logger.error(f"Error retrieving cost analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving cost analytics. Please try again.",
        )


@router.get("/runs")
async def get_runs(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all query runs for the current tenant.
    
    Returns:
        list: Recent query runs with latency and document info
    """
    tenant_id: str = str(current_user.tenant_id)

    try:
        from app.repositories.runs_repository import RunsRepository
        from app.models.runs import Runs
        from sqlalchemy import desc
        
        runs_repo = RunsRepository(db)
        
        # Get last 50 runs
        runs = db.query(Runs).filter(
            Runs.tenant_id == tenant_id
        ).order_by(desc(Runs.created_at)).limit(50).all()
        
        runs_list = []
        for run in runs:
            runs_list.append({
                "run_id": str(run.run_id),
                "query": run.query[:100],  # Truncate for display
                "answer": run.answer[:200] if run.answer else "",
                "latency": float(run.latency) if run.latency else 0.0,
                "cache_hit": run.cache_hit,
                "retrieved_docs_ids": run.retrieved_docs_ids,
                "created_at": run.created_at.isoformat() if run.created_at else None
            })
        
        logger.info(f"Runs retrieved for tenant: {tenant_id}, count: {len(runs_list)}")
        return {
            "runs": runs_list,
            "count": len(runs_list)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving runs. Please try again.",
        )
