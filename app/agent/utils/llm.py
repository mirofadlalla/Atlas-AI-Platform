"""Agent LLM calls with timeout, cost tracking, circuit breaker, and model tiering."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Literal

from langchain_core.callbacks import adispatch_custom_event

from app.agent.core.config import agent_settings
from app.agent.observability.metrics import (
    agent_llm_cost_usd_total,
    agent_llm_tokens_total,
)
from app.agent.utils.circuit_breaker import llm_circuit_breaker
from app.design_pattern.llm_singlton import LLMService

logger = logging.getLogger(__name__)

LLMTier = Literal["routing", "generation"]

# Groq approximate $/1M tokens (llama-3.3-70b); override via env if needed
_DEFAULT_INPUT_COST_PER_M = 0.59
_DEFAULT_OUTPUT_COST_PER_M = 0.79


def _estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    in_cost = (input_tokens / 1_000_000) * agent_settings.llm_input_cost_per_million
    out_cost = (output_tokens / 1_000_000) * agent_settings.llm_output_cost_per_million
    return in_cost + out_cost


def _model_for_tier(tier: LLMTier) -> str:
    if tier == "routing" and agent_settings.llm_routing_model:
        return agent_settings.llm_routing_model
    return agent_settings.llm_generation_model or "llama-3.3-70b-versatile"


def _call_llm_sync(prompt: str, tier: LLMTier) -> dict:
    llm = LLMService()
    model = _model_for_tier(tier)
    return llm.generate(
        prompt,
        system_prompt=agent_settings.llm_system_prompt,
        temperature=agent_settings.llm_temperature,
        max_new_tokens=agent_settings.llm_max_tokens,
        model=model,
    )


def call_agent_llm(
    prompt: str,
    tier: LLMTier = "generation",
    tenant_id: str | None = None,
) -> dict:
    """
    Invoke LLM with timeout, circuit breaker, and usage metrics.
    Returns dict with content, input_tokens, output_tokens, total_tokens, cost_usd.
    """
    tenant_label = tenant_id or "unknown"

    def _invoke() -> dict:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                _call_llm_sync, prompt, tier
            )  # llm call in a separate thread to allow timeout becauze llm call is blocking and can take a long time. We want to enforce a timeout on the call.  # noqa: E501

            try:
                return future.result(timeout=agent_settings.llm_timeout_seconds)
            except FuturesTimeout as exc:
                raise TimeoutError(
                    f"LLM call exceeded {agent_settings.llm_timeout_seconds}s timeout"
                ) from exc

    result = llm_circuit_breaker.call(_invoke)
    input_tokens = int(result.get("input_tokens", 0))
    output_tokens = int(result.get("output_tokens", 0))
    cost_usd = _estimate_cost_usd(input_tokens, output_tokens)

    agent_llm_tokens_total.labels(tenant_id=tenant_label, direction="input").inc(
        input_tokens
    )
    agent_llm_tokens_total.labels(tenant_id=tenant_label, direction="output").inc(
        output_tokens
    )
    agent_llm_cost_usd_total.labels(tenant_id=tenant_label).inc(cost_usd)

    return {
        **result,
        "cost_usd": cost_usd,
    }


async def async_call_agent_llm_stream(
    prompt: str,
    tier: LLMTier = "generation",
    tenant_id: str | None = None,
    event_type: str = "stream_thought_chunk",
) -> dict:
    """
    Asynchronously stream LLM generation, dispatching chunks via adispatch_custom_event
    so the client receives word-by-word / token-by-token streaming in real time.

    Returns dict with content, input_tokens, output_tokens, total_tokens, cost_usd.

    Fixes applied:
    - **Event-loop safety (3.1):** The producer thread is signalled to stop via a
      ``threading.Event`` and the ``ThreadPoolExecutor`` is shut down with
      ``wait=False`` — so a streaming error never stalls the event loop.
    - **Circuit breaker (3.4):** The entire stream is wrapped in
      ``llm_circuit_breaker.async_call`` so provider failures open the breaker and
      back-pressure is applied on the async hot path, not just the sync SQL path.
    """
    tenant_label = tenant_id or "unknown"
    llm = LLMService()
    model = _model_for_tier(tier)

    async def _do_stream() -> dict:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        stop_event = threading.Event()

        def _producer() -> None:
            try:
                for delta, usage in llm.generate_stream(
                    prompt=prompt,
                    system_prompt=agent_settings.llm_system_prompt,
                    max_new_tokens=agent_settings.llm_max_tokens,
                    model=model,
                ):
                    if stop_event.is_set():
                        break
                    if delta is not None:
                        loop.call_soon_threadsafe(q.put_nowait, ("delta", delta))
                    if usage is not None:
                        loop.call_soon_threadsafe(q.put_nowait, ("usage", usage))
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, ("end", None))

        pool = ThreadPoolExecutor(max_workers=1)
        pool.submit(_producer)

        full_content: list[str] = []
        usage_data: dict = {"input": 0, "output": 0}
        _exc: BaseException | None = None

        try:
            while True:
                kind, val = await q.get()
                if kind == "end":
                    break
                elif kind == "delta":
                    full_content.append(val)
                    await adispatch_custom_event(event_type, {"content": val})
                elif kind == "usage":
                    usage_data = val
                elif kind == "error":
                    _exc = val
                    stop_event.set()  # Signal producer to exit its loop early
                    break
        finally:
            # Always signal the producer and release the pool without blocking
            # the event loop. The thread will finish on its own shortly after
            # stop_event is set.
            stop_event.set()
            pool.shutdown(wait=False)

        if _exc is not None:
            raise _exc

        content = "".join(full_content)
        input_tokens = int(
            usage_data.get("input", 0) or usage_data.get("prompt_tokens", 0)
        )
        output_tokens = int(
            usage_data.get("output", 0) or usage_data.get("completion_tokens", 0)
        )
        if input_tokens == 0:
            input_tokens = len(prompt) // 4
        if output_tokens == 0:
            output_tokens = len(content) // 4

        cost_usd = _estimate_cost_usd(input_tokens, output_tokens)

        agent_llm_tokens_total.labels(tenant_id=tenant_label, direction="input").inc(
            input_tokens
        )
        agent_llm_tokens_total.labels(tenant_id=tenant_label, direction="output").inc(
            output_tokens
        )
        agent_llm_cost_usd_total.labels(tenant_id=tenant_label).inc(cost_usd)

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": cost_usd,
        }

    # Wrap with circuit breaker so async LLM failures open the breaker exactly
    # as synchronous failures do in call_agent_llm.
    return await llm_circuit_breaker.async_call(_do_stream)


def llm_usage_updates(result: dict, state: dict) -> dict:
    """Build state delta for token/cost counters from an LLM result."""
    return {
        "input_tokens": state.get("input_tokens", 0)
        + int(result.get("input_tokens", 0)),
        "output_tokens": state.get("output_tokens", 0)
        + int(result.get("output_tokens", 0)),
        "llm_cost_usd": state.get("llm_cost_usd", 0.0)
        + float(result.get("cost_usd", 0.0)),
    }
