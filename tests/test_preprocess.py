"""Tests for minia_tts.preprocess_text."""

import pytest

from minia_tts.preprocess import preprocess_text


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("hello 👋 world", "hello  world"),
        ("🎉🎊 party time", "party time"),
        ("emoji in middle hello 👍 world", "emoji in middle hello  world"),
    ],
)
def test_strip_emojis(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("foo.bar", "foo dot bar"),
        ("path/to/file.md", "path slash to slash file dot md"),
        ("readme.txt", "readme dot txt"),
        ("config.yml", "config dot yml"),
        ("no extension", "no extension"),
    ],
)
def test_expand_filenames(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("**bold text**", "bold text"),
        ("__bold text__", "bold text"),
        ("*italic text*", "italic text"),
        ("`inline code`", "inline code"),
        ("[link text](https://example.com)", "link text"),
        ("# heading", "heading"),
        ("## subheading", "subheading"),
        ("- list item", "list item"),
        ("![image](url)", "image"),
        ("~~strikethrough~~", "strikethrough"),
        ("> blockquote", "blockquote"),
    ],
)
def test_strip_markdown(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("https://example.com", "https colon slash slash example dot com"),
        (
            "Check http://example.com/path",
            "Check http colon slash slash example dot com/path",
        ),
        (
            "Visit https://foo.bar/baz",
            "Visit https colon slash slash foo dot bar slash baz",
        ),
    ],
)
def test_expand_urls(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("user@example.com", "user at example dot com"),
        ("email me john.doe@test.org", "email me john dot doe at test dot org"),
    ],
)
def test_expand_emails(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("e.g. this is a test", "for example this is a test"),
        ("i.e. another example", "that is another example"),
        ("vs. competition", "versus competition"),
        ("etc. more text", "etcetera more text"),
        ("Dr. Smith is here", "Doctor Smith is here"),
        ("Mr. Jones called", "Mister Jones called"),
        ("Mrs. Brown arrived", "Missus Brown arrived"),
        ("Ms. Davis left", "Miss Davis left"),
        ("Jr. and Sr.", "Junior and Senior"),
        ("Prof. Wilson teaches", "Professor Wilson teaches"),
        ("St. Patrick's Day", "Saint Patrick's Day"),
        ("Inc. and Ltd.", "Incorporated and Limited"),
        ("Corp. and Co.", "Corporation and Company"),
    ],
)
def test_expand_abbreviations(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("@user hello", "at user hello"),
        ("$100 is the price", "100 dollars is the price"),
        ("the price is 100$", "the price is 100 dollars"),
        ("99% off", "99 percent off"),
        ("#tag here", "hash tag here"),
    ],
)
def test_expand_symbols(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("v2.3.1", "version two point three point one"),
        ("running v1.0", "running version one point zero"),
        ("v10.20.30", "version ten point twenty point thirty"),
        ("v2", "version two"),
    ],
)
def test_expand_versions(input_text: str, expected: str) -> None:
    assert preprocess_text(input_text) == expected


def test_combined_pipeline() -> None:
    """Test that all steps work together correctly."""
    input_text = "**Check** `https://foo.bar` @user $100 v2.3.1"
    expected = "Check https colon slash slash foo dot bar at user 100 dollars version two point three point one"
    assert preprocess_text(input_text) == expected
