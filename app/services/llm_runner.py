# app/services/llm_runner.py
import logging
from app.design_pattern.llm_singlton import LLMService

logger = logging.getLogger(__name__)

def call_llama(
    prompt: str,
    model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
    # system_prompt: str = "",
    temperature: float = 0.2
):
    """
    Call the Local LLM to generate a response.
    
    Args:
        prompt: The user prompt to send to the model
        model_name: The model to use (note: currently singleton uses a fixed model)
        system_prompt: Optional system prompt for context
        temperature: Temperature for generation (0-1)
    
    Returns:
        dict: Dictionary with keys: 'content' (str), 'input_tokens' (int), 'output_tokens' (int), 'total_tokens' (int)
    """
    try:
        llm = LLMService()
        output = llm.generate(
            prompt,
            # system_prompt=system_prompt,
            temperature=temperature
        )
        # generate() now returns a plain str; token counts are not available via the API
        logger.info("LLM call successful.")
        return output
    except Exception as e:
        print(f"Error calling LLM: {str(e)}")
        logger.error(f"Error calling LLM: {str(e)}", exc_info=True)
        raise



from typing import Any, List, Optional
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

from langchain_core.outputs import GenerationChunk
from typing import Iterator

# transform the call_llama function into a custom LLM class that can be used with LangChain
class CustomLocalLLM(LLM):
    last_usage: dict = {} # مخزن مؤقت لآخر عملية

    def _stream(self, prompt: str, run_manager=None, **kwargs) -> Iterator[GenerationChunk]:
        llm = LLMService()
        for content, usage in llm.generate_stream(prompt):
            if content:
                chunk = GenerationChunk(text=content)
                if run_manager:
                    run_manager.on_llm_new_token(chunk.text)
                yield chunk
            if usage:
                # بنحفظ الأرقام هنا عشان الـ Pipeline يسحبها
                CustomLocalLLM.last_usage = usage

    def _call(self, prompt: str, **kwargs) -> str:
        # Normal Method using invoke
        llm = LLMService()
        res = llm.generate(prompt)  # Removed system_prompt as it's not accepted by generate
        
        # Save usage for pipeline metrics
        CustomLocalLLM.last_usage = {
            "input": res.get("input_tokens", 0),
            "output": res.get("output_tokens", 0)
        }
        
        return res["content"]

    @property
    def _llm_type(self) -> str:
        return "custom_huggingface_stream"