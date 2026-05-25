import os


from minia_mcp_server.tool_pythonproj import (
    extract_python_project_structure,
    _build_summary,
    _extract_file_info,
)


class TestExtractFileInfo:
    def test_single_file(self, tmp_project):
        f = tmp_project / "src" / "main.py"
        result = _extract_file_info(str(f), include_docstrings=False)
        assert "imports" in result
        assert "functions" in result
        assert "classes" in result
        assert "text" in result
        assert "os" in result["imports"]
        assert "App" in result["classes"]
        assert "start" in result["functions"]

    def test_single_file_with_docstrings(self, tmp_project):
        f = tmp_project / "src" / "main.py"
        result = _extract_file_info(str(f), include_docstrings=True)
        assert "text" in result

    def test_nonexistent_file(self, tmp_path):
        result = _extract_file_info(str(tmp_path / "nope.py"), include_docstrings=False)
        assert "error" in result

    def test_invalid_python(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def ( : @@ invalid syntax !!!")
        result = _extract_file_info(str(f), include_docstrings=False)
        assert "error" in result

    def test_non_python_file(self, tmp_project):
        result = _extract_file_info(
            str(tmp_project / "README.md"), include_docstrings=False
        )
        assert "text" in result


class TestBuildSummary:
    def test_build_summary_basic(self, tmp_project):
        files_data = {}
        for root, _, files in os.walk(tmp_project / "src"):
            for f in files:
                fp = os.path.join(root, f)
                files_data[fp] = _extract_file_info(fp, include_docstrings=False)
        result = _build_summary(files_data, str(tmp_project / "src"))
        assert "Python files found" in result

    def test_build_summary_empty(self):
        result = _build_summary({}, "/some/dir")
        assert "Python files found" in result

    def test_build_summary_no_crash_on_relative_imports(self):
        """Regression test: relative imports like 'from . import x' should not crash."""
        files_data = {
            "/fake/relative.py": {
                "imports": [".module", ".thing.name", "os", "sys"],
                "functions": ["foo"],
                "classes": [],
                "text": "",
            }
        }
        result = _build_summary(files_data, "/fake")
        assert "Python files found" in result
        assert "os" in result
        assert "sys" in result

    def test_build_summary_modules_listed(self, tmp_project):
        files_data = {}
        for root, _, files in os.walk(tmp_project / "src"):
            for f in files:
                fp = os.path.join(root, f)
                files_data[fp] = _extract_file_info(fp, include_docstrings=False)
        result = _build_summary(files_data, str(tmp_project / "src"))
        # Should list modules found in imports
        assert "Modules:" in result


class TestExtractPythonProjectStructure:
    def test_single_file(self, tmp_project, monkeypatch):
        monkeypatch.chdir(tmp_project / "src")
        f = tmp_project / "src" / "main.py"
        result = extract_python_project_structure(str(f))
        assert "file" in result
        assert "imports" in result
        assert "functions" in result
        assert "classes" in result
        assert "summary" in result
        assert "suggested_next_steps" not in result

    def test_directory(self, tmp_project, monkeypatch):
        monkeypatch.chdir(tmp_project / "src")
        result = extract_python_project_structure(str(tmp_project / "src"))
        assert "directory" in result
        assert "files" in result
        assert "total_files" in result
        assert result["total_files"] >= 2
        assert "summary" in result
        assert "suggested_next_steps" not in result

    def test_directory_no_python_files(self, tmp_path):
        d = tmp_path / "nopys"
        d.mkdir()
        (d / "readme.md").write_text("# hi")
        result = extract_python_project_structure(str(d))
        assert "error" in result

    def test_nonexistent_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = extract_python_project_structure(str(tmp_path / "nope"))
        assert "not found" in result.get("error", "")

    def test_non_python_file(self, tmp_path, monkeypatch):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        monkeypatch.chdir(tmp_path)
        result = extract_python_project_structure(str(f))
        assert "not a Python" in result.get("error", "")
