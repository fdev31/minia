from minia_protocol import EventType
from .model import LlmContext
from . import response_stream
from . import compaction
from . import token_estimation
from .logger import logger


class Agent:
    def __init__(self, name: str, system_prompt: str, context: LlmContext):
        self.name = name
        self.context = context
        # Copy history to avoid mutating shared context
        self.context.history = [
            {"role": "system", "content": system_prompt},
            *context.history,
        ]
        self.context.total_tokens += token_estimation.estimate_tokens(system_prompt)
        logger.info(
            "[%s] Created agent | model=%s | tools=%d | initial_tokens=%d",
            name,
            context.model,
            len(context.tools_schema),
            context.total_tokens,
        )

    async def run_streaming(self, user_input: str):
        if user_input:
            user_message = {"role": "user", "content": user_input}
            user_message = await compaction.summarize_message(
                self.context, user_message
            )
            self.context.history.append(user_message)
            logger.info(
                "[%s] User input: %s | history_len=%d",
                self.name,
                user_input[:200],
                len(self.context.history),
            )

        async for chunk in response_stream.stream_response(ctx=self.context):
            yield chunk

    async def run(self, user_input: str):
        full_text = ""
        async for chunk in self.run_streaming(user_input):
            if chunk.type in (EventType.TEXT, EventType.FINAL):
                full_text += chunk.content
        return full_text
