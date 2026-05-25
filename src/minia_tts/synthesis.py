"""Audio synthesis handlers for the TTS service."""

from __future__ import annotations

import logging

from minia_tts.cancellation import CancellationToken
from minia_tts.kokoro.constants import SAMPLE_RATE
from minia_tts.protocol import TTSState, _send_audio_frames, _send_ok

logger = logging.getLogger(__name__)


async def _speak_text(writer, state: TTSState, text: str) -> None:
    """Unified text synthesis handler for all output modes."""
    logger.info("[TTS] Synthesis started: '%s'", text[:200])
    state.synthesis.speaking = True
    state.synthesis.current_text = text
    state.synthesis._cancellation = CancellationToken()
    state.synthesis._stop_handled = False
    if state.output_playback:
        state.output_playback.reset_stopped()

    cancelled = False
    try:
        if state.config.output_mode == "playback":
            output_fn = state.output_playback.play if state.output_playback else None
            await _synthesize(writer, state, text, output_fn=output_fn)
        elif state.config.output_mode == "stream":
            await _synthesize(writer, state, text, stream_fn=_send_audio_frames)
        else:
            output_fn = state.output_playback.play if state.output_playback else None
            await _synthesize(
                writer, state, text, output_fn=output_fn, stream_fn=_send_audio_frames
            )
    except Exception as e:
        logger.error("Synthesis error: %s", e)
        cancelled = True
    finally:
        state.synthesis.speaking = False
        state.synthesis.current_text = ""
        if cancelled:
            logger.info("[TTS] Synthesis cancelled")
        elif not state.synthesis._stop_handled:
            logger.info("[TTS] Synthesis completed")
            try:
                await _send_ok(writer)
            except Exception:
                pass


async def _synthesize(
    writer, state: TTSState, text: str, output_fn=None, stream_fn=None
) -> None:
    """Synthesize text and send audio through configured outputs."""
    chunk_count = 0
    try:
        async for audio_chunk in state.provider.speak_streamed(text):
            if state.synthesis._cancellation.is_cancelled or len(audio_chunk) == 0:
                break
            if output_fn is not None:
                await output_fn(audio_chunk, SAMPLE_RATE)
            if stream_fn is not None:
                await stream_fn(writer, audio_chunk)
            chunk_count += 1
            logger.debug("[TTS] Audio chunk %d processed", chunk_count)
    except Exception as e:
        logger.error("Synthesis error during chunk processing: %s", e)
