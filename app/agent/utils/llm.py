"""Agent LLM calls with timeout, cost tracking, circuit breaker, and model tiering."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Literal

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
