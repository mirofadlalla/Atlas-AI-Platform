"""
Routes for AI Agent endpoints.

Implements agent-based question answering with advanced reasoning capabilities.
Records metrics to Prometheus and database for monitoring and analytics.
Supports both streaming (SSE) and batch response modes.
"""
import json
import logging
import time
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.agent.core.graph import agent_app
from app.agent.observability.metrics import agent_executions_total
from app.agent.utils.run_cache import cache_run_result, get_cached_run_result
from app.agent.utils.state_helpers import create_initial_state
from app.services.rag_services.agent_logging_service import trigger_agent_logging
from app.services.auth_services.auth_service import get_current_user
from app.core.db import get_db

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

class AgentRequest(BaseModel):
    """Request model for agent endpoints."""
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        strip_whitespace=True,
        description="The question for the agent to reason about (1–2000 characters).",
    )
    run_id: str | None = None  # optional idempotency key for retries

@router.post("/ask-agent")
async def ask_agent(
    request: AgentRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream agent responses for a question with real-time reasoning visibility.
    
    This endpoint processes a question through a multi-step reasoning agent that can:
    1. Think about the question and devise strategy
    2. Execute SQL queries to retrieve structured data
    3. Retrieve relevant documents from the knowledge base
    4. Synthesize a final answer from gathered information
    
    The response is streamed as Server-Sent Events (SSE) for real-time updates.
    Automatically logs agent executions, costs, and metrics to:
    - Database (runs and costs) for analytics
    - Prometheus for monitoring and alerting
    
    Args:
        request: AgentRequest object containing the user question
        current_user: Authenticated user from dependency injection
        db: Database session for persistence
        
    Yields:
        Server-Sent Events (SSE) with event types:
        - tool_start: Indicates a tool (thinking/SQL/retrieval) is starting
        - thought: Agent's reasoning about what to do next
        - tool_end: Indicates a tool execution has completed
        - answer: The final synthesized answer
        - complete: Marks successful completion
        - error: Error events if something fails
        
    Returns:
        StreamingResponse: SSE stream of agent reasoning and responses
    """
    
    async def event_generator():
        """
        Generator that yields SSE events as agent processes the question.
        
        Tracks execution metrics including:
        - Reasoning steps taken
        - Execution latency
        - Token consumption
        - Database and API calls
        
        Logs metrics to Prometheus and database after completion.
        """
        start_time = time.time()
        final_result = None
        step_count = 0
        input_tokens = 0
        output_tokens = 0
        degraded = False
        degraded_reason = None
        
        inputs = create_initial_state(request.question, current_user.tenant_id, run_id=request.run_id)
        if request.run_id:
            cached = get_cached_run_result(request.run_id)
            if cached:
                logger.info("Returning cached agent result for run_id=%s", request.run_id)
                if cached.get("final_answer"):
                    yield f"data: {json.dumps({'type': 'answer', 'content': cached['final_answer']})}\n\n"
                    yield f"data: {json.dumps({'type': 'complete', 'final_answer': cached['final_answer'], 'degraded': cached.get('degraded', False), 'degraded_reason': cached.get('degraded_reason')})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'status': 'success', 'degraded': cached.get('degraded', False), 'degraded_reason': cached.get('degraded_reason')})}\n\n"
                return

        try:
            # Stream events from the agent graph execution
            # The agent processes the question through multiple reasoning steps
            async for event in agent_app.astream_events(inputs, version="v2"):
                event_type = event.get("event", "")
                event_name = event.get("name", "")
                
                # Send tool start notifications
                if event_type == "on_chain_start":
                    if event_name == "thought":
                        # Agent is thinking about next steps
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': 'Thinking', 'name': event_name})}\n\n"
                    elif event_name == "sql_tool":
                        # Agent is executing SQL query
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': 'SQL Query', 'name': event_name})}\n\n"
                    elif event_name == "retrieval_tool":
                        # Agent is retrieving documents
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': 'Document Retrieval', 'name': event_name})}\n\n"
                
                # Handle tool execution results
                elif event_type == "on_chain_end":
                    data = event.get("data", {})
                    output = data.get("output", {})
                    if isinstance(output, dict):
                        if output.get("degraded"):
                            degraded = True
                            if output.get("degraded_reason"):
                                degraded_reason = output.get("degraded_reason")
                    
                    # Stream thought content from thinking node
                    if event_name == "think" and "thought" in output:
                        thought_content = output.get("thought", "")
                        if thought_content:
                            yield f"data: {json.dumps({'type': 'thought', 'content': thought_content})}\n\n"
                    
                    # Stream final answer from finish node
                    elif event_name == "finish" and "final_answer" in output:
                        final_answer = output.get("final_answer", "")
                        if final_answer:
                            yield f"data: {json.dumps({'type': 'answer', 'content': final_answer})}\n\n"
                            yield f"data: {json.dumps({'type': 'complete', 'final_answer': final_answer, 'degraded': degraded, 'degraded_reason': degraded_reason})}\n\n"
                            # Capture result for post-execution logging
                            final_result = output
                            step_count = output.get("step_count", 0)
                    
                    # Send tool completion notifications
                    elif event_name in ["sql_tool", "retrieval_tool", "think"]:
                        node_display = {
                            "sql_tool": "SQL Query",
                            "retrieval_tool": "Document Retrieval", 
                            "think": "Thinking"
                        }.get(event_name, event_name)
                        yield f"data: {json.dumps({'type': 'tool_end', 'tool': node_display})}\n\n"
            
            # Signal successful completion
            yield f"data: {json.dumps({'type': 'done', 'status': 'success', 'degraded': degraded, 'degraded_reason': degraded_reason})}\n\n"
            
            # Calculate total execution time
            latency = time.time() - start_time
            logger.info(
                f"Agent execution completed - Tenant: {current_user.tenant_id}, "
                f"Steps: {step_count}, Latency: {latency:.2f}s"
            )
            
            # Extract token usage from the model (will represent the last generation step)
            from app.services.llm_runner import CustomLocalLLM
            usage = getattr(CustomLocalLLM, 'last_usage', {}) or {}
            input_tokens = usage.get("input", 0)
            output_tokens = usage.get("output", 0)
            
            # Log the agent run asynchronously to database and Prometheus
            if final_result:
                try:
                    sql_queries = final_result.get("last_sql", "")
                    retrieved_docs = final_result.get("retrieval_context", "")
                    total_cost = final_result.get("total_cost", 0.0)
                    
                    # Record metrics directly to Prometheus (immediate)
                    from app.core.monitors import (
                        agent_queries_total,
                        agent_reasoning_steps_total,
                        agent_reasoning_duration_seconds,
                        agent_reasoning_steps_count,
                        llm_tokens_consumed,
                        llm_tokens_generated,
                        api_calls_cost_total
                    )
                    agent_queries_total.labels(
                        tenant_id=current_user.tenant_id,
                        agent_type="reasoning"
                    ).inc()
                    agent_reasoning_steps_total.labels(
                        tenant_id=current_user.tenant_id,
                        agent_type="reasoning"
                    ).inc(step_count)
                    agent_reasoning_duration_seconds.labels(agent_type="reasoning").observe(latency)
                    agent_reasoning_steps_count.observe(step_count)
                    llm_tokens_consumed.labels(
                        tenant_id=current_user.tenant_id,
                        model_name="Qwen2.5-1.5B"
                    ).inc(input_tokens + output_tokens)
                    llm_tokens_generated.labels(
                        tenant_id=current_user.tenant_id,
                        model_name="Qwen2.5-1.5B"
                    ).inc(output_tokens)
                    api_calls_cost_total.labels(
                        tenant_id=current_user.tenant_id,
                        service="llm"
                    ).inc(float(total_cost))
                    
                    # Trigger background logging task
                    # This will record metrics to both database and Prometheus
                    trigger_agent_logging(
                        tenant_id=current_user.tenant_id,
                        question=request.question,
                        final_answer=final_result.get("final_answer", ""),
                        latency=latency,
                        step_count=step_count,
                        total_cost=float(total_cost),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        sql_queries=sql_queries if sql_queries else "",
                        retrieved_docs=retrieved_docs[:200] if retrieved_docs else "",
                        model_name="Qwen2.5-1.5B"
                    )
                    logger.debug(f"Triggered logging for agent run - Latency: {latency:.2f}s")

                    if request.run_id:
                        cache_response = {
                            "success": True,
                            "run_id": request.run_id,
                            "question": request.question,
                            "final_answer": final_result.get("final_answer"),
                            "thoughts": final_result.get("thoughts", []),
                            "step_count": step_count,
                            "total_cost": float(total_cost),
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "sql_queries": [sql_queries] if sql_queries else [],
                            "retrieved_context": retrieved_docs,
                            "degraded": degraded,
                            "degraded_reason": degraded_reason,
                        }
                        cache_run_result(request.run_id, cache_response)
                except Exception as log_error:
                    logger.error(f"Error triggering agent logging: {log_error}")
            
        except Exception as e:
            logger.error(f"Error during agent execution: {str(e)}", exc_info=True)
            # Send error event to client
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/ask-agent-batch")
async def ask_agent_batch(
    request: AgentRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Non-streaming agent endpoint that returns the complete response at once.
    
    This endpoint processes a question through the same multi-step reasoning agent
    as the streaming endpoint (/ask-agent), but returns the entire response
    in a single JSON response instead of streaming SSE events.
    
    Use this endpoint when:
    - You want to wait for the complete answer before processing
    - You don't need real-time visibility into reasoning steps
    - You prefer simpler JSON response handling on the client
    
    Automatically logs agent executions, costs, and metrics to:
    - Database (runs and costs) for analytics
    - Prometheus for monitoring and alerting
    
    Args:
        request: AgentRequest object containing the user question
        current_user: Authenticated user from dependency injection
        db: Database session for persistence
        
    Returns:
        dict: Complete agent response including:
            - success: Boolean indicating successful execution
            - question: Original user question
            - final_answer: Synthesized final answer
            - thoughts: List of agent reasoning steps
            - step_count: Number of reasoning steps taken
            - total_cost: Total cost of execution
            - sql_queries: List of SQL queries executed
            - retrieved_context: Documents/context retrieved
            - error: Error message if unsuccessful
    """
    start_time = time.time()
    
    inputs = create_initial_state(request.question, current_user.tenant_id)
    if request.run_id:
        inputs["run_id"] = request.run_id
        cached = get_cached_run_result(request.run_id)
        if cached:
            logger.info("Returning cached agent result for run_id=%s", request.run_id)
            return cached
    
    try:
        # Execute the agent graph and wait for completion
        result = await agent_app.ainvoke(inputs)
        
        # Calculate total execution time
        latency = time.time() - start_time
        step_count = result.get("step_count", 0)
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        llm_cost = result.get("llm_cost_usd", 0.0)
        
        logger.info(
            f"Agent batch execution completed - Tenant: {current_user.tenant_id}, "
            f"Steps: {step_count}, Latency: {latency:.2f}s, LLM cost: ${llm_cost:.4f}"
        )
        
        # Log the agent run asynchronously to database and Prometheus
        try:
            sql_queries = result.get("last_sql", "")
            retrieved_docs = result.get("retrieval_context", "")
            total_cost = result.get("total_cost", 0.0)
            
            trigger_agent_logging(
                tenant_id=current_user.tenant_id,
                question=request.question,
                final_answer=result.get("final_answer", ""),
                latency=latency,
                step_count=step_count,
                total_cost=float(total_cost) + float(llm_cost),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                sql_queries=sql_queries if sql_queries else "",
                retrieved_docs=retrieved_docs[:200] if retrieved_docs else "",
                model_name="llama-3.3-70b-versatile"
            )
            agent_executions_total.labels(
                tenant_id=str(current_user.tenant_id),
                status="success",
            ).inc()
            logger.debug(f"Triggered logging for agent batch run - Latency: {latency:.2f}s")
        except Exception as log_error:
            logger.error(f"Error triggering agent logging: {log_error}")
        
        response = {
            "success": True,
            "run_id": result.get("run_id"),
            "question": request.question,
            "final_answer": result.get("final_answer"),
            "thoughts": result.get("thoughts", []),
            "step_count": step_count,
            "total_cost": result.get("total_cost", 0.0),
            "llm_cost_usd": llm_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "sql_queries": [result.get("last_sql")] if result.get("last_sql") else [],
            "retrieved_context": result.get("retrieval_context", ""),
            "degraded": result.get("degraded", False),
            "degraded_reason": result.get("degraded_reason"),
        }
        if request.run_id:
            cache_run_result(request.run_id, response)
        return response
    except Exception as e:
        logger.error(f"Error during agent batch execution: {str(e)}", exc_info=True)
        # Return error response
        return {
            "success": False,
            "error": str(e)
        }
