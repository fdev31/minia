import json
from typing import Any

from minia_llm.llm_client import get_client
from minia_config import config
from minia_llm.model import LlmContext
from minia_llm.serialization import ToolResult, serialize
from minia_utils.logging import get_logger

logger = get_logger(__name__)

THINKING_OPEN = "<think>"
THINKING_CLOSE = "</think>"


def parse_thinking_blocks(text: str) -> tuple[str, str | None]:
    """Parse thinking blocks from text, returning (answer, thinking_content).

    Strips <thinking>...</thinking> tags and returns the clean answer
    along with any extracted thinking content.
    """
    answer_parts: list[str] = []
    thinking_parts: list[str] = []
    pos = 0
    in_thinking = False

    while pos < len(text):
        if not in_thinking:
            idx = text.find(THINKING_OPEN, pos)
            if idx == -1:
                answer_parts.append(text[pos:])
                break
            if idx > pos:
                answer_parts.append(text[pos:idx])
            pos = idx + len(THINKING_OPEN)
            in_thinking = True
        else:
            idx = text.find(THINKING_CLOSE, pos)
            if idx == -1:
                thinking_parts.append(text[pos:])
                break
            thinking_parts.append(text[pos:idx])
            pos = idx + len(THINKING_CLOSE)
            in_thinking = False

    answer = "".join(answer_parts).strip()
    thinking = "".join(thinking_parts) if thinking_parts else None
    return answer, thinking


def format_tool_overflow(
    message: dict[str, Any], content: str, max_size: int
) -> dict[str, Any]:
    """Format a truncated tool result overflow notice.

    Returns a message indicating the tool result was too large,
    with a preview so the LLM can understand the data type and refine its query.
    Uses the configured serialization format.
    """
    preview = content[:1000]
    summarized = dict(message)
    summarized["content"] = serialize(
        ToolResult(
            status="success",
            content=(
                f"Result too large ({len(content)} chars). Showing first 1000 chars:\n\n"
                f"{preview}\n\n"
                f"Try a more specific query to narrow the results."
            ),
            truncated=True,
        ),
        config.llm.tool_format,
    )
    logger.info(
        "[Tool] Result truncated: size=%d > max=%d",
        len(content),
        max_size,
    )
    return summarized


async def summarize_message(
    ctx: LlmContext, message: dict[str, Any], tool_result: bool = False
) -> dict[str, Any]:
    """Summarize a large message via the LLM.

    For other messages, calls the LLM to summarize while preserving key facts.
    Falls back to a heuristic summary if the LLM call fails.

    Tool result overflow is handled by format_tool_overflow() before this function.
    """
    content = message.get("content", "")
    if not content:
        return message

    max_size = config.llm.max_message_size
    if not max_size or len(content) <= max_size:
        return message

    if tool_result:
        return format_tool_overflow(message, content, max_size)

    logger.info(
        "[%s] Summarizing large message: role=%s | size=%d > max=%d",
        ctx.name,
        message.get("role"),
        len(content),
        max_size,
    )

    summary_prompt = config.prompts.SUMMARY_PROMPT + content

    try:
        response = await (await get_client()).chat.completions.create(
            model=ctx.model,
            parallel_tool_calls=config.llm.parallel_tool_calls,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=config.llm.summary_max_tokens,
        )
        summary_text = response.choices[0].message.content or ""
    except Exception:
        logger.warning(
            "[%s] LLM summarization failed, using heuristic fallback",
            ctx.name,
        )
        summary_text = _heuristic_summary(content)
        response = None

    logger.info(
        "[%s] Message summarized: %d -> ~%d chars",
        ctx.name,
        len(content),
        len(summary_text),
    )
    if response and response.usage:
        ctx.total_tokens = response.usage.total_tokens
    summarized = dict(message)
    summarized["content"] = summary_text
    return summarized


async def compact_history(ctx: LlmContext, force: bool = False) -> str | None:
    context_window = config.llm.context_window
    threshold = context_window * config.llm.compaction_threshold

    if not force and ctx.total_tokens < threshold:
        logger.debug(
            "[%s] Skip compaction: tokens=%d < threshold=%d",
            ctx.name,
            ctx.total_tokens,
            threshold,
        )
        return None

    if ctx.total_tokens > context_window:
        logger.warning(
            "[%s] Context exceeds model limit: tokens=%d > max=%d | forcing compaction",
            ctx.name,
            ctx.total_tokens,
            context_window,
        )

    logger.info(
        "[%s] Compacting: tokens=%d | threshold=%d | history_len=%d",
        ctx.name,
        ctx.total_tokens,
        threshold,
        len(ctx.history),
    )

    # 1. Keep system prompt (first message)
    system_prompt = ctx.history[0] if ctx.history else None

    if not system_prompt:
        logger.debug("[%s] No system prompt, skip compaction", ctx.name)
        return None

    # 2. Find last assistant message (if any)
    last_assistant = None
    for msg in reversed(ctx.history):
        if msg.get("role") == "assistant":
            last_assistant = msg
            break

    # 3. Find last 5 user messages (excluding the very last one if it's the current request)
    user_messages = [msg for msg in ctx.history if msg.get("role") == "user"]
    last_5_users = user_messages[-5:] if len(user_messages) >= 5 else user_messages

    # 4. Build the messages to summarize (everything except system, last 5 users, and last assistant)
    preserved_messages = {id(system_prompt)}
    if last_assistant:
        preserved_messages.add(id(last_assistant))
    preserved_ids = {id(msg) for msg in last_5_users}
    preserved_messages.update(preserved_ids)

    messages_to_summarize = [
        msg for msg in ctx.history if id(msg) not in preserved_messages
    ]

    logger.debug(
        "[%s] Split: system=1 | to_summarize=%d | last_5_users=%d | last_assistant=%s",
        ctx.name,
        len(messages_to_summarize),
        len(last_5_users),
        last_assistant is not None,
    )

    if len(messages_to_summarize) < 2:
        logger.debug("[%s] Too few messages to summarize, skip compaction", ctx.name)
        return None

    # Build the prompt for summarization
    summary_content = json.dumps(messages_to_summarize)

    try:
        response = await (await get_client()).chat.completions.create(
            model=ctx.model,
            parallel_tool_calls=config.llm.parallel_tool_calls,
            messages=[
                {
                    "role": "user",
                    "content": config.prompts.SUMMARY_PROMPT + summary_content,
                }
            ],
            max_tokens=config.llm.compaction_max_tokens,
        )
        summary_text = response.choices[0].message.content or ""
    except Exception:
        logger.warning(
            "[%s] LLM compaction failed, using heuristic fallback",
            ctx.name,
        )
        summary_text = _heuristic_summary(json.dumps(messages_to_summarize))
        response = None

    logger.info(
        "[%s] Summary: %s",
        ctx.name,
        summary_text[:300],
    )

    # 5. Rebuild history
    new_history = [system_prompt]
    new_history.append({"role": "user", "content": f"Context summary: {summary_text}"})

    # Add old user messages with explicit "old" marker
    for msg in last_5_users:
        old_msg = dict(msg)
        content = old_msg.get("content", "")
        if content and not content.startswith("[OLD]"):
            old_msg["content"] = f"[OLD] {content}"
        new_history.append(old_msg)

    # Add last assistant message if it exists
    if last_assistant:
        new_history.append(last_assistant)

    ctx.history = new_history
    if response and response.usage:
        ctx.total_tokens = response.usage.total_tokens
    logger.info(
        "[%s] After compaction: history_len=%d | total_tokens=%d",
        ctx.name,
        len(ctx.history),
        ctx.total_tokens,
    )

    _fix_consecutive_assistant_messages(ctx)
    return summary_text


def _fix_consecutive_assistant_messages(ctx: LlmContext) -> None:
    """Remove consecutive assistant messages from the end of history.

    The LLM API requires that the last message is not an assistant message
    if preceded by another assistant message. We replace consecutive assistant
    messages with a single summary message.
    """
    if len(ctx.history) < 3:
        return

    last = ctx.history[-1]
    second_last = ctx.history[-2]

    if last.get("role") == "assistant" and second_last.get("role") == "assistant":
        second_last_content = second_last.get("content", "")
        if second_last_content:
            ctx.history[-2] = {
                "role": "user",
                "content": f"Previous assistant response: {second_last_content[:500]}",
            }
            logger.info(
                "[%s] Fixed consecutive assistant messages by replacing message at index %d",
                ctx.name,
                len(ctx.history) - 2,
            )


def _heuristic_summary(content: str, max_lines: int = 200) -> str:
    """Fallback for content too large for LLM summarization.

    Preserves structure by showing first/last N lines with a truncation notice.
    """
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content
    truncated_count = len(lines) - max_lines
    header = f"[Content truncated: {truncated_count} lines removed]\n"
    first_part = "\n".join(lines[: max_lines // 2])
    last_part = "\n".join(lines[-max_lines // 2 :])
    return (
        header
        + first_part
        + "\n\n... ["
        + str(truncated_count)
        + " lines truncated] ...\n\n"
        + last_part
    )
