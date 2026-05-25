"""File editing MCP tools: edit_file and edit_file_diff with fuzzy matching."""

import os
from difflib import SequenceMatcher
from typing import Optional

from .mcp_instance import mcp
from .utils import is_binary, is_safe_path, read_text


def _replace_nth(content: str, old: str, new: str, n: int) -> str:
    """Replace the Nth (1-indexed) occurrence of old with new in content."""
    start = 0
    idx = -1
    for i in range(n):
        idx = content.find(old, start)
        if idx == -1:
            raise ValueError(f"occurrence {n} not found (only {i} matches exist)")
        start = idx + len(old)
    # idx is the start of the Nth match
    return content[:idx] + new + content[idx + len(old) :]


@mcp.tool()
def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    occurrence: int = 0,
    replace_all: bool = False,
) -> str:
    """replace content with another in a text file"""
    if old_string == new_string:
        return "Error: old_string and new_string are the same, no changes needed."

    if replace_all and occurrence:
        return (
            "Error: Cannot specify both replace_all and occurrence. Please choose one."
        )

    if not is_safe_path(path):
        return "Error: Access denied."

    content = read_text(str(path))

    count = content.count(old_string)
    if count == 0:
        return "Error: old_string not found in file."

    if replace_all:
        new_content = content.replace(old_string, new_string)
        replaced = count
    elif occurrence:
        try:
            new_content = _replace_nth(content, old_string, new_string, occurrence)
        except ValueError as e:
            return "Error: " + str(e)
        replaced = 1
    else:
        if count > 1:
            return (
                "Error: old_string is not unique in file. Found {} occurrences.".format(
                    count
                )
            )
        new_content = content.replace(old_string, new_string, 1)
        replaced = 1

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    old_lines = old_string.count("\n") + 1
    new_lines = new_string.count("\n") + 1
    if replaced == 1:
        return f"Replaced {old_lines} line(s) with {new_lines} line(s) in {path}."
    return f"Replaced {replaced} occurrences of {old_lines} line(s) with {new_lines} line(s) in {path}."


# ---------------------------------------------------------------------------
# edit_file_diff helpers
# ---------------------------------------------------------------------------


def _normalize_line(line: str) -> str:
    """Normalize a line for fuzzy matching: strip trailing whitespace and collapse internal spaces."""
    return " ".join(line.split())


def _find_fuzzy_match(
    lines: list[str], target: str, tolerance: float = 0.9
) -> Optional[int]:
    """Find a line in the list that fuzzy matches the target.

    Returns the index of the matching line, or None if no match found.
    Uses difflib for fuzzy string matching.
    """
    try:
        best_ratio = 0.0
        best_index = None
        for i, line in enumerate(lines):
            # First try exact normalized match
            if _normalize_line(line) == _normalize_line(target):
                return i

            # Then try fuzzy match
            ratio = SequenceMatcher(None, line, target).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_index = i

        if best_index is not None and best_ratio >= tolerance:
            return best_index
        return None
    except Exception:
        # Fallback to simple normalization if difflib fails
        for i, line in enumerate(lines):
            if _normalize_line(line) == _normalize_line(target):
                return i
        return None


def _apply_hunk(file_lines: list[str], hunk: dict) -> tuple[list[str], bool]:
    """Apply a single diff hunk to the file lines.

    Returns (new_lines, success).

    Hunk structure:
    {
        "context": list of unchanged lines (with or without leading space),
        "deletes": list of lines to remove (with or without leading -),
        "adds": list of lines to add (with or without leading +),
    }
    """
    # Note: _parse_diff already strips prefixes, so use hunk values directly
    match_lines = hunk.get("context", []) + hunk.get("deletes", [])
    add_lines = hunk.get("adds", [])

    if not match_lines and not add_lines:
        return file_lines, True

    # Find the starting position in file_lines
    start_idx = None
    tolerance = 0.9

    # Try to find the first non-empty match line
    first_match_line = None
    for ml in match_lines:
        stripped = ml.strip()
        if stripped:
            first_match_line = ml
            break

    if first_match_line is None:
        # All lines are empty/whitespace - try to find position by context
        for cl in hunk.get("context", []):
            idx = _find_fuzzy_match(file_lines, cl, tolerance=0.8)
            if idx is not None:
                start_idx = idx
                break

    if start_idx is None and first_match_line:
        start_idx = _find_fuzzy_match(file_lines, first_match_line, tolerance)

    if start_idx is None:
        # Pure add hunk (no match lines, only add lines)
        # Insert at the end of the file
        if add_lines:
            new_lines = file_lines + add_lines
            return new_lines, True
        return file_lines, False

    # Now apply the hunk starting from start_idx
    file_idx = start_idx
    match_idx = 0

    # Track which lines are context vs deletes
    context_count = len(hunk.get("context", []))

    for i, ml in enumerate(match_lines):
        if file_idx >= len(file_lines):
            return file_lines, False

        # Check if this line matches (context or delete)
        is_context = i < context_count

        if is_context:
            # Context line - must match
            if _normalize_line(file_lines[file_idx]) != _normalize_line(ml):
                # Try fuzzy match
                fuzzy_idx = _find_fuzzy_match(file_lines[file_idx:], ml, tolerance)
                if fuzzy_idx is not None:
                    file_idx += fuzzy_idx + 1
                else:
                    return file_lines, False
            else:
                file_idx += 1
        else:
            # Delete line - remove it
            if _normalize_line(file_lines[file_idx]) != _normalize_line(ml):
                # Try fuzzy match
                fuzzy_idx = _find_fuzzy_match(file_lines[file_idx:], ml, tolerance)
                if fuzzy_idx is not None:
                    file_idx += fuzzy_idx + 1
                else:
                    return file_lines, False
            file_idx += 1
        match_idx += 1

    # Now insert the added lines (each on its own line)
    added_content = [line + "\n" for line in add_lines] if add_lines else []
    new_lines = file_lines[:start_idx] + added_content + file_lines[file_idx:]
    return new_lines, True


def _parse_diff(diff_text: str) -> list[dict]:
    """Parse a unified diff (without line numbers) into hunks.

    Each hunk is a dict with:
    - "context": list of unchanged lines (with leading space)
    - "deletes": list of lines to remove (with leading -)
    - "adds": list of lines to add (with leading +)
    """
    hunks: list[dict[str, list[str]]] = []
    current_hunk: dict[str, list[str]] = {"context": [], "deletes": [], "adds": []}
    in_hunk = False

    for line in diff_text.splitlines():
        stripped = line.rstrip()

        # Skip hunk headers (with or without line numbers)
        if stripped.startswith("@@") and stripped.endswith("@@"):
            if in_hunk and (
                current_hunk["context"]
                or current_hunk["deletes"]
                or current_hunk["adds"]
            ):
                hunks.append(current_hunk)
            current_hunk = {"context": [], "deletes": [], "adds": []}
            in_hunk = True
            continue

        if not in_hunk:
            continue

        if stripped.startswith("-"):
            current_hunk["deletes"].append(stripped[1:])
        elif stripped.startswith("+"):
            current_hunk["adds"].append(stripped[1:])
        elif stripped.startswith(" "):
            current_hunk["context"].append(stripped[1:])
        elif stripped == "" and in_hunk:
            current_hunk["context"].append("")
        else:
            # Unknown line - could be part of the diff or noise
            # Try to be lenient and include it
            pass

    # Don't forget the last hunk
    if in_hunk and (
        current_hunk["context"] or current_hunk["deletes"] or current_hunk["adds"]
    ):
        hunks.append(current_hunk)

    return hunks


@mcp.tool()
def edit_file_diff(file_path: str, diff: str) -> str:
    """Apply a unified diff to a file with fuzzy matching.

    The diff should be in unified diff format WITHOUT line numbers.
    LLMs should omit the @@ -10,5 +10,6 @@ headers with line numbers
    and just provide the search/replace content.

    Format:
    ```
    @@
    - old line 1
    - old line 2
    + new line 1
    + new line 2
    @@

    @@
    - another old line
    + another new line
    @@
    ```

    Lines starting with ` ` (space) are context (unchanged).
    Lines starting with `-` are removed.
    Lines starting with `+` are added.

    Fuzzy matching is used so minor typos won't cause failures.
    """
    if not is_safe_path(file_path):
        return "Error: Access denied."

    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    if is_binary(file_path):
        return "Error: File is binary and cannot be edited with diff."

    try:
        # Read the file
        content = read_text(file_path)
        file_lines = content.splitlines(keepends=True)
        # Remove trailing newline for processing, add it back later
        has_trailing_newline = content.endswith("\n") if content else False
        if has_trailing_newline and file_lines:
            file_lines[-1] = file_lines[-1].rstrip("\n")

        # Parse the diff
        hunks = _parse_diff(diff)

        if not hunks:
            return "Error: No valid hunks found in diff. Make sure each hunk starts and ends with @@."

        # Apply each hunk sequentially
        new_lines = file_lines
        applied_count = 0
        failed_hunks = []

        for i, hunk in enumerate(hunks):
            new_lines, success = _apply_hunk(new_lines, hunk)
            if success:
                applied_count += 1
            else:
                failed_hunks.append(i)

        if not applied_count:
            return (
                "Error: Failed to apply any hunks. The diff content doesn't match "
                "the file. Try providing more context lines or check for typos."
            )

        if failed_hunks:
            # Don't write the file if any hunks failed - return error
            return (
                f"Error: Failed to apply hunks at indices: {failed_hunks}. "
                f"Applied {applied_count} of {len(hunks)} hunks. "
                "The file was not modified."
            )

        # Reconstruct the file
        if has_trailing_newline and new_lines:
            new_lines[-1] = new_lines[-1] + "\n"
        new_content = "".join(new_lines)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully applied {applied_count} hunk(s) to {file_path}"

    except Exception as e:
        return f"Error: {str(e)}"
