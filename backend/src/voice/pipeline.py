"""Voice pipeline – orchestrates VAD + STT + TTS with sounddevice I/O."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import numpy as np
import sounddevice as sd

from src.config import settings
from src.voice.stt import stt
from src.voice.tts import tts
from src.voice.vad import vad

logger = logging.getLogger("hugo.voice.pipeline")

# VAD expects 512-sample chunks at 16kHz (32ms)
VAD_CHUNK_SAMPLES = 512


class VoicePipeline:
    def __init__(self) -> None:
        self.on_transcript: Callable[[str], Coroutine[Any, Any, None]] | None = None
        self._running = False
        self._audio_buffer: list[np.ndarray] = []
        self._speech_buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._models_loaded = False

    def _load_models(self) -> None:
        if self._models_loaded:
            return
        vad.load()
        stt.load()
        tts.load()
        self._models_loaded = True

    async def start(self) -> None:
        await asyncio.to_thread(self._load_models)
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._speech_buffer = []

        self._stream = sd.InputStream(
            samplerate=settings.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=VAD_CHUNK_SAMPLES,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info("Voice pipeline started – listening on mic")

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)
        if not self._running:
            return

        chunk = indata[:, 0].copy()
        result = vad.process_chunk(chunk)

        if result["is_speaking"]:
            self._speech_buffer.append(chunk)

        if result["speech_end"] and self._speech_buffer:
            audio = np.concatenate(self._speech_buffer)
            self._speech_buffer = []
            vad.reset()
            if self._loop is not None:
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._handle_speech(audio),
                )

    async def _handle_speech(self, audio: np.ndarray) -> None:
        text = await asyncio.to_thread(stt.transcribe, audio)
        if not text or len(text.strip()) < 2:
            return
        logger.info("Transcribed: %s", text)
        if self.on_transcript:
            await self.on_transcript(text)

    async def speak(self, text: str) -> None:
        if self._stream is not None:
            self._stream.stop()
        try:
            audio, sr = await asyncio.to_thread(tts.synthesize, text)
            sd.play(audio, samplerate=sr)
            sd.wait()
        finally:
            if self._stream is not None and self._running:
                self._stream.start()

    async def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Voice pipeline stopped")


voice_pipeline = VoicePipeline()
