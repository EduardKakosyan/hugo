"""NeMo Parakeet TDT-backed implementation of the Transcriber protocol.

Only importable inside the `stt` service venv (see deploy/stt/requirements.txt
and docs/adr/0005) — nemo_toolkit is deliberately not a dependency of the
main hugo package.

Transcribes exactly once, at end of utterance (VEN-56). The previous shape
re-transcribed the entire growing buffer every ~1s to produce partials —
O(n²) GPU work competing with vLLM decode for the same GPU, and the voice
loop consumes only the final transcript, so the partials bought literally
nothing. Cache-aware streaming (e.g. nemotron-speech-streaming-en-0.6b,
near-instant finals plus genuinely usable partials) is the documented
future optimization if end-of-utterance transcription latency ever
matters; it isn't v1.
"""

import asyncio

import numpy as np
from nemo.collections.asr.models import ASRModel

MODEL_NAME = "nvidia/parakeet-tdt-1.1b"
SAMPLE_RATE_HZ = 16_000


class ParakeetTranscriber:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model = ASRModel.from_pretrained(model_name=model_name)
        self._model.eval()
        self._buffer = bytearray()

    async def feed(self, pcm_chunk: bytes) -> str | None:
        self._buffer.extend(pcm_chunk)
        return None

    async def finalize(self) -> str:
        return await asyncio.to_thread(self._transcribe_buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def _transcribe_buffer(self) -> str:
        if not self._buffer:
            return ""
        audio = np.frombuffer(bytes(self._buffer), dtype=np.int16).astype(np.float32) / 32768.0
        [result] = self._model.transcribe([audio])
        return str(getattr(result, "text", result))
