import asyncio
import openai
from openai import AsyncOpenAI
from minia_config import config

_instance: AsyncOpenAI | None = None
_instance_lock = asyncio.Lock()


async def get_client() -> AsyncOpenAI:
    global _instance
    if _instance is None:
        async with _instance_lock:
            if _instance is None:
                _instance = AsyncOpenAI(
                    base_url=config.llm.base_url,
                    api_key=config.llm.api_key,
                )
    return _instance


ConnectionError = openai.APIConnectionError
TimeoutError = openai.APITimeoutError
Error = openai.APIError
