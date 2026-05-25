"""Command execution MCP tool."""

import os
import shlex
import subprocess

from .mcp_instance import mcp
from .utils import is_safe_path


@mcp.tool()
def execute_command(command: str, cwd: str = "") -> str:
    """Execute a shell command"""
    try:
        if not cwd:
            cwd = os.getcwd()
        elif cwd and not is_safe_path(cwd):
            return "Error: Access denied for working directory."

        result = subprocess.run(
            shlex.split(command), cwd=cwd, capture_output=True, text=True, timeout=30
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except ValueError:
        return "Error: Invalid command format."
    except Exception as e:
        return f"Error: {str(e)}"
