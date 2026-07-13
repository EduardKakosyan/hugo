"""NeMo Parakeet TDT-backed implementation of the Transcriber protocol.

Only importable inside the `stt` service venv (see deploy/stt/requirements.txt
and docs/adr/0005) — nemo_toolkit is deliberately not a dependency of the
main hugo package.

Uses NeMo's standard, well-documented batch `.transcribe()` API repeatedly
against a growing audio buffer to produce pseudo-streaming partials, rather
than NeMo's cache-aware streaming buffer utilities — simpler and more
robust for a first working version. Swapping to true frame-synchronous
streaming (lower partial-result latency) is a documented future
optimization once this is verified correct on real audio; see the M1.3
integration-test follow-up in the plan.

NOT YET VERIFIED against real audio on hardware — the model name and the
exact shape of `.transcribe()`'s return value should be confirmed with a
`pytest -m integration` run on the DGX Spark before relying on this.
"""

import asyncio

import numpy as np
from nemo.collections.asr.models import ASRModel

MODEL_NAME = "nvidia/parakeet-tdt-1.1b"
SAMPLE_RATE_HZ = 16_000
PARTIAL_INTERVAL_BYTES = SAMPLE_RATE_HZ * 2 * 1  # ~1s of 16-bit mono audio


class ParakeetTranscriber:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model = ASRModel.from_pretrained(model_name=model_name)
        self._model.eval()
        self._buffer = bytearray()
        self._bytes_since_last_partial = 0

    async def feed(self, pcm_chunk: bytes) -> str | None:
        self._buffer.extend(pcm_chunk)
        self._bytes_since_last_partial += len(pcm_chunk)
        if self._bytes_since_last_partial < PARTIAL_INTERVAL_BYTES:
            return None
        self._bytes_since_last_partial = 0
        return await asyncio.to_thread(self._transcribe_buffer)

    async def finalize(self) -> str:
        return await asyncio.to_thread(self._transcribe_buffer)

    def reset(self) -> None:
        self._buffer.clear()
        self._bytes_since_last_partial = 0

    def _transcribe_buffer(self) -> str:
        if not self._buffer:
            return ""
        audio = np.frombuffer(bytes(self._buffer), dtype=np.int16).astype(np.float32) / 32768.0
        [result] = self._model.transcribe([audio])
        return str(getattr(result, "text", result))
