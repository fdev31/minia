"""Tests for agent module."""

import pytest
from unittest.mock import patch

from minia.agent import Agent
from minia.model import LlmContext, ChunkType, ResponseData


class TestAgent:
    @pytest.mark.asyncio
    async def test_agent_creation_adds_system_prompt(self):
        """Agent creation prepends system prompt to history."""
        ctx = LlmContext(name="test", model="test-model")
        Agent("test", "You are helpful.", ctx)
        assert ctx.history[0]["role"] == "system"
        assert ctx.history[0]["content"] == "You are helpful."

    @pytest.mark.asyncio
    async def test_agent_creation_does_not_mutate_shared_history(self):
        """Agent creation copies history, not mutating original."""
        original_history = [{"role": "user", "content": "shared"}]
        ctx = LlmContext(name="test", model="test-model", history=original_history)
        Agent("test", "system", ctx)
        # Original history should be unchanged
        assert len(original_history) == 1
        assert original_history[0] == {"role": "user", "content": "shared"}
        # Agent's context should have system prompt prepended
        assert len(ctx.history) == 2
        assert ctx.history[0]["role"] == "system"
        assert ctx.history[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_agent_estimates_system_prompt_tokens(self):
        """Agent creation adds system prompt token count."""
        ctx = LlmContext(name="test", model="test-model", total_tokens=100)
        Agent("test", "Hello world", ctx)
        # Should have added tokens for "Hello world" (approximately 2-8 tokens)
        assert ctx.total_tokens > 100

    @pytest.mark.asyncio
    async def test_run_streaming_yields_chunks(self):
        """Agent.run_streaming yields chunks from response_stream."""
        ctx = LlmContext(name="test", model="test-model")
        agent = Agent("test", "system", ctx)

        async def fake_stream(*args, **kwargs):
            yield ResponseData(type=ChunkType.TEXT, content="hello")
            yield ResponseData(type=ChunkType.FINAL, content="final answer")

        with patch("minia.agent.response_stream.stream_response", fake_stream):
            chunks = []
            async for chunk in agent.run_streaming("hello"):
                chunks.append(chunk)
            assert len(chunks) == 2
            assert chunks[0].type == ChunkType.TEXT
            assert chunks[1].type == ChunkType.FINAL

    @pytest.mark.asyncio
    async def test_run_collects_text_and_final(self):
        """Agent.run collects TEXT and FINAL content."""
        ctx = LlmContext(name="test", model="test-model")
        agent = Agent("test", "system", ctx)

        async def fake_stream(*args, **kwargs):
            yield ResponseData(type=ChunkType.TEXT, content="part1 ")
            yield ResponseData(type=ChunkType.THINKING, content="thinking")
            yield ResponseData(type=ChunkType.FINAL, content="answer")

        with patch("minia.agent.response_stream.stream_response", fake_stream):
            result = await agent.run("hello")
            assert result == "part1 answer"

    @pytest.mark.asyncio
    async def test_run_skips_non_text_chunks(self):
        """Agent.run skips non-TEXT/FINAL chunks."""
        ctx = LlmContext(name="test", model="test-model")
        agent = Agent("test", "system", ctx)

        async def fake_stream(*args, **kwargs):
            yield ResponseData(type=ChunkType.TOOL_CALL_START, content="read_file")
            yield ResponseData(type=ChunkType.TOOL_CALL, content='{"data": "ok"}')
            yield ResponseData(type=ChunkType.FINAL, content="done")

        with patch("minia.agent.response_stream.stream_response", fake_stream):
            result = await agent.run("hello")
            assert result == "done"
