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
    """Apply all pre-processing steps in order and return cleaned text.

    Processing order is carefully chosen to avoid interference between
    pattern expansions (e.g., IP addresses before URL dot expansion,
    dates/times before standalone number expansion).
    """
    text = _expand_abbreviations(text)
    text = _strip_emojis(text)
    text = _expand_avoid_s(text)
    text = _expand_markdown_headings(text)
    text = _strip_markdown(text)
    text = _expand_ip_addresses(text)
    text = _expand_phone_numbers(text)
    text = _expand_dates(text)
    text = _expand_times(text)
    text = _expand_versions(text)
    text = _expand_emails(text)
    text = _expand_urls(text)
    text = _expand_numbers(text)
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


# ---------------------------------------------------------------------------
# Month name lookup
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    "january": "january",
    "february": "february",
    "march": "march",
    "april": "april",
    "may": "may",
    "june": "june",
    "july": "july",
    "august": "august",
    "september": "september",
    "october": "october",
    "november": "november",
    "december": "december",
}

# ---------------------------------------------------------------------------
# (s) / (es) / (ies) pattern handling
# ---------------------------------------------------------------------------


def _expand_avoid_s(text: str) -> str:
    """Handle optional-plural and alternative patterns in parentheses.

    Examples:
        "file(s)" -> "files"
        "he/she" -> "he or she"
        "category(ies)" -> "categories"
        "(es)" suffix removal
        "(ies)" suffix removal
    """

    # Handle "(ies)" -> convert to "ies" (plural of words ending in consonant+y)
    # e.g., "category(ies)" -> "categories"
    def _replace_ies(match: re.Match) -> str:
        prefix = match.group(1)
        return prefix + "ies"

    text = re.sub(r"(\w)y\(ies\)", _replace_ies, text)

    # Handle "(es)" -> just remove the parentheses
    # e.g., "bus(es)" -> "buses"
    text = re.sub(r"\(es\)", "", text)

    # Handle "(s)" at end of word -> remove (plural marker)
    # e.g., "file(s)" -> "files"
    text = re.sub(r"\(s\)", "", text)

    # Handle "word1/word2" -> "word1 or word2"
    text = re.sub(r"(\w+)/(\w+)", r"\1 or \2", text)

    return text


# ---------------------------------------------------------------------------
# Markdown heading expansion
# ---------------------------------------------------------------------------

_HEADING_PREFIXES = {
    1: "title",
    2: "subtitle",
    3: "section",
    4: "subsection",
    5: "subsubsection",
    6: "sub-subsection",
}


def _expand_markdown_headings(text: str) -> str:
    """Convert markdown headings to spoken format.

    Examples:
        "# heading" -> "title heading"
        "## heading" -> "subtitle heading"
        "### heading" -> "section heading"
    """

    def _replace_heading(match: re.Match) -> str:
        hashes = match.group(1)
        heading_text = match.group(2)
        level = len(hashes)
        prefix = _HEADING_PREFIXES.get(level, "heading")
        return f"{prefix} {heading_text}"

    return re.sub(r"^(#{1,6})\s+(.+)$", _replace_heading, text, flags=re.MULTILINE)


# ---------------------------------------------------------------------------
# Number word expansion
# ---------------------------------------------------------------------------

# Scale names for large numbers
_SCALES = [
    (1_000_000_000, "billion"),
    (1_000_000, "million"),
    (1_000, "thousand"),
    (100, "hundred"),
]

# Tens and units for number words
_TENS = {
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
}

_UNITS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
}


def _number_to_words(n: int) -> str:
    """Convert an integer (0-999) to English words.

    e.g., 42 -> "forty-two", 0 -> "zero", 100 -> "one hundred"
    """
    if n == 0:
        return "zero"
    if n < 0:
        return "negative " + _number_to_words(-n)

    parts: list[str] = []

    if n >= 100:
        hundreds = n // 100
        remainder = n % 100
        parts.append(_UNITS[hundreds] + " hundred")
        if remainder > 0:
            n = remainder
        else:
            return " ".join(parts)

    if n in _UNITS:
        parts.append(_UNITS[n])
    elif n in _TENS:
        parts.append(_TENS[n])
    else:
        tens = (n // 10) * 10
        units = n % 10
        parts.append(f"{_TENS[tens]}-{_UNITS[units]}")

    return " ".join(parts)


def _expand_numbers(text: str) -> str:
    """Expand standalone numbers to their English word form.

    Handles:
        - Integers: "123" -> "one hundred twenty-three"
        - Decimals: "3.14" -> "three point one four"
        - Large numbers: "1,000,000" -> "one million"

    Does NOT expand numbers that are part of version strings,
    IP addresses, dates, times, phone numbers, or other already-
    processed patterns.
    """

    def _expand_number(match: re.Match) -> str:
        num_str = match.group(0)

        # Handle decimals: "3.14" -> "three point one four"
        if "." in num_str:
            parts = num_str.split(".")
            words = _number_to_words(int(parts[0]))
            for digit_part in parts[1:]:
                words += " point " + "".join(_UNITS[int(d)] for d in digit_part)
            return words

        # Remove commas for large numbers: "1,000,000"
        clean = num_str.replace(",", "")

        try:
            n = int(clean)
        except ValueError:
            return num_str

        # Handle large numbers with scale words
        result_parts: list[str] = []
        remaining = n

        for scale_value, scale_name in _SCALES:
            if remaining >= scale_value:
                count = remaining // scale_value
                remainder = remaining % scale_value
                if count == 1:
                    result_parts.append(_number_to_words(count))
                else:
                    result_parts.append(f"{_number_to_words(count)} {scale_name}")
                if remainder > 0:
                    remaining = remainder
                else:
                    remaining = 0

        if remaining > 0:
            result_parts.append(_number_to_words(remaining))

        return " ".join(result_parts)

    # Match integers, comma-separated numbers, and decimals
    # Use word boundaries to avoid matching inside words
    return re.sub(r"\b\d[\d,]*(?:\.\d+)?\b", _expand_number, text)


# ---------------------------------------------------------------------------
# Date expansion
# ---------------------------------------------------------------------------


def _expand_dates(text: str) -> str:
    """Expand date patterns to spoken form.

    Handles:
        - "2024-01-15" -> "January fifteenth twenty twenty-four"
        - "01/15/2024" -> "January fifteenth twenty twenty-four"
        - "15 January 2024" -> "January fifteenth twenty twenty-four"
        - "Q1 2024" -> "quarter one twenty twenty-four"
    """

    def _expand_year(year_str: str) -> str:
        """Expand a 4-digit year: 2024 -> 'twenty twenty-four'."""
        if len(year_str) == 4:
            first_two = year_str[:2]
            last_two = year_str[2:]
            return (
                _number_to_words(int(first_two)) + " " + _number_to_words(int(last_two))
            )
        return _number_to_words(int(year_str))

    def _expand_month(month_str: str) -> str:
        """Expand a month number to name."""
        month_num = int(month_str)
        if 1 <= month_num <= 12:
            month_names = [
                "",
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ]
            return month_names[month_num]
        return month_str

    # ISO date: YYYY-MM-DD
    def _replace_iso_date(match: re.Match) -> str:
        year = match.group(1)
        month = match.group(2)
        day = match.group(3)
        month_name = _expand_month(month)
        day_num = int(day)
        return f"{month_name} {day_num} {_expand_year(year)}"

    text = re.sub(
        r"\b(\d{4})-(\d{2})-(\d{2})\b",
        _replace_iso_date,
        text,
    )

    # US date: MM/DD/YYYY
    def _replace_us_date(match: re.Match) -> str:
        month = match.group(1)
        day = match.group(2)
        year = match.group(3)
        month_name = _expand_month(month)
        day_num = int(day)
        return f"{month_name} {day_num} {_expand_year(year)}"

    text = re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        _replace_us_date,
        text,
    )

    # Quarter: Q1 2024
    def _replace_quarter(match: re.Match) -> str:
        quarter = match.group(1)
        year = match.group(2)
        return f"quarter {quarter} {_expand_year(year)}"

    text = re.sub(r"\bQ(\d)\s+(\d{4})\b", _replace_quarter, text)

    return text


# ---------------------------------------------------------------------------
# Time expansion
# ---------------------------------------------------------------------------


def _expand_times(text: str) -> str:
    """Expand time patterns to spoken form.

    Handles:
        - "14:30" -> "two thirty PM"
        - "9:15 AM" -> "nine fifteen AM"
        - "23:59" -> "eleven fifty nine PM"
    """

    def _replace_24h_time(match: re.Match) -> str:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = "AM" if hour < 12 else "PM"
        if hour > 12:
            hour = hour - 12
        elif hour == 0:
            hour = 12
        minute_str = f"{minute:02d}"
        return f"{_number_to_words(hour)} {_number_to_words(minute)} {period}"

    text = re.sub(
        r"\b(\d{1,2}):(\d{2})\b",
        _replace_24h_time,
        text,
    )

    return text


# ---------------------------------------------------------------------------
# IP address expansion
# ---------------------------------------------------------------------------


def _expand_ip_addresses(text: str) -> str:
    """Expand IP addresses to spoken form.

    Examples:
        "192.168.1.1" -> "one nine two dot one six eight dot one dot one"
    """

    def _expand_ip(match: re.Match) -> str:
        ip = match.group(0)
        parts = ip.split(".")
        return " dot ".join(_number_to_words(int(p)) for p in parts)

    return re.sub(r"\b(\d{1,3}\.){3}\d{1,3}\b", _expand_ip, text)


# ---------------------------------------------------------------------------
# Phone number expansion
# ---------------------------------------------------------------------------


def _expand_phone_numbers(text: str) -> str:
    """Expand phone numbers to spoken form.

    Examples:
        "+1-555-123-4567" -> "positive one five five five one two three four five six seven"
        "(555) 123-4567" -> "five five five one two three four five six seven"
        "1-800-555-1234" -> "one eight zero zero five five five one two three four"
    """

    def _digits_to_words(match: re.Match) -> str:
        digits = match.group(0)
        # Remove any non-digit characters first
        clean_digits = re.sub(r"\D", "", digits)
        if not clean_digits:
            return digits

        # Handle leading "+" as "positive"
        if digits.startswith("+"):
            result = "positive "
            clean_digits = clean_digits[1:]
        else:
            result = ""

        # If it's a 10-digit US number, optionally prefix with "one"
        if len(clean_digits) == 10 and clean_digits.startswith("1"):
            # International dialing prefix
            result += "one "
            clean_digits = clean_digits[1:]
        elif len(clean_digits) == 11 and clean_digits.startswith("1"):
            result += "one "
            clean_digits = clean_digits[1:]

        result += " ".join(_DIGITS.get(d, d) for d in clean_digits)
        return result

    # Match various phone number formats
    # +1-555-123-4567, +1 555 123 4567, +1(555)123-4567
    text = re.sub(
        r"\+\d[\d\s\-\(\)]{6,}\d",
        _digits_to_words,
        text,
    )

    # (555) 123-4567, 555-123-4567, 555.123.4567
    text = re.sub(
        r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}",
        _digits_to_words,
        text,
    )

    return text
