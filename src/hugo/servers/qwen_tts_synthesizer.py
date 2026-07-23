"""Qwen3-TTS-backed implementation of the Synthesizer protocol, via the
faster-qwen3-tts wrapper (VEN-56).

Only importable inside the `tts` service venv (see deploy/tts/requirements.txt
and docs/adr/0005) — faster_qwen3_tts is deliberately not a dependency of
the main hugo package.

Same model, same voice, genuinely streaming: the official `qwen_tts`
package can only synthesize a full utterance in one blocking call (its
"streaming" flag simulates streaming *text input*, not generation —
confirmed in its source), which put whole seconds of dead air before every
sentence. faster-qwen3-tts wraps the identical CustomVoice checkpoint with
CUDA-graph decode and yields audio chunks *during* generation — measured
by its author on DGX Spark GB10: ~464ms to first audio at 1.66x realtime
for the 1.7B. generate_custom_voice_streaming is a synchronous generator
doing GPU work per step, so it runs on a worker thread bridged to asyncio
through a queue; closing our async generator (the barge-in path) stops the
thread at the next chunk boundary, skipping the unspoken audio's GPU
compute.

The previous per-sentence chunking (split_sentences) is gone from this
layer: utterances now arrive one sentence at a time from the streaming
tool loop, and true streaming makes first-audio latency independent of
text length anyway.
"""

import asyncio
import threading
from collections.abc import AsyncGenerator

import numpy as np
import torch
from faster_qwen3_tts import FasterQwen3TTS

MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
DEFAULT_SPEAKER = "ryan"
DEFAULT_LANGUAGE = "English"
SAMPLE_RATE_HZ = 24_000
# Decode steps per yielded chunk: 4 steps ≈ 333ms of audio at the model's
# 12Hz frame rate — the author's chunk-size sweep shows smaller chunks cut
# time-to-first-audio at a small throughput cost, the right trade for a
# conversational assistant.
CHUNK_DECODE_STEPS = 4


class QwenTtsSynthesizer:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        speaker: str = DEFAULT_SPEAKER,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        # device/dtype must be explicit — the CPU default cost minutes per
        # sentence on dgx1's Grace cores (observed live 2026-07-22).
        # kwargs match the author's own DGX Spark benchmark configuration.
        self._model = FasterQwen3TTS.from_pretrained(
            model_name,
            device="cuda",
            dtype=torch.bfloat16,
            attn_implementation="eager",
            max_seq_len=2048,
        )
        self._speaker = speaker
        self._language = language

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        loop = asyncio.get_running_loop()
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        stop = threading.Event()

        def generate() -> None:
            try:
                for wav_chunk, _sample_rate, _timing in self._model.generate_custom_voice_streaming(
                    text=text,
                    speaker=self._speaker,
                    language=self._language,
                    chunk_size=CHUNK_DECODE_STEPS,
                ):
                    if stop.is_set():
                        return
                    loop.call_soon_threadsafe(chunks.put_nowait, _float32_to_pcm16(wav_chunk))
            finally:
                loop.call_soon_threadsafe(chunks.put_nowait, None)

        generation = loop.run_in_executor(None, generate)
        try:
            while (chunk := await chunks.get()) is not None:
                yield chunk
        finally:
            # Runs on normal exhaustion AND on aclose() (cancellation /
            # barge-in): stop the GPU thread at its next chunk boundary and
            # wait it out so a new utterance never overlaps generation.
            stop.set()
            await generation


def _float32_to_pcm16(wav: np.ndarray) -> bytes:
    clipped = np.clip(wav, -1.0, 1.0)
    return bytes((clipped * 32767).astype(np.int16).tobytes())
