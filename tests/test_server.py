import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from minia.server import _drain_queue_and_broadcast


@pytest.mark.asyncio
async def test_drain_broadcasts_all_returns_recent_only():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    now = time.monotonic()
    await queue.put((now - 5, "old_msg"))
    await queue.put((now - 1, "recent_msg1"))
    await queue.put((now - 0.5, "recent_msg2"))

    result = await _drain_queue_and_broadcast(queue, broadcast)

    assert result == ["recent_msg1", "recent_msg2"]
    assert queue.empty()
    assert broadcast.broadcast.call_count == 3
    broadcast.broadcast.assert_any_call({"type": "user_input", "content": "old_msg"})
    broadcast.broadcast.assert_any_call(
        {"type": "user_input", "content": "recent_msg1"}
    )
    broadcast.broadcast.assert_any_call(
        {"type": "user_input", "content": "recent_msg2"}
    )


@pytest.mark.asyncio
async def test_drain_all_old_messages():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    now = time.monotonic()
    await queue.put((now - 10, "old1"))
    await queue.put((now - 5, "old2"))

    result = await _drain_queue_and_broadcast(queue, broadcast)

    assert result == []
    assert queue.empty()
    assert broadcast.broadcast.call_count == 2


@pytest.mark.asyncio
async def test_drain_all_recent_messages():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    now = time.monotonic()
    await queue.put((now - 0.1, "recent1"))
    await queue.put((now - 0.05, "recent2"))
    await queue.put((now - 0.01, "recent3"))

    result = await _drain_queue_and_broadcast(queue, broadcast)

    assert result == ["recent1", "recent2", "recent3"]
    assert queue.empty()
    assert broadcast.broadcast.call_count == 3


@pytest.mark.asyncio
async def test_drain_empty_queue():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    result = await _drain_queue_and_broadcast(queue, broadcast)

    assert result == []
    assert broadcast.broadcast.call_count == 0


@pytest.mark.asyncio
async def test_drain_custom_max_age():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    now = time.monotonic()
    await queue.put((now - 3, "too_old"))
    await queue.put((now - 1, "recent"))

    result = await _drain_queue_and_broadcast(queue, broadcast, max_age=2.0)

    assert result == ["recent"]


@pytest.mark.asyncio
async def test_drain_single_message():
    queue = asyncio.Queue()
    broadcast = MagicMock()
    broadcast.broadcast = AsyncMock()

    now = time.monotonic()
    await queue.put((now - 0.1, "only_one"))
    result = await _drain_queue_and_broadcast(queue, broadcast)

    assert result == ["only_one"]
    assert queue.empty()
    assert broadcast.broadcast.call_count == 1
