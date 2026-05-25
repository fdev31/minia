from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a small Python project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "import os\nimport json\n\nclass App:\n    def run(self):\n        pass\n\ndef start():\n    pass\n",
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def helper():\n    return 42\n",
    )
    (tmp_path / "README.md").write_text("# Test Project\n")
    return tmp_path


@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    return f


@pytest.fixture
def tmp_binary_file(tmp_path: Path) -> Path:
    f = tmp_path / "binary.bin"
    f.write_bytes(b"hello\x00world")
    return f


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mydir"
    d.mkdir()
    (d / "a.txt").write_text("aaa")
    (d / "b.txt").write_text("bbb")
    (d / "sub").mkdir()
    (d / "sub" / "c.txt").write_text("ccc")
    return d


@pytest.fixture
def tmp_empty_dir(tmp_path: Path) -> Path:
    return tmp_path / "emptydir"


@pytest.fixture
def outside_dir(tmp_path: Path) -> Path:
    """Create a directory outside the working directory (simulated)."""
    return tmp_path / "outside"
