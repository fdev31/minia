import fnmatch
import os
from typing import Callable, Iterator, Optional

import gitignore_parser  # type: ignore[import-untyped]


def is_safe_path(path: str) -> bool:
    """Check if path is within the current working directory or /tmp"""
    try:
        abs_path = os.path.realpath(os.path.normpath(path))
        cwd = os.path.realpath(os.getcwd())
        return (
            abs_path == cwd
            or abs_path.startswith(cwd + os.sep)
            or abs_path.startswith("/tmp")
        )
    except Exception:
        return False


def is_binary(path: str, sample_size: int = 1024) -> bool:
    """Check if a file is binary by looking for null bytes."""
    with open(path, "rb") as f:
        return b"\x00" in f.read(sample_size)


def read_text(path: str) -> str:
    """Read a text file with standard encoding handling."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Gitignore-aware directory walking
# ---------------------------------------------------------------------------

# Directories that are always skipped, regardless of .gitignore.
# These are common build artifacts, VCS dirs, virtual environments, and IDE files.
DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "build",
        "dist",
        "target",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        ".cache",
        ".idea",
        ".vscode",
        ".vs",
        ".settings",
        ".DS_Store",
        "vendor",
        "bower_components",
        ".next",
        ".nuxt",
        ".output",
        ".terraform",
        ".gradle",
        ".expo",
        ".svelte-kit",
        ".astro",
        ".parcel-cache",
        "coverage",
        ".nyc_output",
        ".parcel",
        ".bundle",
        ".yarn",
        ".pnp",
        "deps",
        "logs",
    }
)

# Compiled / binary extensions that are always skipped during directory walks.
SKIPPED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyo",
        ".pyc",
        ".pyd",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".dat",
    }
)

# Maximum file size for grep (5 MB). Larger files are skipped to avoid
# hanging the LLM on enormous binary or log files.
GREP_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _load_gitignore(directory: str) -> Optional[Callable[[str], bool]]:
    """Load .gitignore from *directory* and return a matcher function.

    The returned matcher expects **absolute paths** that are under
    *directory*.  Returns None if no .gitignore file exists.
    """
    gitignore_path = os.path.join(directory, ".gitignore")
    if os.path.isfile(gitignore_path):
        return gitignore_parser.parse_gitignore(gitignore_path)
    return None


def _is_dir_skipped(dir_name: str, include_hidden: bool) -> bool:
    """Return True if *dir_name* should be skipped during os.walk.

    - Directories in DEFAULT_SKIP_DIRS are ALWAYS skipped (even with include_hidden=True).
    - Other hidden directories (starting with '.') are skipped unless include_hidden=True.
    """
    # Always skip the hardcoded default directories.
    if dir_name in DEFAULT_SKIP_DIRS:
        return True
    # Skip hidden directories by default (unless explicitly requested).
    if not include_hidden and dir_name.startswith("."):
        return True
    return False


def _is_file_skipped(
    full_path: str,
    gitignore_matcher: Optional[Callable[[str], bool]],
    include_gitignored: bool,
    include_hidden: bool = False,
) -> bool:
    """Return True if *full_path* should be skipped during a directory walk.

    Parameters
    ----------
    full_path : str
        The **absolute** path to the file.
    gitignore_matcher : callable or None
        A matcher function that takes an absolute path and returns True if
        the file should be ignored.  The path is expected to be under the
        directory containing the .gitignore file.
    include_gitignored : bool
        If True, the matcher is bypassed and no files are skipped for
        gitignore reasons.
    include_hidden : bool
        If False (default), files whose basename starts with ``.`` are skipped.
    """
    filename = os.path.basename(full_path)
    # Skip hidden files by default (unless explicitly requested).
    if not include_hidden and filename.startswith("."):
        return True
    # Skip compiled / binary extensions.
    _, ext = os.path.splitext(filename)
    if ext.lower() in SKIPPED_EXTENSIONS:
        return True
    # Respect .gitignore unless the user explicitly asked to include ignored files.
    if not include_gitignored and gitignore_matcher is not None:
        if gitignore_matcher(full_path):
            return True
    return False


def _is_file_too_large(filepath: str) -> bool:
    """Return True if *filepath* exceeds GREP_MAX_FILE_SIZE."""
    try:
        return os.path.getsize(filepath) > GREP_MAX_FILE_SIZE
    except OSError:
        return False


def walk_files(
    root: str,
    pattern: Optional[str] = None,  # fnmatch pattern, None = accept all
    include_hidden: bool = False,
    include_gitignored: bool = False,
    gitignore_matcher: Optional[Callable[[str], bool]] = None,
    recursive: bool = True,
) -> Iterator[str]:
    """Walk *root* and yield file paths, applying all skip rules.

    Parameters
    ----------
    root : str
        The directory to walk (should be an absolute path).
    pattern : str or None
        If given, only yield files whose basename matches this fnmatch pattern.
    include_hidden : bool
        If False (default), directories starting with ``.`` are skipped
        (except those already in DEFAULT_SKIP_DIRS).
    include_gitignored : bool
        If False (default), files matching .gitignore patterns are skipped.
    gitignore_matcher : callable or None
        Pre-compiled gitignore matcher.  If None, ``walk_files`` will attempt
        to load .gitignore from *root*.  The matcher is expected to accept
        **absolute paths** under *root*.
    recursive : bool
        If False, only the immediate children of *root* are yielded.

    Yields
    ------
    str
        Absolute paths to files that passed all filters.
    """
    # Ensure root is absolute for consistent path handling
    root = os.path.abspath(root)

    if gitignore_matcher is None:
        gitignore_matcher = _load_gitignore(root)

    if not recursive:
        try:
            entries = os.listdir(root)
        except OSError:
            return
        for entry in entries:
            full = os.path.join(root, entry)
            if not os.path.isfile(full):
                continue
            if _is_file_skipped(
                full, gitignore_matcher, include_gitignored, include_hidden
            ):
                continue
            if pattern and not fnmatch.fnmatch(entry, pattern):
                continue
            yield full
        return

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden / default-skip dirs in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if not _is_dir_skipped(d, include_hidden)]

        for filename in filenames:
            full = os.path.join(dirpath, filename)
            if _is_file_skipped(
                full, gitignore_matcher, include_gitignored, include_hidden
            ):
                continue
            if pattern and not fnmatch.fnmatch(filename, pattern):
                continue
            yield full


def list_files_filtered(
    root: str,
    include_hidden: bool = False,
    include_gitignored: bool = False,
    gitignore_matcher: Optional[Callable[[str], bool]] = None,
) -> Iterator[str]:
    """Walk *root* and yield relative paths to all files, applying skip rules.

    Unlike ``walk_files``, this yields relative paths (relative to *root*)
    suitable for ``list_files`` output.
    """
    root = os.path.abspath(root)
    if gitignore_matcher is None:
        gitignore_matcher = _load_gitignore(root)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_dir_skipped(d, include_hidden)]
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            if _is_file_skipped(
                full, gitignore_matcher, include_gitignored, include_hidden
            ):
                continue
            rel = os.path.relpath(full, root)
            yield rel
