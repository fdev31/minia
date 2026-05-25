from .mcp_instance import mcp, ToolError
from .utils import is_safe_path, read_text

import ast
import os


def _build_summary(files_data: dict, directory: str) -> str:
    """Build a concise summary of the project structure for the LLM."""
    total = len(files_data)
    all_modules: set[str] = set()
    all_functions: list[str] = []
    all_classes: list[str] = []

    for fpath, info in files_data.items():
        if info.get("imports"):
            for imp in info["imports"]:
                top = imp.split(".")[0]
                if top and not top.startswith("."):
                    all_modules.add(top)
        if info.get("functions"):
            all_functions.extend(info["functions"])
        if info.get("classes"):
            all_classes.extend(info["classes"])

    parts = [f"{total} Python files found."]
    if all_modules:
        parts.append(f"Modules: {', '.join(sorted(all_modules))}.")
    if all_classes:
        parts.append(f"Classes: {', '.join(sorted(set(all_classes)))}.")
    if all_functions:
        unique_funcs = sorted(set(all_functions))
        if len(unique_funcs) > 10:
            parts.append(
                f"Functions: {', '.join(unique_funcs[:10])}... (+{len(unique_funcs) - 10} more)."
            )
        else:
            parts.append(f"Functions: {', '.join(unique_funcs)}.")

    return " ".join(parts)


class StructureVisitor(ast.NodeVisitor):
    def __init__(self, structure, include_docstrings, source_lines):
        self.current_class = None
        self.indent = 0
        self.structure = structure
        self.include_docstrings = include_docstrings
        self.source_lines = source_lines

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.structure.append(f"{'  ' * self.indent}- class {node.name}")
        self.indent += 1
        self._add_snippet(node)
        self.generic_visit(node)
        self.indent -= 1
        self.current_class = None

    def visit_FunctionDef(self, node):
        # Skip nested functions (only show top-level and methods)
        if self.current_class is None and node.name.startswith("_"):
            return

        prefix = "  " * self.indent
        if self.current_class:
            prefix += "- "
        else:
            prefix += "- "

        # Build function/method signature
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        if args:
            signature = f"{node.name}({', '.join(args)})"
        else:
            signature = f"{node.name}()"

        self.structure.append(f"{prefix}{signature}")

        # Add docstring if requested and available
        if self.include_docstrings and ast.get_docstring(node):
            docstring = ast.get_docstring(node)
            self.structure.append(f"{prefix}  ```docstring\n{docstring}\n```")

        # Add code snippet (first few lines of body)
        self._add_snippet(node)

        # Don't visit nested functions
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef):
                continue
            self.visit(child)

    def _add_snippet(self, node):
        """Add a code snippet showing the first few lines of a node's body."""
        if not hasattr(node, "body") or not node.body:
            return
        if not self.source_lines:
            return

        start_line = node.body[0].lineno - 1  # 0-indexed
        end_line = min(start_line + 5, len(self.source_lines))  # max 5 lines
        snippet_lines = []
        for i in range(start_line, end_line):
            line = self.source_lines[i].rstrip()
            if line.strip():
                snippet_lines.append(f"{'  ' * (self.indent + 1)}{line}")

        if snippet_lines:
            self.structure.append(
                "  ```snippet\n" + "\n".join(snippet_lines) + "\n  ```"
            )


def _extract_file_info(file_path: str, include_docstrings: bool) -> dict:
    """Extract imports, functions, classes, and structure text from a single Python file."""
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    structure: list[str] = []

    try:
        content = read_text(file_path)
    except Exception as e:
        raise ToolError(f"Error reading file: {e}")

    try:
        tree = ast.parse(content)
    except Exception as e:
        raise ToolError(f"Error parsing file: {e}")

    source_lines = content.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}")
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    visitor = StructureVisitor(structure, include_docstrings, source_lines)
    visitor.visit(tree)

    return {
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "text": "\n".join(structure)
        if structure
        else "(empty or not a valid Python file)",
    }


@mcp.tool()
def extract_python_project_structure(
    file_path: str, include_docstrings: bool = False
) -> dict:
    """Analyze Python code structure (single file or directory).

    Returns structured data including imports, functions, classes,
    and an indented text representation with method signatures and
    code snippets (first 5 lines of each body).

    Note: This tool shows structure and snippets, not full file content.
    """
    if not is_safe_path(file_path):
        raise ToolError("Access denied.")

    if os.path.isdir(file_path):
        py_files = []
        for root, dirs, files in os.walk(file_path):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            for f in sorted(files):
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))
        if not py_files:
            raise ToolError("No Python files found")

        files_data = {}
        for py_file in py_files:
            files_data[py_file] = _extract_file_info(py_file, include_docstrings)

        summary = _build_summary(files_data, file_path)

        return {
            "directory": file_path,
            "files": files_data,
            "total_files": len(py_files),
            "summary": summary,
        }

    if not os.path.exists(file_path):
        raise ToolError(f"File not found at {file_path}")

    if not file_path.endswith(".py"):
        raise ToolError("File is not a Python file.")

    info = _extract_file_info(file_path, include_docstrings)

    return {
        "file": file_path,
        "imports": info["imports"],
        "functions": info["functions"],
        "classes": info["classes"],
        "text": f"# {file_path}\n" + info["text"],
        "summary": f"Single file: {os.path.basename(file_path)}. {len(info['imports'])} imports, {len(info['functions'])} functions, {len(info['classes'])} classes.",
    }
