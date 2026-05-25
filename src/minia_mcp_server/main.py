"""Minia MCP Server - Entry point and tool registration.

This module serves as the glue that imports all tool modules,
triggering their @mcp.tool() and @mcp.prompt() decorators,
and provides the CLI entry point.
"""

import logging

from minia_utils.logging import configure_logging
from minia_config import config

from .mcp_instance import mcp
from . import tool_geoloc, tool_pythonproj
from . import tool_web, tool_files, tool_edit, tool_command
from . import prompts  # noqa: F401 - side-effect registration

logger = logging.getLogger(__name__)

# List of all tool modules for potential introspection
_mcp_extensions = [
    tool_geoloc,
    tool_pythonproj,
    tool_web,
    tool_files,
    tool_edit,
    tool_command,
]


def mcp_server_main():
    """Main entry point for the MCP server."""
    configure_logging(
        log_level=getattr(config.default, "log_level", "INFO"), add_console=False
    )
    mcp.run(transport="stdio")
