"""Tests for llm_client module."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from minia.llm_client import get_client, ConnectionError, TimeoutError, Error


class TestGetClient:
    @pytest.mark.asyncio
    async def test_returns_client_instance(self):
        """get_client returns an AsyncOpenAI instance."""
        with patch("minia.llm_client.AsyncOpenAI") as mock_openai:
            mock_instance = AsyncMock()
            mock_openai.return_value = mock_instance

            client = await get_client()
            assert client is mock_instance
            mock_openai.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        """get_client returns the same instance on subsequent calls."""
        with patch("minia.llm_client.AsyncOpenAI") as mock_openai:
            mock_instance = AsyncMock()
            mock_openai.return_value = mock_instance

            client1 = await get_client()
            client2 = await get_client()
            assert client1 is client2

    @pytest.mark.asyncio
    async def test_uses_config_values(self):
        """get_client uses config for base_url and api_key."""
        import minia.llm_client as llm_client

        llm_client._instance = None  # reset singleton

        with patch.object(llm_client, "AsyncOpenAI") as mock_openai:
            mock_instance = AsyncMock()
            mock_openai.return_value = mock_instance

            await get_client()
            mock_openai.assert_called_once()
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["base_url"] == "http://localhost:8080/v1"
            assert call_kwargs["api_key"] == "sk-no-key-required"

    @pytest.mark.asyncio
    async def test_concurrent_calls_use_lock(self):
        """Concurrent get_client calls are serialized by the lock."""
        with patch("minia.llm_client.AsyncOpenAI") as mock_openai:
            mock_instance = AsyncMock()
            mock_openai.return_value = mock_instance

            # Reset the singleton to test concurrent creation
            import minia.llm_client as llm_client

            llm_client._instance = None

            # Run multiple concurrent calls
            results = await asyncio.gather(
                get_client(),
                get_client(),
                get_client(),
            )
            # All should return the same instance
            assert all(r is results[0] for r in results)

    @pytest.mark.asyncio
    async def test_error_aliases(self):
        """Error aliases are properly set."""
        from openai import APIConnectionError, APITimeoutError, APIError

        assert ConnectionError is APIConnectionError
        assert TimeoutError is APITimeoutError
        assert Error is APIError
