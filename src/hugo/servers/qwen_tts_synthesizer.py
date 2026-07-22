"""Qwen3-TTS-backed implementation of the Synthesizer protocol.

Only importable inside the `tts` service venv (see deploy/tts/requirements.txt
and docs/adr/0005) — qwen_tts is deliberately not a dependency of the main
hugo package.

NOT streaming at the model level: the official `qwen-tts` package's
`non_streaming_mode` flag only simulates streaming *text input*, not
streaming *generation* — confirmed via its own docstring on dgx1
(2026-07-13). `generate_custom_voice()` always returns a complete
utterance's audio in one call. We synthesize sentence-by-sentence (see
split_sentences in servers/tts_server.py), chunking each sentence's audio
ourselves and yielding progressively, so callers get a genuinely
streamable, cancellable interface at the wire-protocol layer: first audio
after one sentence's compute rather than the whole answer's (whole-answer
was measured in minutes of silence on dgx1, 2026-07-22), and cancellation
between sentences skips the unspoken sentences' GPU compute. Within a
single sentence the model call is still all-or-nothing; swapping to a
true streaming-capable fork (e.g. andimarafioti/faster-qwen3-tts) remains
a documented future optimization, not needed for a correct v1.

VERIFIED on real hardware (dgx1, 2026-07-13): model loads, speaker/language
lists resolve, and a real synthesis call returns float32 PCM at 24kHz.
"""

import asyncio
from collections.abc import AsyncGenerator

import numpy as np
import qwen_tts
import torch

from hugo.servers.tts_server import split_sentences

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
        # device_map/dtype must be explicit: from_pretrained's default is
        # CPU, where a single sentence takes minutes on dgx1's Grace cores
        # (observed live 2026-07-22 — 221% CPU, 85s+ into one sentence,
        # while every earlier "silent SPEAKING" incident traced back to
        # exactly this). qwen_tts's own docstring names these kwargs as
        # the intended GPU configuration.
        self._model = qwen_tts.Qwen3TTSModel.from_pretrained(
            model_name, device_map="cuda:0", dtype=torch.bfloat16
        )
        self._speaker = speaker
        self._language = language

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        # Sentence-by-sentence, not whole-utterance: generate_custom_voice
        # is one blocking call per text it's given, so per-sentence calls
        # cap first-audio latency at one sentence and let cancellation
        # (generator close between yields) skip the remaining sentences'
        # GPU compute entirely — see split_sentences' docstring.
        for sentence in split_sentences(text):
            pcm = await asyncio.to_thread(self._synthesize_full, sentence)
            for offset in range(0, len(pcm), CHUNK_BYTES):
                yield pcm[offset : offset + CHUNK_BYTES]

    def _synthesize_full(self, text: str) -> bytes:
        [wav], _sample_rate = self._model.generate_custom_voice(
            text=text, speaker=self._speaker, language=self._language
        )
        clipped = np.clip(wav, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        return bytes(pcm16.tobytes())
