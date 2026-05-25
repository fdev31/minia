"""Kokoro TTS provider - synthesizes audio to numpy arrays.

Pipelines loaded lazily per language on first use.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, cast

import numpy as np

from minia_tts.cancellation import CancellationToken
from minia_tts.kokoro.constants import (
    ISO_TO_KOKORO,
    KOKORO_VOICES,
    REPO_ID,
    SAMPLE_RATE,
    WARMUP_PHRASES,
    apply_chunk_fades,
    resolve_voice,
    split_text,
)

logger = logging.getLogger(__name__)


def _resolve_voice_path(voice_name: str) -> str:
    """Download (or retrieve from cache) a voice .pt file."""
    from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]

    return str(hf_hub_download(repo_id=REPO_ID, filename=f"voices/{voice_name}.pt"))


class KokoroTTSProvider:
    """Text-to-speech using Kokoro (hexgrad/Kokoro-82M).

    Supports 9 languages with automatic voice selection.
    Pipelines are loaded lazily per language on first use.

    Synthesizes audio to numpy arrays at ``SAMPLE_RATE`` (24 kHz).
    """

    SAMPLE_RATE = 24000

    def __init__(
        self,
        *,
        voice: str | None = None,
        language: str = "en",
        speed: float = 1.0,
        volume: float = 1.0,
        args: dict | None = None,
    ) -> None:
        self._speed = max(0.5, min(2.0, speed))
        self._volume = max(0.0, min(2.0, volume))
        self._executor: Any = None
        self._executor_running = False
        self._args = args or {}

        # Lazy-loaded KPipeline instances keyed by Kokoro lang code
        self._pipelines: dict[str, Any] = {}

        # Cache: voice name -> local .pt file path
        self._voice_paths: dict[str, str] = {}

        # Language setting (ISO 639-1 or variant)
        self._language = language

        # Auto-detection flag: True if language was NOT explicitly set
        self._auto_language: bool = True

        # Cache for detected language (ISO 639-1 code)
        self._detected_lang: str | None = None

        # Current synthesis task (for stop/interrupt)
        self._current_task: Any = None
        self._cancellation = CancellationToken()

        # Resolve voice: explicit name -> language-based default
        self._voice_name: str = resolve_voice(language, voice)
        self._lang_code: str = self._voice_name[0] if self._voice_name else "a"
        self._requested_voice: str | None = voice

    async def start(self) -> None:
        """Load the pipeline for the initial voice's language and warm up."""
        if self._voice_name not in KOKORO_VOICES:
            fallback = "af_heart"
            logger.warning(
                "Voice '%s' not in Kokoro voice list, falling back to '%s'",
                self._voice_name,
                fallback,
            )
            self._voice_name = fallback
            self._lang_code = "a"

        logger.info("Kokoro TTS: loading pipeline for voice '%s'", self._voice_name)
        await self._ensure_pipeline(self._lang_code)
        await self._ensure_voice_path(self._voice_name)

        # Warmup
        warmup_text = WARMUP_PHRASES.get(self._lang_code, "Hello.")
        pipeline = self._pipelines[self._lang_code]
        voice_pt = self._voice_pt
        await self._run_in_executor(
            lambda: [None for _ in pipeline(warmup_text, voice=voice_pt, speed=1.0)]
        )
        logger.info(
            "Kokoro TTS ready: voice=%s, lang=%s, sr=%d",
            self._voice_name,
            self._lang_code,
            SAMPLE_RATE,
        )

    def _clear_resources(self) -> None:
        """Clear pipeline references."""
        self._pipelines.clear()
        self._voice_paths.clear()

    async def _ensure_executor(self) -> None:
        """Ensure the thread pool executor is running."""
        from concurrent.futures import ThreadPoolExecutor

        if self._executor is None or getattr(self._executor, "_shutdown", False):
            self._executor = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="kokoro",
            )
            self._executor_running = True

    async def _run_in_executor(self, fn, *args):
        """Run a function in the background executor."""
        await self._ensure_executor()
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, lambda: fn(*args)
        )

    async def _ensure_pipeline(self, lang_code: str) -> Any:
        """Lazy-load a KPipeline for the given language code."""
        if lang_code in self._pipelines:
            return self._pipelines[lang_code]

        from kokoro import KPipeline  # type: ignore[import-not-found]

        logger.info("Kokoro TTS: loading pipeline for lang_code='%s'", lang_code)

        pipeline = await self._run_in_executor(
            partial(KPipeline, lang_code=lang_code, repo_id=REPO_ID, **self._args)
        )
        self._pipelines[lang_code] = pipeline
        logger.info("Kokoro TTS: pipeline loaded for lang_code='%s'", lang_code)
        return pipeline

    async def _ensure_voice_path(self, voice_name: str) -> str:
        """Resolve and cache the local .pt path for a voice name."""
        if voice_name in self._voice_paths:
            return self._voice_paths[voice_name]

        path = await self._run_in_executor(_resolve_voice_path, voice_name)
        self._voice_paths[voice_name] = path
        logger.debug("Kokoro voice path cached: %s -> %s", voice_name, path)
        return str(path)

    @property
    def _voice_pt(self) -> str:
        """Return the cached .pt path for the current voice, or fall back to name."""
        return self._voice_paths.get(self._voice_name, self._voice_name)

    # -- Language detection --

    def _iso_to_kokoro(self, iso_code: str) -> str:
        """Map ISO 639-1 language code to Kokoro single-char lang code."""
        codes = ISO_TO_KOKORO.get(iso_code)
        if codes is not None:
            return cast(str, codes[0])
        logger.warning(
            "Unsupported TTS language '%s', falling back to English", iso_code
        )
        return "a"

    def _detect_language(self, text: str) -> str:
        """Detect the language of *text* and return the Kokoro lang code."""
        if self._detected_lang is not None:
            return self._iso_to_kokoro(self._detected_lang)

        try:
            import langid  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("langid not installed - falling back to English for TTS")
            self._detected_lang = "en"
            return "a"

        try:
            iso_code, _confidence = langid.classify(text)
            self._detected_lang = iso_code
            return self._iso_to_kokoro(iso_code)
        except Exception:
            logger.debug("TTS language detection failed, using English", exc_info=True)
            self._detected_lang = "en"
            return "a"

    def _resolve_lang_code(self, text: str) -> str:
        """Return the Kokoro lang code to use for *text*."""
        if self._auto_language:
            return self._detect_language(text)
        return self._lang_code

    # -- Core synthesis --

    def _synthesize_segment(
        self, segment: str, pipeline, voice_pt: str, speed: float
    ) -> np.ndarray:
        """Synthesize a single text segment and return audio chunk."""
        chunks: list[np.ndarray] = []
        for _gs, _ps, audio in pipeline(segment, voice=voice_pt, speed=speed):
            if audio is not None:
                chunk_np: np.ndarray = apply_chunk_fades(
                    np.asarray(audio, dtype=np.float32)
                )
                chunks.append(chunk_np)
        if chunks:
            result: np.ndarray = np.concatenate(chunks)
            return result
        return np.zeros(0, dtype=np.float32)

    async def speak(self, text: str) -> np.ndarray:
        """Synthesize text to a float32 numpy array."""
        self._cancellation = CancellationToken()
        lang_code = self._resolve_lang_code(text)
        await self._ensure_pipeline(lang_code)
        await self._ensure_voice_path(self._voice_name)

        voice_pt = self._voice_pt
        speed = self._speed
        pipeline = self._pipelines[lang_code]

        def _synth() -> np.ndarray:
            chunks: list[np.ndarray] = []
            for segment in split_text(text):
                if self._cancellation.is_cancelled:
                    break
                chunk = self._synthesize_segment(segment, pipeline, voice_pt, speed)
                if len(chunk) > 0:
                    chunks.append(chunk)
            if chunks:
                return np.concatenate(chunks)
            return np.zeros(0, dtype=np.float32)

        audio_np: np.ndarray = await self._run_in_executor(_synth)

        if len(audio_np) > 0 and self._volume != 1.0:
            audio_np = audio_np * self._volume
        return audio_np

    async def speak_streamed(self, text: str):
        """Generator that yields audio chunks as they are synthesized."""
        self._cancellation = CancellationToken()
        lang_code = self._resolve_lang_code(text)
        await self._ensure_pipeline(lang_code)
        await self._ensure_voice_path(self._voice_name)

        voice_pt = self._voice_pt
        speed = self._speed
        pipeline = self._pipelines[lang_code]
        segments = list(split_text(text))
        logger.info("[TTS] Segments: %d", len(segments))

        for i, segment in enumerate(segments):
            if self._cancellation.is_cancelled:
                logger.info("[TTS] Cancelled at segment %d/%d", i + 1, len(segments))
                break
            logger.debug(
                "[TTS] Synthesizing segment %d/%d: '%s'",
                i + 1,
                len(segments),
                segment[:80],
            )
            await asyncio.sleep(0)
            audio_np: np.ndarray = await self._run_in_executor(
                self._synthesize_segment, segment, pipeline, voice_pt, speed
            )
            await asyncio.sleep(0)
            if len(audio_np) > 0 and self._volume != 1.0:
                audio_np = audio_np * self._volume
            yield audio_np

    async def stop(self) -> None:
        """Stop synthesis and discard remaining audio."""
        logger.info(
            "[TTS] provider.stop: ENTER _cancellation.is_cancelled=%s",
            self._cancellation.is_cancelled,
        )
        self._cancellation.cancel()
        logger.info("[TTS] provider.stop: cancelled")

    @property
    def is_speaking(self) -> bool:
        """True if synthesis is in progress."""
        return not self._cancellation.is_cancelled

    def set_voice(self, voice: str) -> None:
        """Set voice name (will be loaded on next speak call)."""
        if voice not in KOKORO_VOICES:
            logger.warning("Unknown Kokoro voice '%s'", voice)
            return
        self._voice_name = voice
        self._requested_voice = voice
        self._lang_code = voice[0]
        self._auto_language = False
        self._detected_lang = None

    def set_language(self, language: str) -> None:
        """Set language (ISO 639-1 or variant) and resolve a matching voice."""
        if not language:
            return
        self._language = language
        self._voice_name = resolve_voice(language, self._requested_voice)
        self._lang_code = self._voice_name[0]
        self._auto_language = False
        self._detected_lang = None

    def set_speed(self, speed: float) -> None:
        """Set speech rate multiplier (0.5-2.0)."""
        self._speed = max(0.5, min(2.0, speed))

    def set_volume(self, volume: float) -> None:
        """Set volume (0.0 to 2.0)."""
        self._volume = max(0.0, min(2.0, volume))

    def list_voices(self) -> list[str]:
        """Return available Kokoro voice names."""
        return list(KOKORO_VOICES)

    def shutdown(self) -> None:
        """Release resources."""
        self._clear_resources()
        executor = self._executor
        if executor is not None:
            shutdown_flag = getattr(executor, "_shutdown", False)
            if not shutdown_flag:
                executor.shutdown(wait=False)
                self._executor_running = False
