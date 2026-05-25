"""Markdown-to-fragments converter for prompt_toolkit formatted text.

Converts markdown (headings, bold, italic, code, code blocks, bullet/numbered
lists, tables, horizontal rules) into prompt_toolkit style fragments.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Style names (must match keys in Style.from_dict in ChatUI)
# ---------------------------------------------------------------------------

_S_MD_HEADING = "class:md-heading"
_S_MD_BOLD = "class:md-bold"
_S_MD_BOLD_ITALIC = "class:md-bold italic"
_S_MD_ITALIC = "class:md-italic"
_S_MD_CODE = "class:md-code"
_S_MD_CODE_BLOCK = "class:md-code-block"
_S_MD_BULLET = "class:md-bullet"
_S_MD_TEXT = "class:md-text"
_S_SEPARATOR = "class:separator"


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

_TABLE_ROW_PAT = r"^\s*\|(.+)\|\s*$"
_TABLE_SEP_PAT = r"^\s*\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|\s*$"


def _get_table_row_re() -> re.Pattern[str]:
    return re.compile(_TABLE_ROW_PAT)


def _get_table_sep_re() -> re.Pattern[str]:
    return re.compile(_TABLE_SEP_PAT)


def _parse_table_cells(line: str) -> list[str]:
    """Extract cell contents from a markdown table row."""
    m = _get_table_row_re().match(line)
    if not m:
        return []
    return [cell.strip() for cell in m.group(1).split("|")]


def _render_table(
    rows: list[list[str]],
    header_idx: int | None,
    base_style: str,
    frags: list[tuple[str, str]],
) -> None:
    """Render a table with aligned columns into fragments."""
    if not rows:
        return
    n_cols = max(len(r) for r in rows)
    col_widths = [0] * n_cols
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    for row_idx, row in enumerate(rows):
        frags.append((base_style, "  "))
        for col_idx in range(n_cols):
            cell = row[col_idx] if col_idx < len(row) else ""
            padded = cell.ljust(col_widths[col_idx])
            if col_idx > 0:
                frags.append((_S_SEPARATOR, " │ "))
            if row_idx == header_idx:
                frags.append((_S_MD_BOLD, padded))
            else:
                inline_to_fragments(padded, base_style, frags)
        frags.append((base_style, "\n"))
        if row_idx == header_idx:
            frags.append((base_style, "  "))
            for col_idx in range(n_cols):
                if col_idx > 0:
                    frags.append((_S_SEPARATOR, "─┼─"))
                frags.append((_S_SEPARATOR, "─" * col_widths[col_idx]))
            frags.append((base_style, "\n"))


# ---------------------------------------------------------------------------
# Token formatting
# ---------------------------------------------------------------------------


def format_tokens(n: int) -> str:
    """Format token count as human-readable string (e.g. 1.2k, 64k)."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ---------------------------------------------------------------------------
# Markdown → fragments
# ---------------------------------------------------------------------------


def markdown_to_fragments(
    text: str,
    base_style: str = _S_MD_TEXT,
) -> list[tuple[str, str]]:
    """Convert markdown text to prompt_toolkit style fragments.

    Handles: ``# headings``, ``**bold**``, ``*italic*``, `` `code` ``,
    ```` ```code blocks``` ````, ``- bullet lists``, ``| tables |``.
    """
    frags: list[tuple[str, str]] = []
    lines = text.split("\n")

    if (
        len(lines) >= 2
        and lines[0].strip().lower() in ("```markdown", "```md")
        and lines[-1].strip() == "```"
    ):
        lines = lines[1:-1]

    in_code_block = False
    code_block_lines: list[str] = []
    table_rows: list[list[str]] = []
    table_header_idx: int | None = None

    def _flush_table() -> None:
        if table_rows:
            _render_table(table_rows, table_header_idx, base_style, frags)

    for line in lines:
        if line.strip().startswith("```"):
            if in_code_block:
                frags.append((_S_MD_CODE_BLOCK, "\n".join(code_block_lines)))
                frags.append((base_style, "\n"))
                code_block_lines = []
                in_code_block = False
            else:
                _flush_table()
                table_rows = []
                table_header_idx = None
                in_code_block = True
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        if _get_table_row_re().match(line):
            if _get_table_sep_re().match(line):
                if table_rows:
                    table_header_idx = len(table_rows) - 1
                continue
            table_rows.append(_parse_table_cells(line))
            continue

        if table_rows:
            _flush_table()
            table_rows = []
            table_header_idx = None

        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            frags.append((_S_MD_HEADING, heading_match.group(2)))
            frags.append((base_style, "\n"))
            continue

        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            frags.append((_S_SEPARATOR, "─" * 40))
            frags.append((base_style, "\n"))
            continue

        bullet_match = re.match(r"^(\s*)([-*+])\s+(.*)", line)
        if bullet_match:
            indent = bullet_match.group(1)
            frags.append((base_style, indent))
            frags.append((_S_MD_BULLET, "• "))
            inline_to_fragments(bullet_match.group(3), base_style, frags)
            frags.append((base_style, "\n"))
            continue

        num_match = re.match(r"^(\s*)(\d+\.)\s+(.*)", line)
        if num_match:
            indent = num_match.group(1)
            frags.append((base_style, indent))
            frags.append((_S_MD_BULLET, num_match.group(2) + " "))
            inline_to_fragments(num_match.group(3), base_style, frags)
            frags.append((base_style, "\n"))
            continue

        inline_to_fragments(line, base_style, frags)
        frags.append((base_style, "\n"))

    if table_rows:
        _flush_table()

    if in_code_block and code_block_lines:
        frags.append((_S_MD_CODE_BLOCK, "\n".join(code_block_lines)))
        frags.append((base_style, "\n"))

    return frags


# ---------------------------------------------------------------------------
# Inline markdown → fragments
# ---------------------------------------------------------------------------


def inline_to_fragments(
    text: str,
    base_style: str,
    frags: list[tuple[str, str]],
) -> None:
    """Parse inline markdown (bold, italic, code) and append fragments."""
    pattern = re.compile(
        r"(\*\*\*(.+?)\*\*\*"
        r"|\*\*(.+?)\*\*"
        r"|\*(.+?)\*"
        r"|`(.+?)`)"
    )
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            frags.append((base_style, text[last : m.start()]))

        if m.group(2):
            frags.append((_S_MD_BOLD_ITALIC, m.group(2)))
        elif m.group(3):
            frags.append((_S_MD_BOLD, m.group(3)))
        elif m.group(4):
            frags.append((_S_MD_ITALIC, m.group(4)))
        elif m.group(5):
            frags.append((_S_MD_CODE, m.group(5)))

        last = m.end()

    if last < len(text):
        frags.append((base_style, text[last:]))
