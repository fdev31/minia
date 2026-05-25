"""Tests for gitignore-aware directory walking in MCP tools."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from minia_mcp_server.tool_files import (
    grep,
    list_files,
    find_files,
)
from minia_mcp_server.utils import (
    DEFAULT_SKIP_DIRS,
    GREP_MAX_FILE_SIZE,
    SKIPPED_EXTENSIONS,
    _is_dir_skipped,
    _is_file_skipped,
    _load_gitignore,
    walk_files,
    list_files_filtered,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_gitignore_project(tmp_path: Path) -> Path:
    """Create a project with a .gitignore file and various directories.

    Structure::
        project/
            .gitignore
            src/
                main.py
                utils.py
            node_modules/
                package.js
            .venv/
                activate
            .hidden_dir/
                secret.txt
            build/
                output.o
            logs/
                app.log
            README.md
            data.txt
    """
    project = tmp_path / "project"
    project.mkdir()

    # .gitignore
    (project / ".gitignore").write_text("data.txt\n*.log\nbuild/\n.hidden_dir/\n")

    # src/
    src = project / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n")
    (src / "utils.py").write_text("def helper(): pass\n")

    # node_modules/ (should be skipped by DEFAULT_SKIP_DIRS)
    node = project / "node_modules"
    node.mkdir()
    (node / "package.js").write_text("module.exports = {};\n")

    # .venv/ (should be skipped by DEFAULT_SKIP_DIRS)
    venv = project / ".venv"
    venv.mkdir()
    (venv / "activate").write_text("#!/bin/bash\n")

    # .hidden_dir/ (should be skipped by default hidden-dir rule AND .gitignore)
    hidden = project / ".hidden_dir"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("secret\n")

    # build/ (should be skipped by DEFAULT_SKIP_DIRS AND .gitignore)
    build = project / "build"
    build.mkdir()
    (build / "output.o").write_text("binary data\n")

    # logs/ (should be skipped by DEFAULT_SKIP_DIRS)
    logs = project / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("log entry\n")

    # Root files
    (project / "README.md").write_text("# Project\n")
    (project / "data.txt").write_text("important data\n")

    return project


@pytest.fixture
def tmp_empty_gitignore(tmp_path: Path) -> Path:
    """Create a project with an empty .gitignore."""
    project = tmp_path / "empty_gitignore"
    project.mkdir()
    (project / ".gitignore").write_text("")
    (project / "file.txt").write_text("content\n")
    return project


@pytest.fixture
def tmp_no_gitignore(tmp_path: Path) -> Path:
    """Create a project without a .gitignore."""
    project = tmp_path / "no_gitignore"
    project.mkdir()
    (project / "file.txt").write_text("content\n")
    return project


# ---------------------------------------------------------------------------
# Unit tests for utility functions
# ---------------------------------------------------------------------------


class TestDefaultSkipDirs:
    """Test that DEFAULT_SKIP_DIRS contains expected directories."""

    def test_contains_pycache(self):
        assert "__pycache__" in DEFAULT_SKIP_DIRS

    def test_contains_git(self):
        assert ".git" in DEFAULT_SKIP_DIRS

    def test_contains_node_modules(self):
        assert "node_modules" in DEFAULT_SKIP_DIRS

    def test_contains_venv(self):
        assert ".venv" in DEFAULT_SKIP_DIRS
        assert "venv" in DEFAULT_SKIP_DIRS

    def test_contains_build_dirs(self):
        assert "build" in DEFAULT_SKIP_DIRS
        assert "dist" in DEFAULT_SKIP_DIRS
        assert "target" in DEFAULT_SKIP_DIRS

    def test_contains_ide_dirs(self):
        assert ".idea" in DEFAULT_SKIP_DIRS
        assert ".vscode" in DEFAULT_SKIP_DIRS


class TestSkippedExtensions:
    """Test that SKIPPED_EXTENSIONS contains expected file extensions."""

    def test_contains_python_bytecode(self):
        assert ".pyc" in SKIPPED_EXTENSIONS
        assert ".pyo" in SKIPPED_EXTENSIONS
        assert ".pyd" in SKIPPED_EXTENSIONS

    def test_contains_shared_libs(self):
        assert ".so" in SKIPPED_EXTENSIONS
        assert ".dll" in SKIPPED_EXTENSIONS
        assert ".dylib" in SKIPPED_EXTENSIONS

    def test_contains_binaries(self):
        assert ".exe" in SKIPPED_EXTENSIONS
        assert ".bin" in SKIPPED_EXTENSIONS
        assert ".dat" in SKIPPED_EXTENSIONS


class TestIsDirSkipped:
    """Test the _is_dir_skipped helper function."""

    def test_hidden_dir_skipped_by_default(self):
        assert _is_dir_skipped(".git", include_hidden=False)
        assert _is_dir_skipped(".venv", include_hidden=False)
        assert _is_dir_skipped(".hidden", include_hidden=False)

    def test_hidden_dir_not_skipped_when_requested(self):
        """Non-default hidden dirs should not be skipped with include_hidden=True."""
        assert not _is_dir_skipped(".hidden", include_hidden=True)
        # .tox is in DEFAULT_SKIP_DIRS, so it's always skipped
        assert _is_dir_skipped(".tox", include_hidden=True)

    def test_default_skip_dirs_always_skipped(self):
        """DEFAULT_SKIP_DIRS should always be skipped, even with include_hidden=True."""
        for dir_name in DEFAULT_SKIP_DIRS:
            assert _is_dir_skipped(dir_name, include_hidden=True)
            assert _is_dir_skipped(dir_name, include_hidden=False)

    def test_normal_dir_not_skipped(self):
        assert not _is_dir_skipped("src", include_hidden=False)
        assert not _is_dir_skipped("tests", include_hidden=False)
        # node_modules is in DEFAULT_SKIP_DIRS, so always skipped
        assert _is_dir_skipped("node_modules", include_hidden=True)

    def test_empty_dir_name_not_skipped(self):
        assert not _is_dir_skipped("", include_hidden=False)


class TestIsFileSkipped:
    """Test the _is_file_skipped helper function."""

    def test_skipped_extension_is_skipped(self):
        """Extension filtering works with absolute paths."""
        assert _is_file_skipped(
            "/tmp/main.pyc", None, include_gitignored=False, include_hidden=False
        )
        assert _is_file_skipped(
            "/tmp/module.so", None, include_gitignored=False, include_hidden=False
        )

    def test_non_skipped_extension_not_skipped(self):
        assert not _is_file_skipped(
            "/tmp/main.py", None, include_gitignored=False, include_hidden=False
        )
        assert not _is_file_skipped(
            "/tmp/readme.md", None, include_gitignored=False, include_hidden=False
        )

    def test_gitignore_matcher_skips_matching_files(self):
        """Test with a mock gitignore matcher using absolute paths."""

        def mock_matcher(path):
            return os.path.basename(path) == "ignored.txt"

        assert _is_file_skipped(
            "/tmp/ignored.txt",
            mock_matcher,
            include_gitignored=False,
            include_hidden=False,
        )
        assert not _is_file_skipped(
            "/tmp/kept.txt",
            mock_matcher,
            include_gitignored=False,
            include_hidden=False,
        )

    def test_include_gitignored_bypasses_matcher(self):
        """include_gitignored=True should bypass the matcher."""

        def mock_matcher(path):
            return os.path.basename(path) == "ignored.txt"

        assert not _is_file_skipped(
            "/tmp/ignored.txt",
            mock_matcher,
            include_gitignored=True,
            include_hidden=False,
        )

    def test_no_matcher_no_skip(self):
        """Without a matcher, no files should be skipped (except extensions)."""
        assert not _is_file_skipped(
            "/tmp/any_file.txt", None, include_gitignored=False, include_hidden=False
        )

    def test_hidden_file_skipped_by_default(self):
        """Hidden files (starting with .) should be skipped by default."""
        assert _is_file_skipped(
            "/tmp/.gitignore", None, include_gitignored=False, include_hidden=False
        )
        assert _is_file_skipped(
            "/tmp/.env", None, include_gitignored=False, include_hidden=False
        )

    def test_hidden_file_not_skipped_when_requested(self):
        """include_hidden=True should include hidden files."""
        assert not _is_file_skipped(
            "/tmp/.gitignore", None, include_gitignored=False, include_hidden=True
        )
        assert not _is_file_skipped(
            "/tmp/.env", None, include_gitignored=False, include_hidden=True
        )


class TestLoadGitignore:
    """Test the _load_gitignore helper function."""

    def test_returns_matcher_when_gitignore_exists(self, tmp_path: Path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")
        matcher = _load_gitignore(str(tmp_path))
        assert matcher is not None
        # gitignore_parser requires absolute paths
        assert matcher(str(tmp_path / "test.log"))
        assert not matcher(str(tmp_path / "test.txt"))

    def test_returns_none_when_no_gitignore(self, tmp_no_gitignore: Path):
        matcher = _load_gitignore(str(tmp_no_gitignore))
        assert matcher is None

    def test_handles_empty_gitignore(self, tmp_empty_gitignore: Path):
        matcher = _load_gitignore(str(tmp_empty_gitignore))
        assert matcher is not None
        # Empty gitignore should not skip anything
        assert not matcher(str(tmp_empty_gitignore / "anything.txt"))


# ---------------------------------------------------------------------------
# Integration tests for walk_files
# ---------------------------------------------------------------------------


class TestWalkFiles:
    """Test the walk_files utility function."""

    def test_skips_default_dirs_by_default(self, tmp_gitignore_project: Path):
        """Default dirs like node_modules, .venv, build should be skipped."""
        files = list(walk_files(str(tmp_gitignore_project)))
        file_basenames = [os.path.basename(f) for f in files]
        file_dirs = [os.path.basename(os.path.dirname(f)) for f in files]

        # These should NOT appear
        assert "node_modules" not in file_dirs
        assert ".venv" not in file_dirs
        assert "build" not in file_dirs
        assert "logs" not in file_dirs

        # These SHOULD appear
        assert "src" in file_dirs
        assert "main.py" in file_basenames
        assert "utils.py" in file_basenames

    def test_skips_hidden_dirs_by_default(self, tmp_gitignore_project: Path):
        """Hidden directories should be skipped by default."""
        files = list(walk_files(str(tmp_gitignore_project)))
        file_dirs = [os.path.basename(os.path.dirname(f)) for f in files]

        assert ".hidden_dir" not in file_dirs

    def test_includes_hidden_dirs_when_requested(self, tmp_gitignore_project: Path):
        """include_hidden=True allows walking into hidden directories.

        Note: .hidden_dir is also in .gitignore, so files inside are still
        filtered by gitignore unless include_gitignored=True is also set.
        This test verifies that the directory IS walked into (dir pruning
        respects include_hidden), even if files inside are still gitignored.
        """
        # With include_hidden=True, .hidden_dir is no longer pruned by
        # the dot-prefix rule. The directory IS walked into.
        # However, secret.txt inside is gitignored, so it won't appear
        # unless include_gitignored=True is also set.
        #
        # The key point: with include_hidden=True, the directory itself
        # is NOT skipped by _is_dir_skipped(), so os.walk descends into it.
        # Files inside are then subject to gitignore filtering.

        # When both flags are True, we should see everything
        files_both = list(
            walk_files(
                str(tmp_gitignore_project),
                include_hidden=True,
                include_gitignored=True,
            )
        )
        file_dirs_both = [os.path.basename(os.path.dirname(f)) for f in files_both]
        assert ".hidden_dir" in file_dirs_both

        # With just include_hidden=True, the dir is walked into but files
        # inside are gitignored, so we won't see files from that dir
        files_hidden_only = list(
            walk_files(
                str(tmp_gitignore_project),
                include_hidden=True,
            )
        )
        # .gitignore file itself should appear (it's hidden but include_hidden=True)
        file_basenames = [os.path.basename(f) for f in files_hidden_only]
        assert ".gitignore" in file_basenames

    def test_both_flags_see_hidden_gitignored_files(self, tmp_gitignore_project: Path):
        """Both include_hidden=True and include_gitignored=True should see everything."""
        files = list(
            walk_files(
                str(tmp_gitignore_project),
                include_hidden=True,
                include_gitignored=True,
            )
        )
        file_basenames = [os.path.basename(f) for f in files]

        # .hidden_dir/secret.txt should appear (hidden dir + gitignored file)
        assert "secret.txt" in file_basenames
        # data.txt is gitignored
        assert "data.txt" in file_basenames

    def test_respects_gitignore_patterns(self, tmp_gitignore_project: Path):
        """Files matching .gitignore patterns should be skipped."""
        files = list(walk_files(str(tmp_gitignore_project)))
        file_basenames = [os.path.basename(f) for f in files]

        # data.txt is in .gitignore
        assert "data.txt" not in file_basenames
        # *.log is in .gitignore (and logs/ is in DEFAULT_SKIP_DIRS)
        assert "app.log" not in file_basenames

    def test_include_gitignored_bypasses_patterns(self, tmp_gitignore_project: Path):
        """include_gitignored=True should include gitignored files (that aren't hidden)."""
        files = list(
            walk_files(
                str(tmp_gitignore_project),
                include_gitignored=True,
            )
        )
        file_basenames = [os.path.basename(f) for f in files]

        # data.txt is in .gitignore, should appear with include_gitignored=True
        assert "data.txt" in file_basenames
        # app.log is in .gitignore AND logs/ is in DEFAULT_SKIP_DIRS
        # So it won't appear because the dir is skipped before gitignore is checked
        # (DEFAULT_SKIP_DIRS takes precedence)

    def test_pattern_filtering(self, tmp_gitignore_project: Path):
        """fnmatch pattern should filter files."""
        files = list(
            walk_files(
                str(tmp_gitignore_project),
                pattern="*.py",
            )
        )
        file_basenames = [os.path.basename(f) for f in files]

        assert "main.py" in file_basenames
        assert "utils.py" in file_basenames
        assert "package.js" not in file_basenames  # was already skipped by default

    def test_non_recursive_mode(self, tmp_gitignore_project: Path):
        """recursive=False should only list immediate children."""
        files = list(
            walk_files(
                str(tmp_gitignore_project),
                recursive=False,
            )
        )
        # Should only get files directly in tmp_gitignore_project, not in src/
        for f in files:
            assert os.path.dirname(f) == str(tmp_gitignore_project)

    def test_no_gitignore_file(self, tmp_no_gitignore: Path):
        """Should work correctly when there's no .gitignore."""
        files = list(walk_files(str(tmp_no_gitignore)))
        assert len(files) == 1
        assert os.path.basename(files[0]) == "file.txt"


class TestListFilesFiltered:
    """Test the list_files_filtered utility function."""

    def test_returns_relative_paths(self, tmp_gitignore_project: Path):
        """Should return paths relative to root."""
        files = list(list_files_filtered(str(tmp_gitignore_project)))
        for rel in files:
            assert not os.path.isabs(rel)
            assert "/" not in rel or rel.startswith("src/")

    def test_skips_default_dirs(self, tmp_gitignore_project: Path):
        """Default dirs should be filtered out."""
        files = list(list_files_filtered(str(tmp_gitignore_project)))
        file_paths = set(files)

        assert "node_modules/package.js" not in file_paths
        assert ".venv/activate" not in file_paths
        assert "build/output.o" not in file_paths
        assert "logs/app.log" not in file_paths

    def test_includes_hidden_when_requested(self, tmp_gitignore_project: Path):
        """include_hidden=True should include hidden dirs in walk.

        Note: .hidden_dir is both hidden AND gitignored, so both flags
        are needed to see files inside it.
        """
        files = list(
            list_files_filtered(
                str(tmp_gitignore_project),
                include_hidden=True,
                include_gitignored=True,  # also need this since .hidden_dir is gitignored
            )
        )
        file_paths = set(files)

        # .hidden_dir/secret.txt should appear with both flags
        assert ".hidden_dir/secret.txt" in file_paths


# ---------------------------------------------------------------------------
# Integration tests for MCP tools
# ---------------------------------------------------------------------------


class TestGrepWithGitignore:
    """Test grep tool with gitignore-aware behavior."""

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_skips_default_dirs_in_grep(self, mock_safe, tmp_gitignore_project: Path):
        """grep should not search inside default skip dirs."""
        result = grep(
            str(tmp_gitignore_project),
            "print",
            recursive=True,
        )
        # Should find print in src/main.py
        assert "main.py" in result
        # Should NOT search in node_modules, .venv, etc.
        assert "node_modules" not in result
        assert ".venv" not in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_skips_gitignored_files_in_grep(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """grep should not search gitignored files."""
        result = grep(
            str(tmp_gitignore_project),
            "secret",
            recursive=True,
        )
        # .hidden_dir is skipped by default (hidden dir)
        assert ".hidden_dir" not in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_include_hidden_allows_hidden_dir_search(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """include_hidden=True + include_gitignored=True should allow searching hidden dirs."""
        # .hidden_dir is both hidden AND gitignored, so we need both flags
        result = grep(
            str(tmp_gitignore_project),
            "secret",
            recursive=True,
            include_hidden=True,
            include_gitignored=True,
        )
        assert "secret.txt" in result
        assert "secret" in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_include_gitignored_allows_gitignored_file_search(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """include_gitignored=True should allow searching gitignored files."""
        result = grep(
            str(tmp_gitignore_project),
            "important",
            recursive=True,
            include_gitignored=True,
        )
        assert "data.txt" in result
        assert "important" in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_skips_large_files_in_grep(self, mock_safe, tmp_path: Path):
        """grep should skip files larger than GREP_MAX_FILE_SIZE."""
        # Create a project
        project = tmp_path / "large_file_project"
        project.mkdir()
        (project / ".gitignore").write_text("")

        # Create a file that's too large - use .txt extension to avoid SKIPPED_EXTENSIONS
        large_file = project / "huge.txt"
        large_file.write_bytes(b"x" * (GREP_MAX_FILE_SIZE + 1024))

        # Create a small file with the pattern
        small_file = project / "small.txt"
        small_file.write_text("pattern\n")

        result = grep(str(project), "pattern", recursive=True)

        # Should find the pattern in small.txt
        assert "small.txt" in result
        # Should report skipping the large file
        assert "Skipped" in result
        assert "huge.txt" in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_grep_file_too_large_message(self, mock_safe, tmp_path: Path):
        """grep should report the size limit in the skip message."""
        project = tmp_path / "project"
        project.mkdir()
        (project / ".gitignore").write_text("")

        # Use .txt extension to avoid SKIPPED_EXTENSIONS
        large_file = project / "huge.txt"
        large_file.write_bytes(b"x" * (GREP_MAX_FILE_SIZE + 1024))

        result = grep(str(project), "x", recursive=True)

        assert f"exceeds {GREP_MAX_FILE_SIZE // 1024 // 1024}MB limit" in result


class TestListFilesWithGitignore:
    """Test list_files tool with gitignore-aware behavior."""

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_skips_default_dirs_in_list_files(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """list_files should not list files from default skip dirs."""
        result = list_files(
            str(tmp_gitignore_project),
            recursive=True,
        )
        assert "node_modules" not in result
        assert ".venv" not in result
        assert "build" not in result
        assert "logs" not in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_includes_hidden_when_requested(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """include_hidden=True should include hidden dirs (with gitignored bypass too)."""
        # .hidden_dir is both hidden AND gitignored, so we need both flags
        result = list_files(
            str(tmp_gitignore_project),
            recursive=True,
            include_hidden=True,
        )
        # With just include_hidden=True, .gitignore file itself appears
        # (it's hidden but include_hidden=True bypasses the dot rule)
        assert ".gitignore" in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_respects_gitignore_in_list_files(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """list_files should respect .gitignore patterns."""
        result = list_files(
            str(tmp_gitignore_project),
            recursive=True,
        )
        # data.txt is in .gitignore
        assert "data.txt" not in result
        # logs/app.log is in .gitignore (and logs/ is in DEFAULT_SKIP_DIRS)
        assert "logs/app.log" not in result


class TestFindFilesWithGitignore:
    """Test find_files tool with gitignore-aware behavior."""

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_skips_default_dirs_in_find_files(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """find_files should not find files in default skip dirs."""
        result = find_files(
            str(tmp_gitignore_project),
            "*.py",
        )
        assert "main.py" in result
        assert "utils.py" in result
        assert "node_modules" not in result
        assert ".venv" not in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_includes_hidden_when_requested(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """include_hidden=True + include_gitignored=True should include hidden dirs."""
        result = find_files(
            str(tmp_gitignore_project),
            "*.txt",
            include_hidden=True,
            include_gitignored=True,  # also need this since .hidden_dir is gitignored
        )
        assert ".hidden_dir" in result

    @patch("minia_mcp_server.tool_files.is_safe_path", return_value=True)
    def test_respects_gitignore_in_find_files(
        self, mock_safe, tmp_gitignore_project: Path
    ):
        """find_files should respect .gitignore patterns."""
        result = find_files(
            str(tmp_gitignore_project),
            "*.txt",
        )
        # data.txt is in .gitignore
        assert "data.txt" not in result
        # .hidden_dir/secret.txt is skipped (hidden dir)
        assert ".hidden_dir" not in result
