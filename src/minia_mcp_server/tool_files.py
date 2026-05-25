"""File operation MCP tools: read, write, list, find, create, delete, move, copy, info."""

import os
import shutil

from .mcp_instance import mcp, ToolError
from .utils import (
    GREP_MAX_FILE_SIZE,
    is_safe_path,
    is_binary,
    list_files_filtered,
    read_text,
    walk_files,
)


@mcp.tool()
def touch_file(file_path: str):
    """Create an empty file or update its atime"""
    open(file_path, "a+").close()


@mcp.tool()
def read_file(file_path: str, start_line, line_count=20) -> str:
    """Read lines from a file. Returns content with metadata header."""
    if not os.path.exists(file_path):
        raise ToolError(f"File not found at {file_path}")
    if is_binary(file_path):
        raise ToolError("File is binary and cannot be read as text.")
    if os.path.isdir(file_path):
        raise ToolError("Cannot read a directory, list its content instead")

    content = read_text(file_path)
    all_lines = content.splitlines(keepends=True)
    total_lines = len(all_lines)
    file_size = len(content.encode("utf-8"))

    start_line = int(start_line)
    line_count = int(line_count)

    if start_line > total_lines:
        raise ToolError(f"Offset {start_line} exceeds total lines {total_lines}.")

    shown_lines = all_lines[start_line : start_line + line_count]
    shown_text = "".join(shown_lines)

    size_kb = file_size / 1024
    header = f"--- {file_path} (total {total_lines} lines, {size_kb:.1f}KB) ---\n"

    if start_line + line_count < total_lines:
        header += f"--- showing lines {start_line + 1}-{start_line + line_count} of {total_lines} ---\n"
    elif start_line > 0:
        header += (
            f"--- showing lines {start_line + 1}-{total_lines} of {total_lines} ---\n"
        )

    return header + shown_text


def _is_file_too_large(filepath: str) -> bool:
    """Return True if *filepath* exceeds GREP_MAX_FILE_SIZE."""
    try:
        return os.path.getsize(filepath) > GREP_MAX_FILE_SIZE
    except OSError:
        return False


@mcp.tool()
def grep(
    path: str,
    pattern: str,
    lines_before: int = 0,
    lines_after: int = 0,
    recursive: bool = False,
    include_hidden: bool = False,
    include_gitignored: bool = False,
) -> str:
    """Search for a pattern in files. Returns formatted results or 'No matches found.'

    By default, skips hidden directories (starting with '.'), common build
    artifacts (__pycache__, node_modules, .venv, etc.), and files listed in
    .gitignore.  Use ``include_hidden=True`` and ``include_gitignored=True``
    to override these defaults.
    """
    matches = []
    skipped = []
    if not is_safe_path(path):
        raise ToolError("Access denied.")

    if os.path.isfile(path):
        files_to_search = [path]
    elif os.path.isdir(path):
        files_to_search = list(
            walk_files(
                path,
                include_hidden=include_hidden,
                include_gitignored=include_gitignored,
                recursive=recursive,
            )
        )
    else:
        raise ToolError(f"{path} is not a valid file or directory.")

    for file in files_to_search:
        # Skip files that are too large
        if _is_file_too_large(file):
            skipped.append(
                f"Skipped {file}: exceeds {GREP_MAX_FILE_SIZE // 1024 // 1024}MB limit"
            )
            continue

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if pattern in line:
                    start = max(0, i - lines_before)
                    end = min(len(lines), i + lines_after + 1)
                    match_context = "\n".join(lines[start:end])
                    matches.append(f"{file}:{i + 1}: {match_context}")
        except Exception as e:
            matches.append(f"Error reading {file}: {str(e)}")

    if not matches and not skipped:
        return "No matches found."

    parts = []
    if matches:
        parts.append(f"Found {len(matches)} match(es):\n\n" + "\n".join(matches))
    if skipped:
        parts.append("\nSkipped files:\n" + "\n".join(skipped))

    return "\n\n".join(parts)


# @mcp.tool()
# def write_file(file_path: str, content: str, overwrite: bool = True) -> str:
#     """Write to a file"""
#     try:
#         if not is_safe_path(file_path):
#             return "Error: Access denied."
#         mode = "w" if overwrite else "a"
#         with open(file_path, mode, encoding="utf-8") as f:
#             f.write(content)
#         return f" {file_path} {'written.' if overwrite else 'appended to.'}"
#     except Exception as e:
#         return f"Error: {str(e)}"


@mcp.tool()
def list_files(
    dir_path: str, recursive: bool = False, include_hidden: bool = False
) -> str:
    """List files in a directory

    By default, skips hidden directories (starting with '.'), common build
    artifacts (__pycache__, node_modules, .venv, etc.), and files listed in
    .gitignore.  Use ``include_hidden=True`` to override these defaults.
    """
    max_files = 40
    if not is_safe_path(dir_path):
        raise ToolError("Access denied.")
    if not os.path.exists(dir_path):
        raise ToolError(f"Directory not found at {dir_path}")
    if not os.path.isdir(dir_path):
        raise ToolError(f"{dir_path} is not a directory.")

    files = []
    if recursive:
        for rel_path in list_files_filtered(dir_path, include_hidden=include_hidden):
            files.append(rel_path)
            if len(files) >= max_files:
                raise ToolError(
                    f"Too many files found. Limit is {max_files}. Consider narrowing your search."
                )

    else:
        files = os.listdir(dir_path)

    return "\n".join(files)


@mcp.tool()
def find_files(
    dir_path: str,
    pattern: str,
    include_hidden: bool = False,
    include_gitignored: bool = False,
) -> str:
    """Find files matching a pattern (e.g., '*.py')

    By default, skips hidden directories (starting with '.'), common build
    artifacts (__pycache__, node_modules, .venv, etc.), and files listed in
    .gitignore.  Use ``include_hidden=True`` and ``include_gitignored=True``
    to override these defaults.
    """
    if not is_safe_path(dir_path):
        raise ToolError("Access denied.")
    matches = list(
        walk_files(
            dir_path,
            pattern=pattern,
            include_hidden=include_hidden,
            include_gitignored=include_gitignored,
        )
    )
    return "\n".join(matches)


@mcp.tool()
def create_directory(dir_path: str, parents: bool = True, exist_ok: bool = True) -> str:
    """Create a directory"""
    if not is_safe_path(dir_path):
        raise ToolError("Access denied.")
    os.makedirs(dir_path, parents, exist_ok)
    return f"Successfully created directory {dir_path}"


@mcp.tool()
def delete_file(file_path: str) -> str:
    """Delete a file"""
    if not is_safe_path(file_path):
        raise ToolError("Access denied.")
    if not os.path.exists(file_path):
        raise ToolError(f"File not found at {file_path}")
    os.remove(file_path)
    return f"Successfully deleted {file_path}"


@mcp.tool()
def move_file(src: str, dst: str) -> str:
    """Move/rename a file"""
    if not is_safe_path(src) or not is_safe_path(dst):
        raise ToolError("Access denied.")
    shutil.move(src, dst)
    return f"Successfully moved {src} to {dst}"


@mcp.tool()
def copy_file(src: str, dst: str) -> str:
    """Copy a file"""
    if not is_safe_path(src) or not is_safe_path(dst):
        raise ToolError("Access denied.")
    shutil.copy2(src, dst)
    return f"Successfully copied {src} to {dst}"


@mcp.tool()
def get_file_info(file_path: str) -> dict:
    """Get file metadata"""
    if not is_safe_path(file_path):
        raise ToolError("Access denied.")
    if not os.path.exists(file_path):
        raise ToolError(f"File not found at {file_path}")

    stat = os.stat(file_path)
    return {
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "created": stat.st_ctime,
        "is_file": os.path.isfile(file_path),
        "is_dir": os.path.isdir(file_path),
        "is_symlink": os.path.islink(file_path),
    }
