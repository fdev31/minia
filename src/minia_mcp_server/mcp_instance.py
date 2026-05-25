from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]


class ToolError(Exception):
    """Raised by MCP tools when an operation fails.

    Unlike generic exceptions, these carry a user-facing error message
    that the MCP framework will surface as a tool error (isError=True),
    so the LLM receives <status>error</status> in the XML result.
    """


mcp = FastMCP("MiniaTools", json_response=True)
