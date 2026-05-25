"""Constants, voice lists, and helpers for Kokoro TTS."""

from __future__ import annotations

import re
import types
from typing import TypeVar

_np: types.ModuleType | None = None


def _get_np() -> types.ModuleType:
    global _np
    if _np is None:
        import numpy

        _np = numpy
    return _np


# ISO 639-1 to Kokoro single-char language code mapping
ISO_TO_KOKORO: dict[str, list[str]] = {
    "en": ["a", "b"],
    "en-us": ["a"],
    "en-gb": ["b"],
    "es": ["e"],
    "fr": ["f"],
    "hi": ["h"],
    "it": ["i"],
    "ja": ["j"],
    "pt": ["p"],
    "zh": ["z"],
}

KOKORO_TO_ISO: dict[str, str] = {
    v[0]: k[-2:] for k, v in ISO_TO_KOKORO.items() if len(v) == 1
}

# Default voice per Kokoro language code
DEFAULT_VOICES: dict[str, str] = {
    "a": "af_heart",
    "b": "bf_emma",
    "e": "ef_dora",
    "f": "ff_siwis",
    "h": "hf_alpha",
    "i": "if_sara",
    "j": "jf_alpha",
    "p": "pf_dora",
    "z": "zf_xiaobei",
}

# All 54 voices shipped with Kokoro
KOKORO_VOICES: list[str] = [
    # American English (a)
    "af_heart",
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    # British English (b)
    "bf_emma",
    "bf_isabella",
    "bf_alice",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
    # Spanish (e)
    "ef_dora",
    "em_alex",
    "em_santa",
    # French (f)
    "ff_siwis",
    # Hindi (h)
    "hf_alpha",
    "hf_beta",
    "hm_omega",
    "hm_psi",
    # Italian (i)
    "if_sara",
    "im_nicola",
    # Japanese (j)
    "jf_alpha",
    "jf_gongitsune",
    "jf_nezumi",
    "jf_tebukuro",
    "jm_kumo",
    # Portuguese - Brazilian (p)
    "pf_dora",
    "pm_alex",
    "pm_santa",
    # Chinese - Mandarin (z)
    "zf_xiaobei",
    "zf_xiaoni",
    "zf_xiaoxiao",
    "zf_xiaoyi",
    "zm_yunjian",
    "zm_yunxi",
    "zm_yunxia",
    "zm_yunyang",
]

SAMPLE_RATE = 24000  # Kokoro always outputs 24kHz float32
REPO_ID = "hexgrad/Kokoro-82M"

# Fade duration in samples at chunk boundaries to eliminate clicks
FADE_SAMPLES = int(SAMPLE_RATE * 0.005)

# Minimum characters to accumulate before synthesising
MIN_CHUNK_CHARS = 40

WARMUP_PHRASES: dict[str, str] = {
    "a": "Hello.",
    "b": "Hello.",
    "e": "Hola.",
    "f": "Bonjour.",
    "h": "Namaste.",
    "i": "Ciao.",
    "j": "こんにちは。",
    "p": "Olá.",
    "z": "你好。",
}


def resolve_voice(
    language: str | None = None,
    voice: str | None = None,
) -> str:
    """Resolve the voice name to use.

    Priority:
        1. Explicit *voice* argument (passthrough, validated later by the provider)
        2. *language* mapped via ``ISO_TO_KOKORO`` -> first available voice,
           falling back to ``DEFAULT_VOICES`` for the inferred Kokoro lang code
        3. ``"af_heart"`` (English) as ultimate fallback

    Args:
        language: ISO 639-1 (or regional variant) language code, e.g. ``"fr"``,
            ``"en-us"``.
        voice: An explicit Kokoro voice name.  Returned unchanged when provided.

    Returns:
        A Kokoro voice name string.
    """
    if voice:
        return voice

    if not language:
        return DEFAULT_VOICES["a"]  # af_heart

    # Try direct ISO -> voice list mapping first (handles regional variants)
    kokoro_codes = ISO_TO_KOKORO.get(language)
    if kokoro_codes:
        for code in kokoro_codes:
            default = DEFAULT_VOICES.get(code)
            if default:
                return default
        # All listed voices missing from DEFAULT_VOICES -> pick first code's default
        first = DEFAULT_VOICES.get(kokoro_codes[0])
        if first:
            return first

    # Last resort: try to infer a single-char lang code and look up DEFAULT_VOICES
    first_char = language[:1].lower()
    default = DEFAULT_VOICES.get(first_char)
    if default:
        return default

    return DEFAULT_VOICES["a"]


T = TypeVar("T")


def apply_chunk_fades(chunk: T, fade: int = FADE_SAMPLES) -> T:
    """Apply a short linear fade-out to an audio chunk."""
    if fade <= 0:
        return chunk
    np = _get_np()
    if not hasattr(chunk, "__len__") or len(chunk) < fade:
        return chunk
    out = chunk.copy()  # type: ignore[attr-defined]
    ramp_out = np.linspace(1.0, 0.0, fade, dtype=np.float32)
    out[-fade:] *= ramp_out
    return out  # type: ignore[no-any-return]


def split_text(text: str) -> list[str]:
    """Split text into sentence-sized chunks for optimal Kokoro prosody."""
    raw = re.split(r"(?<=[.!?;])\s+", text.strip())

    chunks: list[str] = []
    for segment in raw:
        segment = segment.strip()
        if not segment:
            continue
        if len(segment.split()) <= 40:
            chunks.append(segment)
            continue
        parts = re.split(r"(?<=[,;:\u2014\u2013])\s+", segment)  # em/en dash
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip() if buf else part
            if len(candidate.split()) > 40 and buf:
                chunks.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            chunks.append(buf)

    return chunks if chunks else [text]
