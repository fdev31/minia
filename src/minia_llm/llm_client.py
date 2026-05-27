import asyncio
import openai
from minia_config import config


def _get_async_openai():
    """Lazily get AsyncOpenAI so patching minia_llm.llm_client.AsyncOpenAI works."""
    import openai

    return openai.AsyncOpenAI


_instance = None
_instance_lock = asyncio.Lock()


async def get_client():
    global _instance
    if _instance is None:
        async with _instance_lock:
            if _instance is None:
                _instance = _get_async_openai()(
                    base_url=config.llm.base_url,
                    api_key=config.llm.api_key,
                )
    return _instance


ConnectionError = openai.APIConnectionError
TimeoutError = openai.APITimeoutError
Error = openai.APIError

# Re-export AsyncOpenAI for patching compatibility
AsyncOpenAI = openai.AsyncOpenAI
