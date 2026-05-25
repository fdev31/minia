"""Tests for model module."""

from minia.model import ChunkType, ResponseData, LlmContext


class TestChunkType:
    def test_all_chunk_types_exist(self):
        """All expected chunk types are defined."""
        assert ChunkType.TEXT.value == "text"
        assert ChunkType.THINKING.value == "thinking"
        assert ChunkType.TOOL_CALL_START.value == "tool_call_start"
        assert ChunkType.TOOL_CALL.value == "tool_call"
        assert ChunkType.FINAL.value == "final"
        assert ChunkType.CHECK.value == "check"


class TestResponseData:
    def test_to_dict_minimal(self):
        """to_dict with minimal fields."""
        data = ResponseData(type=ChunkType.TEXT, content="hello")
        result = data.to_dict()
        assert result["type"] == "text"
        assert result["content"] == "hello"
        assert result["tool_name"] is None
        assert result["tool_call_id"] is None

    def test_to_dict_with_all_fields(self):
        """to_dict with all fields populated."""
        data = ResponseData(
            type=ChunkType.TOOL_CALL,
            content='{"result": "ok"}',
            tool_name="read_file",
            tool_call_id="call_123",
        )
        result = data.to_dict()
        assert result["type"] == "tool_call"
        assert result["tool_name"] == "read_file"
        assert result["tool_call_id"] == "call_123"

    def test_to_dict_with_optional_fields(self):
        """to_dict includes optional fields when set."""
        data = ResponseData(
            type=ChunkType.TOOL_CALL_START,
            content="delegate_task",
            task_instruction="Read the file",
            tool_schema={"type": "function"},
        )
        result = data.to_dict()
        assert result["task_instruction"] == "Read the file"
        assert result["tool_schema"] == {"type": "function"}

    def test_to_dict_excludes_none_optional_fields(self):
        """to_dict excludes None optional fields."""
        data = ResponseData(type=ChunkType.TEXT, content="hello")
        result = data.to_dict()
        assert "task_instruction" not in result
        assert "tool_schema" not in result


class TestLlmContext:
    def test_default_values(self):
        """LlmContext has correct default values."""
        ctx = LlmContext(name="test", model="gpt-4")
        assert ctx.server_id is None
        assert ctx.tools_schema == []
        assert ctx.tool_executor is None
        assert ctx.history == []
        assert ctx.total_tokens == 0
        assert ctx.unfolded_tools == {}

    def test_with_values(self):
        """LlmContext accepts custom values."""
        ctx = LlmContext(
            name="worker",
            model="gpt-3.5",
            server_id="server-1",
            tools_schema=[{"name": "test"}],
        )
        assert ctx.name == "worker"
        assert ctx.model == "gpt-3.5"
        assert ctx.server_id == "server-1"
        assert len(ctx.tools_schema) == 1
