"""Tests for compaction module."""

import asyncio

from minia.compaction import (
    _heuristic_summary,
    _fix_consecutive_assistant_messages,
    format_tool_overflow,
    parse_thinking_blocks,
    summarize_message,
)
from minia.model import LlmContext


class TestParseThinkingBlocks:
    def test_no_thinking_tags(self):
        """Text without thinking tags returns empty thinking."""
        answer, thinking = parse_thinking_blocks("Hello world")
        assert answer == "Hello world"
        assert thinking is None

    def test_with_thinking_tags(self):
        """Text with thinking tags extracts both parts."""
        text = "<think>Let me think...</think>Hello world"
        answer, thinking = parse_thinking_blocks(text)
        assert answer == "Hello world"
        assert thinking == "Let me think..."

    def test_thinking_only(self):
        """Text with only thinking tags returns empty answer."""
        text = "<think>Thinking content..."
        answer, thinking = parse_thinking_blocks(text)
        assert answer == ""
        assert thinking == "Thinking content..."

    def test_multiple_thinking_blocks(self):
        """Multiple thinking blocks are handled."""
        text = "<think>First...</think>Middle<think>Second...</think>Final"
        answer, thinking = parse_thinking_blocks(text)
        assert "Middle" in answer
        assert "Final" in answer

    def test_unclosed_thinking_tag(self):
        """Unclosed thinking tag puts remainder in thinking."""
        text = "start<think>unclosed"
        answer, thinking = parse_thinking_blocks(text)
        assert answer == "start"
        assert thinking == "unclosed"

    def test_trailing_thinking_close_without_open(self):
        """Trailing closing tag without open tag is kept as text."""
        text = "content</think>"
        answer, thinking = parse_thinking_blocks(text)
        assert answer == "content</think>"
        assert thinking is None


class TestHeuristicSummary:
    def test_short_content_unchanged(self):
        """Short content is returned as-is."""
        content = "line1\nline2\nline3"
        result = _heuristic_summary(content)
        assert result == content

    def test_long_content_truncated(self):
        """Long content is truncated with notice."""
        lines = "\n".join(f"line{i}" for i in range(300))
        result = _heuristic_summary(lines)
        assert "truncated" in result.lower()
        assert "line0" in result  # first lines preserved
        assert "line299" in result  # last lines preserved

    def test_custom_max_lines(self):
        """Custom max_lines parameter works."""
        lines = "\n".join(f"line{i}" for i in range(50))
        result = _heuristic_summary(lines, max_lines=20)
        assert "truncated" in result.lower()


class TestFixConsecutiveAssistantMessages:
    def test_no_consecutive_assistants(self):
        """No change when no consecutive assistant messages."""
        ctx = LlmContext(
            name="test",
            model="test-model",
            history=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "user", "content": "more"},
            ],
        )
        _fix_consecutive_assistant_messages(ctx)
        assert ctx.history[-1]["role"] == "user"

    def test_consecutive_assistants_replaced(self):
        """Consecutive assistant messages are replaced."""
        ctx = LlmContext(
            name="test",
            model="test-model",
            history=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "first"},
                {"role": "assistant", "content": "second"},
            ],
        )
        _fix_consecutive_assistant_messages(ctx)
        # Second-to-last should be replaced with user message
        assert ctx.history[-2]["role"] == "user"
        assert "Previous assistant response" in ctx.history[-2]["content"]

    def test_history_too_small(self):
        """No change when history has fewer than 3 messages."""
        ctx = LlmContext(
            name="test",
            model="test-model",
            history=[
                {"role": "system", "content": "sys"},
                {"role": "assistant", "content": "hello"},
            ],
        )
        _fix_consecutive_assistant_messages(ctx)
        assert len(ctx.history) == 2

    def test_empty_assistant_content(self):
        """No replacement when assistant content is empty."""
        ctx = LlmContext(
            name="test",
            model="test-model",
            history=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": ""},
                {"role": "assistant", "content": "second"},
            ],
        )
        _fix_consecutive_assistant_messages(ctx)
        # Empty content means no replacement
        assert ctx.history[-2].get("content") == ""


class TestFormatToolOverflow:
    def test_large_content_truncated(self):
        """Large content is truncated with preview and instruction."""
        big_content = "line\n" * 25000  # ~125KB
        message = {"role": "tool", "tool_call_id": "1", "content": big_content}
        result = format_tool_overflow(message, big_content, 100000)
        content = result["content"]
        assert "too large" in content.lower()
        assert "125000" in content
        assert "first 1000 chars" in content.lower()
        assert "truncated" in content.lower()
        assert "more specific query" in content.lower()
        assert "line\nline\nline" in content  # preview contains actual output

    def test_preview_length(self):
        """Preview is limited to 1000 chars."""
        big_content = "x" * 150000
        message = {"role": "tool", "tool_call_id": "1", "content": big_content}
        result = format_tool_overflow(message, big_content, 100000)
        preview_start = result["content"].find("\n\n") + 2
        preview_end = result["content"].rfind("\n\nThe result was truncated")
        preview = result["content"][preview_start:preview_end]
        assert len(preview) <= 1000

    def test_preserves_message_fields(self):
        """Other message fields are preserved."""
        message = {"role": "tool", "tool_call_id": "abc123", "content": "x" * 200000}
        result = format_tool_overflow(message, message["content"], 100000)
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "abc123"


class TestSummarizeMessage:
    def test_small_tool_result_unchanged(self):
        """Small tool result passes through unchanged."""
        ctx = LlmContext(name="test", model="test-model", history=[])
        message = {"role": "tool", "tool_call_id": "1", "content": "small result"}
        result = asyncio.run(summarize_message(ctx, message, tool_result=True))
        assert result["content"] == "small result"

    def test_large_tool_result_delegates_to_overflow_formatter(self):
        """Large tool result delegates to format_tool_overflow."""
        ctx = LlmContext(name="test", model="test-model", history=[])
        big_content = "line\n" * 25000
        message = {"role": "tool", "tool_call_id": "1", "content": big_content}
        result = asyncio.run(summarize_message(ctx, message, tool_result=True))
        content = result["content"]
        assert "too large" in content.lower()
        assert "first 1000 chars" in content.lower()

    def test_large_non_tool_result_uses_llm(self):
        """Non-tool large messages are sent to LLM for summarization."""
        ctx = LlmContext(name="test", model="test-model", history=[])
        big_content = "y" * 200000
        message = {"role": "user", "content": big_content}
        # Should not raise, will try LLM call (which may fail in tests)
        result = asyncio.run(summarize_message(ctx, message, tool_result=False))
        # If LLM call fails, falls back to heuristic summary
        assert len(result["content"]) < len(big_content)
