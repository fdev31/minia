"""Streaming LLM response handler with tool execution and thinking block parsing."""

import asyncio
import hashlib
import json
from typing import Any

from .llm_client import get_client, Error as LLMAPIError
from minia_protocol import EventType
from .model import ResponseData, LlmContext
from . import compaction
from minia_config import config
from .logger import logger

# How often to poll for cancellation signals during tool execution (seconds)
_TOOL_POLL_INTERVAL = 0.1


def _empty_retry_msg(ctx: LlmContext) -> str:
    n = ctx.consecutive_empty
    if n == 1:
        return "Your previous response was empty. Please provide a tool call or text response."
    if n == 2:
        tools = ", ".join(
            t.get("function", {}).get("name", "?") for t in ctx.tools_schema
        )
        return f"Your previous response was empty again. Available tools: {tools}. Please use one or provide a text answer."
    return (
        "Your previous response was empty for the third time. "
        "Consider delegating the task to a worker agent, or explain the situation."
    )


def _tool_loop_detected(ctx: LlmContext, name: str, args: str) -> bool:
    """Return True if the same tool+args has been called >2 times recently."""
    h = hashlib.md5(args.encode()).hexdigest()[:8]
    results = [
        e for e in ctx.history if isinstance(e, dict) and e.get("role") == "tool"
    ][-10:]
    for entry in results:
        tcid = entry.get("tool_call_id")
        if not tcid:
            continue
        for i in range(len(ctx.history) - 1, -1, -1):
            msg = ctx.history[i]
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    if tc.get("id") == tcid:
                        if (
                            tc.get("function", {}).get("name") == name
                            and hashlib.md5(
                                tc.get("function", {}).get("arguments", "").encode()
                            ).hexdigest()[:8]
                            == h
                        ):
                            return True
                break
    return False


def _parse_thinking(
    text: str, in_thinking: bool, buf: str, yield_fn, EventType
) -> tuple[bool, str, str]:
    """Incremental <thinking> tag parser. Returns (in_thinking, thinking_buf, answer_buf)."""
    thinking_buf = ""
    answer_buf = ""
    pos = 0
    while pos < len(text):
        if not in_thinking:
            idx = text.find("<thinking>", pos)
            if idx == -1:
                answer_buf += text[pos:]
                break
            if idx > pos:
                answer_buf += text[pos:idx]
            in_thinking = True
            pos = idx + len("<thinking>")
        else:
            idx = text.find("</thinking>", pos)
            if idx == -1:
                thinking_buf += text[pos:]
                break
            thinking_buf += text[pos:idx]
            if thinking_buf:
                yield_fn(ResponseData(type=EventType.THINKING, content=thinking_buf))
                thinking_buf = ""
            in_thinking = False
            pos = idx + len("</thinking>")
    return in_thinking, thinking_buf, answer_buf


async def _run_tool_with_polling(
    ctx: LlmContext,
    fn: str,
    args: dict,
    poll_interval: float = _TOOL_POLL_INTERVAL,
) -> str:
    """Run a tool executor, polling for cancellation during execution.

    This wraps the tool call in a task and periodically checks if the
    server has requested cancellation (via ctx.cancel_requested). Without
    this, the server would be blocked for the entire duration of the tool
    call when a new message arrives.
    """
    assert ctx.tool_executor is not None
    task: asyncio.Task = asyncio.create_task(ctx.tool_executor(fn, args))  # type: ignore[misc, arg-type, var-annotated]
    while not task.done():
        # Wait for either the task to complete or the poll interval to elapse
        done, _ = await asyncio.wait([task], timeout=poll_interval)
        if done:
            return task.result()
        # Check if cancellation was requested
        if ctx.cancel_requested.is_set():
            logger.info("[%s] Cancelling in-flight tool: %s", ctx.name, fn)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise asyncio.CancelledError("Tool execution cancelled by interrupt")
    return task.result()


async def stream_response(ctx: LlmContext):
    """Async generator yielding ResponseData chunks for one agent turn loop.

    Tool calls are wrapped with polling so the server can interrupt them
    when a new message arrives.
    """
    iteration = 0
    while True:
        iteration += 1
        logger.debug(
            "[%s] Loop #%d | history=%d tokens=%d",
            ctx.name,
            iteration,
            len(ctx.history),
            ctx.total_tokens,
        )

        summary = await compaction.compact_history(ctx)
        if summary:
            yield ResponseData(type=EventType.COMPACTION, content=summary)
        if ctx.total_tokens > config.llm.context_window:
            summary = await compaction.compact_history(ctx, force=True)
            if summary:
                yield ResponseData(type=EventType.COMPACTION, content=summary)

        tools = list(ctx.tools_schema)
        for ts in ctx.unfolded_tools.values():
            if not any(
                t.get("function", {}).get("name") == ts["function"]["name"]
                for t in tools
            ):
                tools.append(ts)

        logger.debug(
            "[%s] API: model=%s msgs=%d tools=%d",
            ctx.name,
            ctx.model,
            len(ctx.history),
            len(tools),
        )

        client = await get_client()
        response = await client.chat.completions.create(
            model=ctx.model,
            parallel_tool_calls=config.llm.parallel_tool_calls,
            messages=ctx.history,
            tools=tools,
            tool_choice="auto",
            stream=True,
            stream_options={"include_usage": True},
        )

        acc_tools: dict[int, dict[str, str]] = {}
        content_parts: list[str] = []
        parse_error = None
        in_thinking, think_buf, answer_buf = False, "", ""

        try:
            async for chunk in response:
                if chunk.usage:
                    ctx.total_tokens = chunk.usage.total_tokens
                    continue
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    in_thinking, think_buf, answer_buf = _parse_thinking(
                        delta.content,
                        in_thinking,
                        think_buf,
                        lambda r: None,
                        EventType.THINKING,
                    )
                    content_parts.append(delta.content)
                    # Accumulate partial text in context so server can flush on interrupt
                    ctx.partial_text += delta.content

                if delta.tool_calls:
                    for td in delta.tool_calls:
                        idx = td.index
                        if idx not in acc_tools:
                            acc_tools[idx] = {"id": td.id or "", "name": "", "args": ""}
                        acc = acc_tools[idx]
                        if td.function:
                            if td.function.name:
                                acc["name"] += td.function.name
                            if td.function.arguments:
                                acc["args"] += td.function.arguments
        except LLMAPIError as e:
            parse_error = str(e)
            logger.warning("[%s] Parse error: %s", ctx.name, parse_error[:200])

        if parse_error:
            ctx.history.append(
                {
                    "role": "user",
                    "content": "Malformed tool call: "
                    + str(parse_error)
                    + ". Respond with a valid tool call or text.",
                }
            )
            yield ResponseData(type=EventType.CHECK, content="")
            continue

        if not acc_tools and not content_parts:
            ctx.consecutive_empty += 1
            if ctx.consecutive_empty >= 3:
                logger.error(
                    "[%s] Breaking after %d empty responses",
                    ctx.name,
                    ctx.consecutive_empty,
                )
                yield ResponseData(
                    type=EventType.CHECK,
                    content="[System] Agent stuck in empty response loop.",
                )
                return
            ctx.history.append({"role": "user", "content": _empty_retry_msg(ctx)})
            yield ResponseData(type=EventType.CHECK, content="")
            continue

        ctx.consecutive_empty = 0

        # Flush remaining buffers
        if in_thinking and think_buf:
            yield ResponseData(type=EventType.THINKING, content=think_buf)
        if answer_buf:
            yield ResponseData(type=EventType.TEXT, content=answer_buf)

        # Deduplicate tool calls within this response (same name+args)
        seen: set[tuple[str, str]] = set()
        deduped: dict[int, dict[str, str]] = {}
        duplicates: list[dict[str, str]] = []
        for idx in sorted(acc_tools.keys()):
            acc = acc_tools[idx]
            key = (acc["name"], acc["args"])
            if key in seen:
                duplicates.append(acc)
            else:
                seen.add(key)
                deduped[idx] = acc
        if duplicates:
            dup_names = [d["name"] for d in duplicates if d["name"]]
            if dup_names:
                logger.warning(
                    "[%s] Dropping duplicate tool call(s): %s",
                    ctx.name,
                    ", ".join(dup_names),
                )
                ctx.history.append(
                    {
                        "role": "user",
                        "content": "You requested the same tool call multiple times with identical arguments. Please focus on the plan and avoid repetitions.",
                    }
                )
        acc_tools = deduped

        full_msg: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": [],
        }

        # Handle load_tool specially
        load_call = None
        other_calls = []
        for acc in acc_tools.values():
            if acc["name"] == "load_tool":
                load_call = acc
            else:
                other_calls.append(acc)

        if load_call:
            tname = json.loads(load_call["args"]).get("tool_name", "")
            yield ResponseData(
                type=EventType.THINKING,
                content=f"[System] Loading schema for '{tname}'...",
            )
            if ctx.tool_executor:
                await _run_tool_with_polling(
                    ctx, "load_tool", json.loads(load_call["args"])
                )
            else:
                logger.warning("[%s] No executor for load_tool", ctx.name)
            yield ResponseData(
                type=EventType.THINKING, content="[System] Schema loaded. Resending."
            )
            full_msg["tool_calls"].append(
                {
                    "id": load_call["id"],
                    "type": "function",
                    "function": {"name": "load_tool", "arguments": load_call["args"]},
                }
            )
            ctx.history.append(
                {
                    "role": "tool",
                    "tool_call_id": load_call["id"],
                    "content": f"Tool '{tname}' loaded and added to available tools.",
                }
            )
            yield ResponseData(type=EventType.CHECK, content="")
            continue

        tool_results: list[Any] = []
        for acc in other_calls:
            if not acc["name"]:
                continue
            fn = acc["name"]
            logger.info("[%s] tool_start: %s", ctx.name, fn)
            yield ResponseData(
                type=EventType.TOOL_CALL_START,
                content=fn,
                tool_name=fn,
                tool_call_id=acc["id"],
                task_instruction=json.loads(acc["args"]).get("task_instruction")
                if fn == "delegate_task"
                else None,
                tool_schema=ctx.unfolded_tools.get(fn),
            )

            args = json.loads(acc["args"])
            # Wrap tool call with polling so server can interrupt it
            try:
                result = (
                    await _run_tool_with_polling(ctx, fn, args)
                    if ctx.tool_executor
                    else '{"error":"No executor"}'
                )
            except asyncio.CancelledError:
                # Tool was cancelled by interrupt — don't add to history
                logger.info("[%s] Tool %s was cancelled by interrupt", ctx.name, fn)
                # Clear any remaining tool results that haven't been added yet
                tool_results.clear()
                raise
            except Exception as e:
                logger.error("[%s] Tool %s failed: %s", ctx.name, fn, e)
                result = f"Error: {e}"

            yield ResponseData(
                type=EventType.TOOL_CALL,
                content=result,
                tool_name=fn,
                tool_call_id=acc["id"],
            )

            full_msg["tool_calls"].append(
                {
                    "id": acc["id"],
                    "type": "function",
                    "function": {"name": fn, "arguments": acc["args"]},
                }
            )
            tm = {"role": "tool", "tool_call_id": acc["id"], "content": result}
            tm = await compaction.summarize_message(ctx, tm, tool_result=True)
            tool_results.append(tm)

        # Loop detection
        for acc in other_calls:
            if acc.get("function_name") and _tool_loop_detected(
                ctx, acc["name"], acc["args"]
            ):
                logger.warning("[%s] Tool loop: %s", ctx.name, acc["name"])
                ctx.history.append(
                    {
                        "role": "assistant",
                        "content": f"⚠️ Loop detected! Tool '{acc['name']}' called >2 times with same args. Try a different approach.",
                    }
                )
                yield ResponseData(type=EventType.CHECK, content="tool_loop_detected")
                return

        # Append to history
        if full_msg["tool_calls"]:
            if ctx.history and ctx.history[-1]["role"] == "assistant":
                ctx.history.pop()
            ctx.history.append(full_msg)
            ctx.history.extend(tool_results)
        else:
            full_msg = await compaction.summarize_message(ctx, full_msg)
            if full_msg.get("content"):
                ctx.history.append(full_msg)
            elif ctx.history and ctx.history[-1]["role"] == "assistant":
                ctx.history.pop()
                ctx.history.append(full_msg)

        # Clear partial_text after successful flush to history
        ctx.partial_text = ""

        logger.debug(
            "[%s] Post-loop: history=%d tokens=%d",
            ctx.name,
            len(ctx.history),
            ctx.total_tokens,
        )

        if acc_tools:
            yield ResponseData(type=EventType.CHECK, content="")
            continue

        # Final text response
        resp = (full_msg["content"] or "").strip()
        resp, _ = compaction.parse_thinking_blocks(resp)
        if not resp:
            ctx.history.append(
                {
                    "role": "user",
                    "content": "Your response contained only thinking tags. Provide a direct answer or use a tool.",
                }
            )
            yield ResponseData(type=EventType.CHECK, content="")
            continue

        logger.info("[%s] FINAL: %d chars", ctx.name, len(resp))
        yield ResponseData(type=EventType.FINAL, content=resp)
        yield ResponseData(type=EventType.USAGE, content="", tokens=ctx.total_tokens)
        return
