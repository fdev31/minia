"""Command execution MCP tool."""

import os
import shlex
import subprocess

from .mcp_instance import mcp, ToolError
from .utils import is_safe_path


@mcp.tool()
def execute_command(command: str, cwd: str = "") -> str:
    """Execute a shell command"""
    if not cwd:
        cwd = os.getcwd()
    elif cwd and not is_safe_path(cwd):
        raise ToolError("Access denied for working directory.")

    result = subprocess.run(
        shlex.split(command), cwd=cwd, capture_output=True, text=True, timeout=30
    )
    return result.stdout if result.returncode == 0 else result.stderr
