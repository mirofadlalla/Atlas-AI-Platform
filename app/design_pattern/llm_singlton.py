"""
LLM Singleton — uses Groq (llama-3.3-70b-versatile) for all generation.

Priority:
  1. Groq cloud API (primary — fast, reliable)
  Falls back on: configured via GROQ_API_KEY in settings / .env
"""

import logging
import os

from groq import Groq

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    _instance = None

    def __new__(cls):
        if (
            cls._instance is None
            or not hasattr(cls._instance, "client")
            or cls._instance.client is None
        ):
            logger.info("Initializing Groq LLM client (llama-3.3-70b-versatile)...")
            api_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "")
            instance = super().__new__(cls)
            instance.client = Groq(api_key=api_key)
            instance.model = "llama-3.3-70b-versatile"
            cls._instance = instance
        return cls._instance

    def generate(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        max_new_tokens: int = 2048,
        temperature: float = 1.0,
        model: str | None = None,
    ) -> dict:
        """
        Non-streaming generation. Returns content + token usage.
        """
        completion = self.client.chat.completions.create(
            model=model or self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_completion_tokens=max_new_tokens,
            top_p=1,
            stream=False,
            stop=None,
        )
        return {
            "content": completion.choices[0].message.content,
            "input_tokens": completion.usage.prompt_tokens,
            "output_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        }

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        max_new_tokens: int = 2048,
        model: str | None = None,
    ):
        """
        Streaming generation. Yields (content_chunk, None) for text chunks
        and (None, usage_dict) as a final item once usage is available.

        Groq streams usage in the final chunk via x_groq.usage.
        """
        stream = self.client.chat.completions.create(
            model=model or self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
            max_completion_tokens=max_new_tokens,
            top_p=1,
            stream=True,
            stop=None,
        )

        usage_data = {"input": 0, "output": 0}
        for chunk in stream:
            # Yield text delta
            delta_content = chunk.choices[0].delta.content if chunk.choices else None
            if delta_content:
                yield delta_content, None

            # Groq sends usage in the last chunk via x_groq field
            if (
                hasattr(chunk, "x_groq")
                and chunk.x_groq
                and hasattr(chunk.x_groq, "usage")
            ):
                u = chunk.x_groq.usage
                usage_data["input"] = getattr(u, "prompt_tokens", 0)
                usage_data["output"] = getattr(u, "completion_tokens", 0)

        # Always yield usage at the end
        yield None, usage_data
