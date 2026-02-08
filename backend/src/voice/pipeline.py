"""Voice pipeline – Silero VAD for speech detection, Gemini API for STT, Kokoro for TTS."""

import asyncio
import io
import logging
import wave
from typing import Any

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

from src.config import settings
from src.events import TRANSCRIPT_READY, Event, bus
from src.voice.tts import tts
from src.voice.vad import vad

logger = logging.getLogger("hugo.voice.pipeline")

# VAD expects 512-sample chunks at 16kHz (32ms)
VAD_CHUNK_SAMPLES = 512
MIN_SPEECH_DURATION = 0.8  # seconds


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert float32 audio array to WAV bytes for Gemini API."""
    int16_audio = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_audio.tobytes())
    return buf.getvalue()


class VoicePipeline:
    def __init__(self) -> None:
        self._running = False
        self._speech_buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._models_loaded = False
        self._gemini_client: genai.Client | None = None

    def _load_models(self) -> None:
        if self._models_loaded:
            return
        vad.load()
        tts.load()
        self._models_loaded = True

    async def start(self) -> None:
        if self._running:
            logger.warning("Voice pipeline already running")
            return

        await asyncio.to_thread(self._load_models)
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._speech_buffer = []

        # Init Gemini client for STT
        if not settings.gemini_api_key:
            raise RuntimeError("HUGO_GEMINI_API_KEY not set – required for voice STT")
        self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini STT ready (model=%s)", settings.gemini_model)

        # Log default input device
        try:
            default_device = sd.query_devices(kind="input")
            logger.info(
                "Using input device: '%s' (index=%s, channels=%d, sr=%.0f)",
                default_device["name"],
                default_device["index"],
                default_device["max_input_channels"],
                default_device["default_samplerate"],
            )
        except Exception:
            logger.warning("Could not query default input device")

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

        if result["speech_start"]:
            logger.info("VAD: speech started (confidence=%.2f)", result["confidence"])

        if result["is_speaking"]:
            self._speech_buffer.append(chunk)

        if result["speech_end"] and self._speech_buffer:
            duration = len(self._speech_buffer) * VAD_CHUNK_SAMPLES / settings.sample_rate
            logger.info("VAD: speech ended (%.1fs, %d chunks)", duration, len(self._speech_buffer))
            if duration < MIN_SPEECH_DURATION:
                logger.info("VAD: too short (%.1fs), discarding", duration)
                self._speech_buffer = []
                vad.reset()
                return
            audio = np.concatenate(self._speech_buffer)
            self._speech_buffer = []
            vad.reset()
            if self._loop is not None:
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._handle_speech(audio),
                )

    async def _handle_speech(self, audio: np.ndarray) -> None:
        duration = len(audio) / settings.sample_rate
        logger.info("STT: transcribing %.1fs of audio via Gemini...", duration)
        try:
            text = await self._transcribe_with_gemini(audio)
        except Exception:
            logger.exception("Gemini STT failed")
            return
        if not text or len(text.strip()) < 2:
            logger.info("STT: empty or too-short transcript, skipping")
            return
        # Filter out prompt echo — Gemini sometimes returns the instruction text
        # when the audio is unclear
        if "transcribe" in text.lower() and "audio" in text.lower():
            logger.info("STT: prompt echo detected, skipping: '%s'", text)
            return
        logger.info("Transcribed: '%s'", text)
        await bus.emit(Event(
            type=TRANSCRIPT_READY,
            data={"text": text.strip()},
            source="voice",
        ))

    async def _transcribe_with_gemini(self, audio: np.ndarray) -> str:
        """Send audio to Gemini API for transcription."""
        if self._gemini_client is None:
            raise RuntimeError("Gemini client not initialized")

        wav_bytes = await asyncio.to_thread(_audio_to_wav_bytes, audio, settings.sample_rate)

        response = await self._gemini_client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=wav_bytes,
                                mime_type="audio/wav",
                            )
                        ),
                        types.Part(
                            text="Transcribe this English audio exactly as spoken. Return ONLY the transcription text, nothing else. If the audio contains no intelligible English speech, return an empty string."
                        ),
                    ]
                )
            ],
        )
        return (response.text or "").strip()

    async def speak(self, text: str) -> None:
        """Speak text via Kokoro TTS, pausing mic capture during playback."""
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
