"""Text pre-processing for TTS synthesis.

Normalizes raw text before passing it to the Kokoro TTS engine.
Handles emojis, filenames, markdown, URLs, emails, abbreviations,
symbols, and version numbers to improve speech quality.
"""

from __future__ import annotations

import re
import unicodedata

# Digit to English word mapping for version numbers
_DIGITS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

# Small number words for version numbers
_NUMBER_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
    "13": "thirteen",
    "14": "fourteen",
    "15": "fifteen",
    "16": "sixteen",
    "17": "seventeen",
    "18": "eighteen",
    "19": "nineteen",
    "20": "twenty",
    "21": "twenty-one",
    "22": "twenty-two",
    "23": "twenty-three",
    "24": "twenty-four",
    "25": "twenty-five",
    "26": "twenty-six",
    "27": "twenty-seven",
    "28": "twenty-eight",
    "29": "twenty-nine",
    "30": "thirty",
    "31": "thirty-one",
    "32": "thirty-two",
    "33": "thirty-three",
    "34": "thirty-four",
    "35": "thirty-five",
    "36": "thirty-six",
    "37": "thirty-seven",
    "38": "thirty-eight",
    "39": "thirty-nine",
    "40": "forty",
    "41": "forty-one",
    "42": "forty-two",
    "43": "forty-three",
    "44": "forty-four",
    "45": "forty-five",
    "46": "forty-six",
    "47": "forty-seven",
    "48": "forty-eight",
    "49": "forty-nine",
    "50": "fifty",
    "51": "fifty-one",
    "52": "fifty-two",
    "53": "fifty-three",
    "54": "fifty-four",
    "55": "fifty-five",
    "56": "fifty-six",
    "57": "fifty-seven",
    "58": "fifty-eight",
    "59": "fifty-nine",
    "60": "sixty",
    "61": "sixty-one",
    "62": "sixty-two",
    "63": "sixty-three",
    "64": "sixty-four",
    "65": "sixty-five",
    "66": "sixty-six",
    "67": "sixty-seven",
    "68": "sixty-eight",
    "69": "sixty-nine",
    "70": "seventy",
    "71": "seventy-one",
    "72": "seventy-two",
    "73": "seventy-three",
    "74": "seventy-four",
    "75": "seventy-five",
    "76": "seventy-six",
    "77": "seventy-seven",
    "78": "seventy-eight",
    "79": "seventy-nine",
    "80": "eighty",
    "81": "eighty-one",
    "82": "eighty-two",
    "83": "eighty-three",
    "84": "eighty-four",
    "85": "eighty-five",
    "86": "eighty-six",
    "87": "eighty-seven",
    "88": "eighty-eight",
    "89": "eighty-nine",
    "90": "ninety",
    "91": "ninety-one",
    "92": "ninety-two",
    "93": "ninety-three",
    "94": "ninety-four",
    "95": "ninety-five",
    "96": "ninety-six",
    "97": "ninety-seven",
    "98": "ninety-eight",
    "99": "ninety-nine",
}

# Common TLDs whose following slashes should be preserved as URL paths
_COMMON_TLDS = frozenset(
    {
        "com",
        "org",
        "net",
        "edu",
        "gov",
        "mil",
        "int",
        "io",
        "co",
        "us",
        "uk",
        "de",
        "fr",
        "jp",
        "au",
        "ca",
        "it",
        "es",
        "nl",
        "se",
        "no",
        "fi",
        "dk",
        "pl",
        "cz",
        "ru",
        "cn",
        "in",
        "br",
        "mx",
        "ar",
        "za",
        "ng",
        "ke",
        "eu",
        "biz",
        "info",
        "name",
        "pro",
        "museum",
        "coop",
    }
)


def preprocess_text(text: str) -> str:
    """Apply all pre-processing steps in order and return cleaned text."""
    text = _expand_abbreviations(text)
    text = _strip_emojis(text)
    text = _strip_markdown(text)
    text = _expand_versions(text)
    text = _expand_emails(text)
    text = _expand_urls(text)
    text = _expand_filenames(text)
    text = _expand_symbols(text)
    return text.strip()


def _expand_abbreviations(text: str) -> str:
    """Expand common English abbreviations for TTS.

    Must run BEFORE filename expansion so patterns like "Dr." are not
    mangled into "Dr dot" first.
    """
    abbreviations = {
        "e.g.": "for example",
        "i.e.": "that is",
        "vs.": "versus",
        "etc.": "etcetera",
        "Dr.": "Doctor",
        "Mr.": "Mister",
        "Mrs.": "Missus",
        "Ms.": "Miss",
        "Sr.": "Senior",
        "Jr.": "Junior",
        "Prof.": "Professor",
        "St.": "Saint",
        "Inc.": "Incorporated",
        "Ltd.": "Limited",
        "Corp.": "Corporation",
        "Co.": "Company",
        "Dept.": "Department",
        "Gov.": "Government",
        "Hon.": "Honorable",
        "Rev.": "Reverend",
        "Gen.": "General",
        "Capt.": "Captain",
        "Lt.": "Lieutenant",
        "Sgt.": "Sergeant",
        "Pvt.": "Private",
        "Cmdr.": "Commander",
        "Adm.": "Admiral",
        "Col.": "Colonel",
        "Maj.": "Major",
        "Cpl.": "Corporal",
        "Spc.": "Specialist",
        "Ph.D.": "Doctor of Philosophy",
        "M.D.": "Doctor of Medicine",
    }

    # Sort by length (longest first) to avoid partial replacements
    sorted_abbrevs = sorted(abbreviations.keys(), key=len, reverse=True)

    for abbr in sorted_abbrevs:
        text = text.replace(abbr, abbreviations[abbr])

    return text


def _strip_emojis(text: str) -> str:
    """Remove all Unicode emoji characters.

    Only filters 'So' (Other Symbol) category which contains most emojis.
    Preserves currency symbols ('Sc'), math symbols ('Sm'), and punctuation ('Po')
    like $, @, #, % which are handled by later steps.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "So")


def _strip_markdown(text: str) -> str:
    """Strip common Markdown formatting for TTS."""
    # Code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Inline code (`code`)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Bold (**bold** or __bold__)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)

    # Italic (*italic* or _italic_)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # Strikethrough (~~strikethrough~~)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)

    # Headings (# heading)
    text = re.sub(r"^(#{1,6})\s+", "", text, flags=re.MULTILINE)

    # Image links ![alt](url) -> alt (must come before link rule)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Blockquotes (> text)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)

    # List markers (- item, * item, + item)
    text = re.sub(r"^[*\-+]\s+", "", text, flags=re.MULTILINE)

    # Horizontal rules (--- or ***)
    text = re.sub(r"^(-{3,}|_{3,}|\*{3,})$", "", text, flags=re.MULTILINE)

    return text


def _expand_urls(text: str) -> str:
    """Expand URL components for TTS."""
    # Expand protocol: https:// -> https colon slash slash (with trailing space)
    text = re.sub(
        r"(\w+)(://)",
        r"\1 colon slash slash ",
        text,
    )

    # Expand dots in URLs: example.com -> example dot com
    # Only expand dots that follow a word character
    text = re.sub(
        r"(\w+)\.",
        r"\1 dot ",
        text,
    )

    return text


def _expand_emails(text: str) -> str:
    """Expand email address components for TTS."""

    def _expand_email(match: re.Match) -> str:
        email = match.group(0)
        return email.replace("@", " at ").replace(".", " dot ")

    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", _expand_email, text)

    return text


def _expand_filenames(text: str) -> str:
    """Expand obvious filename patterns for TTS.

    Matches patterns like:
    - foo.bar -> foo dot bar
    - path/to/file.md -> path slash to slash file dot md

    Slashes after common TLDs are preserved as URL paths.
    """

    # Expand directory separators, preserving slashes after TLDs (URL paths)
    def _replace_slash(match: re.Match) -> str:
        prev_word = match.group(1)
        if prev_word.lower() in _COMMON_TLDS:
            return match.group(0)
        return f"{prev_word} slash "

    text = re.sub(r"(\w+)/", _replace_slash, text)

    # Expand file extensions: word.word -> word dot word
    text = re.sub(r"(\w+)\.(\w+)", r"\1 dot \2", text)

    return text


def _expand_symbols(text: str) -> str:
    """Expand symbols at word boundaries for TTS."""
    # Dollar sign at start of word: $100 -> 100 dollars
    text = re.sub(r"\$(\d+(?:\.\d+)?)", r"\1 dollars", text)

    # Dollar sign at end of word: 100$ -> 100 dollars
    text = re.sub(r"(\d+)\$", r"\1 dollars", text)

    # Percent sign: 99% -> 99 percent
    text = re.sub(r"(\d+)%", r"\1 percent", text)

    # At sign at word start: @user -> at user
    text = re.sub(r"\B@(\w+)", r"at \1", text)

    # Hash at word start: #tag -> hash tag
    text = re.sub(r"\B#(\w+)", r"hash \1", text)

    return text


def _expand_versions(text: str) -> str:
    """Expand version number patterns: v2.3.1 -> version two point three point one."""

    def _expand_version(match: re.Match) -> str:
        version_str = match.group(1)
        parts = version_str.split(".")
        words = []
        for part in parts:
            if part in _NUMBER_WORDS:
                words.append(_NUMBER_WORDS[part])
            elif part.isdigit():
                # Fall back to digits for numbers > 99
                words.append(part)
            else:
                words.append(part)
        return "version " + " point ".join(words)

    return re.sub(r"v(\d+(?:\.\d+)*)", _expand_version, text)
