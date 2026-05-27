from minia_mcp_client.mcp_client import McpClient

LOAD_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "load_tool",
        "description": "Load a tool by name and return its schema. Call this once to discover the tool, before usage.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "The name of the tool to load the full schema for (eg: service_name:function_name).",
                }
            },
            "required": ["tool_name"],
        },
    },
}


def build_delegate_task_schema(
    tool_descriptions: list[tuple[str, str]],
    worker_types: list[str] | None = None,
) -> dict:
    """Return the delegate_task tool schema for a manager."""
    enum_values = [name for name, _ in tool_descriptions]
    properties: dict[str, dict] = {
        "worker_type": {
            "type": "string",
            "description": "Worker type to use for this task.",
            "enum": worker_types or ["default"],
        },
        "tool": {
            "type": "string",
            "description": "The tool to use.",
            "enum": enum_values,
        },
        "task_instruction": {
            "type": "string",
            "description": "Clear, standalone instruction for the worker.",
        },
    }
    return {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Delegate a specific task to a specialized worker agent with access to MCP tools.",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": ["task_instruction"],
            },
        },
    }


def build_direct_tool_schemas(mcp_client: McpClient, names: set[str]) -> list[dict]:
    """Return direct-use schemas for a subset of tools with server prefix."""
    tools = []
    for tool_name in names:
        schema = mcp_client.get_tool_schema(tool_name)
        if schema is None:
            continue
        params = schema["function"]["parameters"]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"{mcp_client.server_id}:{tool_name}",
                    "description": schema["function"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": params.get("properties", {}),
                        "required": params.get("required", []),
                    },
                },
            }
        )
    return tools


def build_all_tool_descriptions(mcp_clients: list[McpClient]) -> list[tuple[str, str]]:
    """Build (prefixed_name, description) pairs for all tools from all servers."""
    descriptions: list[tuple[str, str]] = []
    for mcp_client in mcp_clients:
        for name, desc in mcp_client.tool_descriptions:
            descriptions.append((f"{mcp_client.server_id}:{name}", desc))
    return descriptions
