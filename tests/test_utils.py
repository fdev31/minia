"""Tests for utils module."""

from minia.utils import (
    build_tool_description_list,
    build_system_prompt,
    create_agent,
    create_llm_context,
)
from minia.agent import Agent
from minia.model import LlmContext


class TestBuildToolDescriptionList:
    def test_empty_list(self):
        """Empty list returns empty string."""
        result = build_tool_description_list([])
        assert result == ""

    def test_single_tool(self):
        """Single tool is formatted correctly."""
        result = build_tool_description_list([("read_file", "Read a file")])
        assert result == "- read_file: Read a file"

    def test_multiple_tools(self):
        """Multiple tools are newline-separated."""
        tools = [("read_file", "Read a file"), ("write_file", "Write a file")]
        result = build_tool_description_list(tools)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "- read_file: Read a file"
        assert lines[1] == "- write_file: Write a file"


class TestBuildSystemPrompt:
    def test_basic_formatting(self):
        """Basic template formatting works."""
        template = "Hello {tool_lines}!"
        result = build_system_prompt(template, "world")
        assert result == "Hello world!"

    def test_with_kwargs(self):
        """Additional kwargs are formatted."""
        template = "Tools: {tool_lines}\nExtra: {extra}"
        result = build_system_prompt(template, "tools", extra="value")
        assert "Tools: tools" in result
        assert "Extra: value" in result

    def test_manager_prompt_format(self):
        """Manager prompt template formats correctly."""
        from minia import prompts

        result = build_system_prompt(prompts.MANAGER_PROMPT, "read_file: Read files")
        assert "read_file: Read files" in result


class TestCreateLlmContext:
    def test_minimal(self):
        """Minimal context creation."""
        ctx = create_llm_context(name="test", model="gpt-4")
        assert ctx.name == "test"
        assert ctx.model == "gpt-4"
        assert ctx.server_id is None
        assert ctx.tools_schema == []

    def test_full(self):
        """Full context creation."""
        ctx = create_llm_context(
            name="worker",
            model="gpt-3.5",
            server_id="server-1",
            tools_schema=[{"name": "test"}],
            tool_executor=lambda f, a: "",
        )
        assert ctx.name == "worker"
        assert ctx.server_id == "server-1"
        assert len(ctx.tools_schema) == 1


class TestCreateAgent:
    def test_returns_agent(self):
        """create_agent returns an Agent instance."""
        ctx = LlmContext(name="test", model="gpt-4")
        agent = create_agent("test", "system", ctx)
        assert isinstance(agent, Agent)
        assert agent.name == "test"
