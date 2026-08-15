"""
Agent controller.

Encapsulates the agent graph execution, SSE streaming, batch invocation,
cache management, and post-execution logging / Prometheus metrics.
"""

import json
import logging
import time

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.core.graph import agent_app
from app.agent.observability.metrics import agent_executions_total
from app.agent.utils.run_cache import cache_run_result, get_cached_run_result
from app.agent.utils.state_helpers import create_initial_state
from app.memory.memory_manager import memory_manager
from app.services.rag_services.agent_logging_service import trigger_agent_logging

logger = logging.getLogger(__name__)


class AgentController:
    """Controller for all /agent endpoints."""

    # ── /agent/ask-agent (streaming SSE) ──────────────────────────────────────

    @staticmethod
    def ask_agent_stream(request, current_user, db: Session) -> StreamingResponse:
        """
        Return a StreamingResponse of SSE events from the agent graph.

        The generator streams tool_start / thought / tool_end / answer / complete
        / done / error events, then logs metrics after completion.
        """

        async def event_generator():
            start_time = time.time()
            final_result = None
            step_count = 0
            input_tokens = 0
            output_tokens = 0
            degraded = False
            degraded_reason = None

            inputs = create_initial_state(
                request.question,
                current_user.tenant_id,
                run_id=request.run_id,
                user_id=current_user.id,
                session_id=request.session_id,
            )

            # Parallel non-blocking fast memory loading (Short-Term + Cached Semantic)
            fast_context = await memory_manager.load_fast_context(
                str(current_user.tenant_id),
                str(current_user.id),
                request.session_id,
                request.question,
            )
            inputs.update(fast_context)

            # Cache hit — skip graph execution
            if request.run_id:
                cached = get_cached_run_result(request.run_id)
                if cached:
                    logger.info(
                        "Returning cached agent result for run_id=%s", request.run_id
                    )
                    if cached.get("final_answer"):
                        yield f"data: {json.dumps({'type': 'answer', 'content': cached['final_answer']})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete', 'final_answer': cached['final_answer'], 'degraded': cached.get('degraded', False), 'degraded_reason': cached.get('degraded_reason')})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'status': 'success', 'degraded': cached.get('degraded', False), 'degraded_reason': cached.get('degraded_reason')})}\n\n"
                    return

            try:
                node_display_names = {
                    "fast_router": "Hybrid Router",
                    "memory_loader": "Memory Loader",
                    "memory_read": "Short-Term Memory",
                    "episodic_recall": "Episodic Memory",
                    "semantic_recall": "Semantic Memory",
                    "direct_answer": "Direct Answer",
                    "decompose": "Question Decomposition",
                    "think": "Thinking",
                    "sql_tool": "SQL Query",
                    "retrieval_tool": "Document Retrieval",
                    "finish": "Answer Synthesis",
                    "memory_write": "Persisting Memory",
                }

                async for event in agent_app.astream_events(inputs, version="v2"):
                    event_type = event.get("event", "")
                    event_name = event.get("name", "")
                    data = event.get("data", {})

                    # Handle custom real-time streaming events dispatched from graph nodes
                    if event_type == "on_custom_event":
                        if event_name == "stream_node_status":
                            yield f"data: {json.dumps({'type': 'tool_start', 'tool': data.get('tool', 'Node'), 'name': data.get('node', ''), 'message': data.get('message', '')})}\n\n"
                        elif event_name == "stream_thought_chunk":
                            yield f"data: {json.dumps({'type': 'thought', 'content': data.get('content', '')})}\n\n"
                        elif event_name == "stream_answer_chunk":
                            yield f"data: {json.dumps({'type': 'answer', 'content': data.get('content', '')})}\n\n"

                    elif event_type == "on_chain_start":
                        if event_name in node_display_names:
                            display = node_display_names[event_name]
                            yield f"data: {json.dumps({'type': 'tool_start', 'tool': display, 'name': event_name})}\n\n"

                    elif event_type == "on_chain_end":
                        output = data.get("output", {})
                        if isinstance(output, dict):
                            if output.get("degraded"):
                                degraded = True
                                if output.get("degraded_reason"):
                                    degraded_reason = output.get("degraded_reason")

                        if event_name in node_display_names:
                            display = node_display_names[event_name]
                            yield f"data: {json.dumps({'type': 'tool_end', 'tool': display, 'name': event_name})}\n\n"

                        if event_name in ("finish", "direct_answer") and isinstance(
                            output, dict
                        ):
                            final_answer = output.get("final_answer", "")
                            if final_answer:
                                yield f"data: {json.dumps({'type': 'answer', 'content': final_answer})}\n\n"
                            yield f"data: {json.dumps({'type': 'complete', 'final_answer': final_answer, 'degraded': degraded, 'degraded_reason': degraded_reason})}\n\n"
                            final_result = output
                            step_count = output.get("step_count", 0)

                yield f"data: {json.dumps({'type': 'done', 'status': 'success', 'degraded': degraded, 'degraded_reason': degraded_reason})}\n\n"

                latency = time.time() - start_time
                logger.info(
                    f"Agent execution completed - Tenant: {current_user.tenant_id}, "
                    f"Steps: {step_count}, Latency: {latency:.2f}s"
                )

                from app.services.llm_runner import CustomLocalLLM

                usage = getattr(CustomLocalLLM, "last_usage", {}) or {}
                input_tokens = usage.get("input", 0)
                output_tokens = usage.get("output", 0)

                if final_result:
                    try:
                        sql_queries = final_result.get("last_sql", "")
                        retrieved_docs = final_result.get("retrieval_context", "")
                        total_cost = final_result.get("total_cost", 0.0)

                        from app.core.monitors import (
                            agent_queries_total,
                            agent_reasoning_steps_total,
                            agent_reasoning_duration_seconds,
                            agent_reasoning_steps_count,
                            llm_tokens_consumed,
                            llm_tokens_generated,
                            api_calls_cost_total,
                        )

                        agent_queries_total.labels(
                            tenant_id=current_user.tenant_id, agent_type="reasoning"
                        ).inc()
                        agent_reasoning_steps_total.labels(
                            tenant_id=current_user.tenant_id, agent_type="reasoning"
                        ).inc(step_count)
                        agent_reasoning_duration_seconds.labels(
                            agent_type="reasoning"
                        ).observe(latency)
                        agent_reasoning_steps_count.observe(step_count)
                        llm_tokens_consumed.labels(
                            tenant_id=current_user.tenant_id, model_name="Qwen2.5-1.5B"
                        ).inc(input_tokens + output_tokens)
                        llm_tokens_generated.labels(
                            tenant_id=current_user.tenant_id, model_name="Qwen2.5-1.5B"
                        ).inc(output_tokens)
                        api_calls_cost_total.labels(
                            tenant_id=current_user.tenant_id, service="llm"
                        ).inc(float(total_cost))

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
                            retrieved_docs=(
                                retrieved_docs[:200] if retrieved_docs else ""
                            ),
                            model_name="Qwen2.5-1.5B",
                        )
                        logger.debug(
                            f"Triggered logging for agent run - Latency: {latency:.2f}s"
                        )

                        if request.run_id:
                            cache_run_result(
                                request.run_id,
                                {
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
                                },
                            )
                    except Exception as log_error:
                        logger.error(f"Error triggering agent logging: {log_error}")

            except Exception as e:
                logger.error(f"Error during agent execution: {str(e)}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # ── /agent/ask-agent-batch ────────────────────────────────────────────────

    @staticmethod
    async def ask_agent_batch(request, current_user, db: Session) -> dict:
        """Execute the agent graph synchronously and return a complete JSON response."""
        start_time = time.time()

        inputs = create_initial_state(
            request.question,
            current_user.tenant_id,
            user_id=current_user.id,
            session_id=request.session_id,
        )
        if request.run_id:
            inputs["run_id"] = request.run_id
            cached = get_cached_run_result(request.run_id)
            if cached:
                logger.info(
                    "Returning cached agent result for run_id=%s", request.run_id
                )
                return cached

        try:
            result = await agent_app.ainvoke(inputs)

            latency = time.time() - start_time
            step_count = result.get("step_count", 0)
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
            llm_cost = result.get("llm_cost_usd", 0.0)

            logger.info(
                f"Agent batch execution completed - Tenant: {current_user.tenant_id}, "
                f"Steps: {step_count}, Latency: {latency:.2f}s, LLM cost: ${llm_cost:.4f}"
            )

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
                    model_name="llama-3.3-70b-versatile",
                )
                agent_executions_total.labels(
                    tenant_id=str(current_user.tenant_id), status="success"
                ).inc()
                logger.debug(
                    f"Triggered logging for agent batch run - Latency: {latency:.2f}s"
                )
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
                "sql_queries": (
                    [result.get("last_sql")] if result.get("last_sql") else []
                ),
                "retrieved_context": result.get("retrieval_context", ""),
                "degraded": result.get("degraded", False),
                "degraded_reason": result.get("degraded_reason"),
            }
            if request.run_id:
                cache_run_result(request.run_id, response)
            return response

        except Exception as e:
            logger.error(f"Error during agent batch execution: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
