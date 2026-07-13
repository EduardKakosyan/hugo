"""Qwen3-TTS-backed implementation of the Synthesizer protocol.

Only importable inside the `tts` service venv (see deploy/tts/requirements.txt
and docs/adr/0005) — qwen_tts is deliberately not a dependency of the main
hugo package.

NOT streaming at the model level: the official `qwen-tts` package's
`non_streaming_mode` flag only simulates streaming *text input*, not
streaming *generation* — confirmed via its own docstring on dgx1
(2026-07-13). `generate_custom_voice()` always returns a complete
utterance's audio in one call. We synthesize the full utterance, then chunk
it ourselves and yield progressively, so callers still get a genuinely
streamable, cancellable interface at the wire-protocol layer (see
servers/tts_server.py) even though the model itself isn't chunking —
cancellation stops further chunks being *sent*, but doesn't save the
GPU compute already spent generating the full utterance. Swapping to a
true streaming-capable fork (e.g. andimarafioti/faster-qwen3-tts) for
lower first-audio latency and cancel-time compute savings is a documented
future optimization, not needed for a correct v1.

VERIFIED on real hardware (dgx1, 2026-07-13): model loads, speaker/language
lists resolve, and a real synthesis call returns float32 PCM at 24kHz.
"""

import asyncio
from collections.abc import AsyncGenerator

import numpy as np
import qwen_tts

MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
DEFAULT_SPEAKER = "ryan"
DEFAULT_LANGUAGE = "english"
SAMPLE_RATE_HZ = 24_000
CHUNK_DURATION_S = 0.05
CHUNK_BYTES = int(SAMPLE_RATE_HZ * CHUNK_DURATION_S) * 2  # 16-bit samples


class QwenTtsSynthesizer:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        speaker: str = DEFAULT_SPEAKER,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._model = qwen_tts.Qwen3TTSModel.from_pretrained(model_name)
        self._speaker = speaker
        self._language = language

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        pcm = await asyncio.to_thread(self._synthesize_full, text)
        for offset in range(0, len(pcm), CHUNK_BYTES):
            yield pcm[offset : offset + CHUNK_BYTES]

    def _synthesize_full(self, text: str) -> bytes:
        [wav], _sample_rate = self._model.generate_custom_voice(
            text=text, speaker=self._speaker, language=self._language
        )
        clipped = np.clip(wav, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        return bytes(pcm16.tobytes())
