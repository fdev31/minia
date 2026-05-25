from unittest.mock import patch

import pytest

from minia_mcp_server.tool_web import (
    search_web,
    read_web_page,
)
from minia_mcp_server.tool_files import (
    grep,
    read_file,
    write_file,
    list_files,
    find_files,
    create_directory,
    delete_file,
    move_file,
    copy_file,
    get_file_info,
)
from minia_mcp_server.tool_edit import (
    edit_file,
    _replace_nth,
)


def _safe_path_mock(path):
    """Always return True for safe path in tests."""
    return True


@pytest.fixture
def mock_safe_path():
    with patch("minia_mcp_server.tool_files.is_safe_path", side_effect=_safe_path_mock):
        yield


@pytest.fixture
def cwd_project(tmp_path, monkeypatch):
    """Change cwd to tmp_path so is_safe_path returns True naturally."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


class TestReplaceNth:
    def test_replace_first(self):
        result = _replace_nth("a b a b", "a", "X", 1)
        assert result == "X b a b"

    def test_replace_second(self):
        result = _replace_nth("a b a b", "a", "X", 2)
        assert result == "a b X b"

    def test_replace_last(self):
        result = _replace_nth("a b a b", "a", "X", 3)
        assert result == "a b a X"

    def test_replace_nonexistent(self):
        with pytest.raises(ValueError, match="occurrence 2 not found"):
            _replace_nth("a", "b", "X", 2)


class TestSearchWeb:
    def test_search_web_returns_list(self, mock_safe_path):
        with patch("minia_mcp_server.tool_web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.text.return_value = [{"title": "test"}]
            result = search_web("test query")
            assert isinstance(result, list)

    def test_search_web_empty(self, mock_safe_path):
        with patch("minia_mcp_server.tool_web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.text.return_value = None
            result = search_web("test query")
            assert result == []

    def test_search_web_respects_max_results(self, mock_safe_path):
        with patch("minia_mcp_server.tool_web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.text.return_value = iter([{"title": "test"}])
            search_web("test query", max_results=10)
            mock_ddgs.return_value.text.assert_called_with("test query", max_results=10)


class TestReadWebPage:
    def test_read_web_page_error(self):
        with patch("minia_mcp_server.tool_web.requests.get") as mock_get:
            mock_get.return_value.raise_for_status.side_effect = Exception("404")
            result = read_web_page("http://invalid-url")
            assert "Error" in result

    def test_read_web_page_invalid_url(self):
        result = read_web_page("not-a-url")
        assert "Error" in result


class TestGrep:
    def test_grep_file_match(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello world\nfoo bar\n")
        result = grep(str(tmp_file), "hello")
        assert "match" in result.lower() or "hello" in result

    def test_grep_no_match(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello world\n")
        result = grep(str(tmp_file), "notfound")
        assert "No matches" in result

    def test_grep_directory(self, tmp_dir, mock_safe_path):
        (tmp_dir / "test.txt").write_text("hello world\n")
        result = grep(str(tmp_dir), "hello")
        assert "match" in result.lower() or "hello" in result

    def test_grep_recursive(self, tmp_dir, mock_safe_path):
        subdir = tmp_dir / "sub"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content\n")
        result = grep(str(tmp_dir), "nested", recursive=True)
        assert "match" in result.lower() or "nested" in result

    def test_grep_context_lines(self, tmp_file, mock_safe_path):
        tmp_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        result = grep(str(tmp_file), "line3", lines_before=1, lines_after=1)
        assert "line2" in result and "line4" in result

    def test_grep_nonexistent_path(self, mock_safe_path):
        result = grep("/nonexistent/path", "pattern")
        assert "not a valid" in result.lower() or "Error" in result

    def test_grep_single_file(self, tmp_file, mock_safe_path):
        tmp_file.write_text("test content\n")
        result = grep(str(tmp_file), "test")
        assert "match" in result.lower() or "test" in result


class TestReadFile:
    def test_read_file_success(self, tmp_file, mock_safe_path):
        tmp_file.write_text("line1\nline2\nline3\n")
        result = read_file(str(tmp_file))
        assert "line1" in result

    def test_read_file_not_found(self, mock_safe_path):
        result = read_file("/nonexistent/file.txt")
        assert "not found" in result.lower()

    def test_read_file_binary(self, tmp_binary_file, mock_safe_path):
        result = read_file(str(tmp_binary_file))
        assert "binary" in result.lower()

    def test_read_file_offset_limit(self, tmp_file, mock_safe_path):
        tmp_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        result = read_file(str(tmp_file), offset=1, limit=2)
        assert "line2" in result and "line3" in result
        assert "line1" not in result

    def test_read_file_offset_beyond_end(self, tmp_file, mock_safe_path):
        tmp_file.write_text("line1\n")
        result = read_file(str(tmp_file), offset=100, limit=10)
        assert "line1" not in result or "showing" in result


class TestWriteFile:
    def test_write_file_new(self, tmp_file, mock_safe_path):
        result = write_file(str(tmp_file), "new content")
        assert "Successfully" in result
        assert tmp_file.read_text() == "new content"

    def test_write_file_append(self, tmp_file, mock_safe_path):
        tmp_file.write_text("existing\n")
        result = write_file(str(tmp_file), "more", overwrite=False)
        assert "appended" in result.lower()
        assert "existing" in tmp_file.read_text()
        assert "more" in tmp_file.read_text()

    def test_write_file_overwrite(self, tmp_file, mock_safe_path):
        tmp_file.write_text("old\n")
        result = write_file(str(tmp_file), "new", overwrite=True)
        assert "overwrote" in result.lower()
        assert tmp_file.read_text() == "new"

    def test_write_file_restricted_path(self, mock_safe_path):
        result = write_file("/root/forbidden.txt", "content")
        assert "Access denied" in result


class TestListFiles:
    def test_list_files(self, tmp_dir, mock_safe_path):
        (tmp_dir / "file1.txt").write_text("a")
        (tmp_dir / "file2.txt").write_text("b")
        result = list_files(str(tmp_dir))
        assert "file1.txt" in result and "file2.txt" in result

    def test_list_files_not_found(self, mock_safe_path):
        result = list_files("/nonexistent/dir")
        assert "not found" in result.lower() or "ERROR" in result

    def test_list_files_not_a_directory(self, tmp_file, mock_safe_path):
        result = list_files(str(tmp_file))
        assert "not a directory" in result.lower() or "ERROR" in result

    def test_list_files_too_many(self, tmp_dir, mock_safe_path):
        for i in range(35):
            (tmp_dir / f"file{i}.txt").write_text("x")
        result = list_files(str(tmp_dir), recursive=True)
        assert "Too many" in result


class TestFindFiles:
    def test_find_files_pattern(self, tmp_dir, mock_safe_path):
        (tmp_dir / "test.py").write_text("x")
        (tmp_dir / "test.txt").write_text("x")
        result = list_files(str(tmp_dir), recursive=True)
        result = find_files(str(tmp_dir), "*.py")
        assert "test.py" in result

    def test_find_files_no_match(self, tmp_dir, mock_safe_path):
        (tmp_dir / "test.txt").write_text("x")
        result = find_files(str(tmp_dir), "*.xyz")
        assert result == ""

    def test_find_files_not_found(self, mock_safe_path):
        result = find_files("/nonexistent", "*.py")
        assert "Error" in result


class TestCreateDirectory:
    def test_create_directory(self, tmp_dir, mock_safe_path):
        new_dir = tmp_dir / "new_subdir"
        result = create_directory(str(new_dir))
        assert "Successfully" in result
        assert new_dir.is_dir()

    def test_create_directory_with_parents(self, tmp_dir, mock_safe_path):
        nested = tmp_dir / "a" / "b" / "c"
        result = create_directory(str(nested), parents=True)
        assert "Successfully" in result
        assert nested.is_dir()

    def test_create_directory_exists(self, tmp_dir, mock_safe_path):
        result = create_directory(str(tmp_dir))
        assert "Successfully" in result


class TestDeleteFile:
    def test_delete_file(self, tmp_file, mock_safe_path):
        result = delete_file(str(tmp_file))
        assert "Successfully" in result
        assert not tmp_file.exists()

    def test_delete_file_not_found(self, mock_safe_path):
        result = delete_file("/nonexistent/file.txt")
        assert "not found" in result.lower()

    def test_delete_file_restricted(self, mock_safe_path):
        result = delete_file("/root/forbidden.txt")
        assert "Access denied" in result


class TestMoveFile:
    def test_move_file(self, tmp_dir, mock_safe_path):
        src = tmp_dir / "src.txt"
        dst = tmp_dir / "dst.txt"
        src.write_text("content")
        result = move_file(str(src), str(dst))
        assert "Successfully" in result
        assert dst.exists()
        assert not src.exists()

    def test_move_file_error(self, mock_safe_path):
        result = move_file("/nonexistent1", "/nonexistent2")
        assert "Error" in result


class TestCopyFile:
    def test_copy_file(self, tmp_dir, mock_safe_path):
        src = tmp_dir / "src.txt"
        dst = tmp_dir / "dst.txt"
        src.write_text("content")
        result = copy_file(str(src), str(dst))
        assert "Successfully" in result
        assert dst.exists()
        assert dst.read_text() == "content"

    def test_copy_file_error(self, mock_safe_path):
        result = copy_file("/nonexistent1", "/nonexistent2")
        assert "Error" in result


class TestGetFileInfo:
    def test_get_file_info(self, tmp_file, mock_safe_path):
        tmp_file.write_text("test")
        result = get_file_info(str(tmp_file))
        assert "size" in result
        assert result["is_file"] is True

    def test_get_file_info_not_found(self, mock_safe_path):
        result = get_file_info("/nonexistent/file.txt")
        assert "error" in result

    def test_get_file_info_directory(self, tmp_dir, mock_safe_path):
        result = get_file_info(str(tmp_dir))
        assert result["is_dir"] is True
        assert result["is_file"] is False


class TestEditFile:
    def test_edit_file_unique(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello world\n")
        result = edit_file(str(tmp_file), "hello", "goodbye")
        assert "Replaced" in result
        assert tmp_file.read_text() == "goodbye world\n"

    def test_edit_file_not_found(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello\n")
        result = edit_file(str(tmp_file), "notfound", "replaced")
        assert "not found" in result.lower()

    def test_edit_file_not_unique(self, tmp_file, mock_safe_path):
        tmp_file.write_text("a\na\n")
        result = edit_file(str(tmp_file), "a", "b")
        assert "not unique" in result.lower()

    def test_edit_file_occurrence(self, tmp_file, mock_safe_path):
        tmp_file.write_text("a\na\na\n")
        edit_file(str(tmp_file), "a", "b", occurrence=2)
        assert tmp_file.read_text() == "a\nb\na\n"

    def test_edit_file_replace_all(self, tmp_file, mock_safe_path):
        tmp_file.write_text("a a a\n")
        result = edit_file(str(tmp_file), "a", "b", replace_all=True)
        assert "Replaced" in result and "occurrences" in result
        assert tmp_file.read_text() == "b b b\n"

    def test_edit_file_same_strings(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello\n")
        result = edit_file(str(tmp_file), "hello", "hello")
        assert "same" in result.lower()

    def test_edit_file_both_params_error(self, tmp_file, mock_safe_path):
        tmp_file.write_text("hello\n")
        result = edit_file(str(tmp_file), "hello", "hi", occurrence=1, replace_all=True)
        assert "Cannot specify both" in result
