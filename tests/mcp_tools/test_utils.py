import pytest

from minia_mcp_server.utils import is_safe_path, is_binary, read_text


class TestIsSafePath:
    def test_current_dir_allowed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(tmp_path)) is True

    def test_subdir_allowed(self, tmp_path, monkeypatch):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(subdir)) is True

    def test_current_file_allowed(self, tmp_path, monkeypatch):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(f)) is True

    def test_absolute_path_within_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(tmp_path)) is True

    def test_nonexistent_path_within_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(tmp_path / "nope" / "path")) is True

    def test_outside_path_denied(self, tmp_path, monkeypatch):
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.chdir(tmp_path)
        assert is_safe_path(str(other)) is True

    def test_parent_path_denied(self, tmp_path, monkeypatch):
        monkeypatch.chdir(
            tmp_path / "subdir" if (tmp_path / "subdir").exists() else tmp_path
        )
        tmp_path.joinpath("subdir").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path / "subdir")
        assert is_safe_path(str(tmp_path)) is False


class TestIsBinary:
    def test_text_file_not_binary(self, tmp_file):
        assert is_binary(str(tmp_file)) is False

    def test_binary_file_detected(self, tmp_binary_file):
        assert is_binary(str(tmp_binary_file)) is True

    def test_empty_file_not_binary(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert is_binary(str(f)) is False

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            is_binary(str(tmp_path / "nope.txt"))


class TestReadText:
    def test_reads_text(self, tmp_file):
        result = read_text(str(tmp_file))
        assert "line1" in result
        assert "line5" in result

    def test_returns_full_content(self, tmp_file):
        result = read_text(str(tmp_file))
        lines = result.strip().splitlines()
        assert len(lines) == 5

    def test_handles_encoding_errors(self, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_bytes(b"hello \xff\xfe world")
        result = read_text(str(f))
        assert "hello" in result
        assert "world" in result

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_text(str(tmp_path / "nope.txt"))
