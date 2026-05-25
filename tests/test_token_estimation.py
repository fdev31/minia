"""Tests for token estimation module."""

from unittest.mock import patch

from minia.token_estimation import estimate_tokens


def test_estimate_tokens_basic():
    """Basic token estimation returns positive integer."""
    result = estimate_tokens("Hello world")
    assert isinstance(result, int)
    assert result > 0


def test_estimate_tokens_empty():
    """Empty string returns zero tokens."""
    result = estimate_tokens("")
    assert result == 0


def test_estimate_tokens_longer_text():
    """Longer text estimates more tokens."""
    short = estimate_tokens("Hi")
    long_text = estimate_tokens(
        "This is a much longer piece of text with many more words to estimate tokens for."
    )
    assert long_text > short


def test_estimate_tokens_fallback():
    """Fallback to word*4 when tiktoken fails."""
    with patch("minia.token_estimation.tiktoken") as mock_tiktoken:
        mock_tiktoken.get_encoding.side_effect = Exception("tiktoken unavailable")
        result = estimate_tokens("hello world foo bar baz")
        assert result == 5 * 4  # 5 words * 4


def test_estimate_tokens_code():
    """Code with special characters is handled."""
    code = "def foo(x): return x + 1"
    result = estimate_tokens(code)
    assert isinstance(result, int)
    assert result > 0


def test_estimate_tokens_multiline():
    """Multiline text is handled correctly."""
    text = "line 1\nline 2\nline 3\nline 4\nline 5"
    result = estimate_tokens(text)
    assert isinstance(result, int)
    assert result > 0
