"""Voice pipeline — Pipecat-based VAD + local Whisper STT + Kokoro TTS."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VoiceConfig:
    """Configuration for the voice pipeline."""

    stt_model: str = "mlx-community/whisper-large-v3-turbo"
    tts_model: str = "prince-canuma/Kokoro-82M"
    sample_rate: int = 16000
    vad_threshold: float = 0.5
    silence_duration_ms: int = 700
    tts_speed: float = 1.0
    tts_voice: str = "af_heart"  # Kokoro voice preset


@dataclass
class TranscriptionResult:
    """Result from STT."""

    text: str
    language: str = "en"
    confidence: float = 1.0


@dataclass
class VoicePipeline:
    """Local voice pipeline: Silero VAD → Whisper MLX STT → Kokoro MLX TTS.

    All inference runs on Apple Silicon via MLX — no cloud calls.
    """

    config: VoiceConfig = field(default_factory=VoiceConfig)
    _vad_model: object | None = field(default=None, init=False, repr=False)
    _stt_pipeline: object | None = field(default=None, init=False, repr=False)
    _tts_pipeline: object | None = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False)

    async def initialize(self) -> None:
        """Load all models (VAD, STT, TTS). Call once at startup."""
        logger.info("Initializing voice pipeline...")
        await asyncio.gather(
            self._load_vad(),
            self._load_stt(),
            self._load_tts(),
        )
        logger.info("Voice pipeline ready")

    async def _load_vad(self) -> None:
        """Load Silero VAD model."""
        try:
            import torch  # type: ignore[import-untyped]

            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
            )
            self._vad_model = model
            logger.info("Silero VAD loaded")
        except Exception:
            logger.exception("Failed to load Silero VAD")
            raise

    async def _load_stt(self) -> None:
        """Load Whisper V3 Turbo via mlx-audio."""
        try:
            from mlx_audio.speech_recognition import load  # type: ignore[import-untyped]

            self._stt_pipeline = load(self.config.stt_model)
            logger.info("Whisper STT loaded: %s", self.config.stt_model)
        except Exception:
            logger.exception("Failed to load Whisper STT")
            raise

    async def _load_tts(self) -> None:
        """Load Kokoro TTS via mlx-audio."""
        try:
            from mlx_audio.tts import load  # type: ignore[import-untyped]

            self._tts_pipeline = load(self.config.tts_model)
            logger.info("Kokoro TTS loaded: %s", self.config.tts_model)
        except Exception:
            logger.exception("Failed to load Kokoro TTS")
            raise

    def detect_voice_activity(self, audio_chunk: np.ndarray) -> bool:
        """Run Silero VAD on an audio chunk. Returns True if speech detected."""
        if self._vad_model is None:
            return False

        import torch  # type: ignore[import-untyped]

        tensor = torch.from_numpy(audio_chunk).float()
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)

        confidence = self._vad_model(tensor, self.config.sample_rate)  # type: ignore[operator]
        return float(confidence) > self.config.vad_threshold

    async def transcribe(self, audio: np.ndarray) -> TranscriptionResult:
        """Transcribe audio to text using Whisper MLX.

        Args:
            audio: Audio as float32 numpy array, shape (samples,), sample_rate=16kHz.

        Returns:
            TranscriptionResult with text and detected language.
        """
        if self._stt_pipeline is None:
            msg = "STT pipeline not loaded"
            raise RuntimeError(msg)

        try:
            from mlx_audio.speech_recognition import transcribe  # type: ignore[import-untyped]

            result = transcribe(self._stt_pipeline, audio)
            text = result.get("text", "").strip()
            lang = result.get("language", "en")
            return TranscriptionResult(text=text, language=lang)
        except Exception:
            logger.exception("Transcription failed")
            return TranscriptionResult(text="", confidence=0.0)

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize text to audio using Kokoro TTS via MLX.

        Args:
            text: The text to speak.

        Returns:
            Audio as float32 numpy array at 24kHz.
        """
        if self._tts_pipeline is None:
            msg = "TTS pipeline not loaded"
            raise RuntimeError(msg)

        try:
            from mlx_audio.tts import generate  # type: ignore[import-untyped]

            audio = generate(
                self._tts_pipeline,
                text,
                voice=self.config.tts_voice,
                speed=self.config.tts_speed,
            )
            return np.array(audio, dtype=np.float32)
        except Exception:
            logger.exception("TTS synthesis failed")
            return np.array([], dtype=np.float32)

    async def listen(self) -> AsyncIterator[TranscriptionResult]:
        """Listen for voice input via microphone, yield transcriptions.

        Uses VAD to detect speech boundaries, then transcribes complete utterances.
        """
        import sounddevice as sd  # type: ignore[import-untyped]

        self._running = True
        chunk_size = int(self.config.sample_rate * 0.03)  # 30ms chunks
        silence_chunks = int(
            self.config.silence_duration_ms / 30
        )  # chunks of silence before cutoff
        audio_buffer: list[np.ndarray] = []
        silent_count = 0
        is_speaking = False

        logger.info("Listening for voice input...")

        stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
        )

        with stream:
            while self._running:
                chunk, _overflowed = stream.read(chunk_size)
                audio_data = chunk.flatten()

                has_speech = self.detect_voice_activity(audio_data)

                if has_speech:
                    if not is_speaking:
                        logger.debug("Speech started")
                        is_speaking = True
                    audio_buffer.append(audio_data)
                    silent_count = 0
                elif is_speaking:
                    audio_buffer.append(audio_data)
                    silent_count += 1

                    if silent_count >= silence_chunks:
                        # End of utterance — transcribe
                        logger.debug("Speech ended, transcribing...")
                        full_audio = np.concatenate(audio_buffer)
                        result = await self.transcribe(full_audio)

                        if result.text:
                            yield result

                        audio_buffer.clear()
                        silent_count = 0
                        is_speaking = False

                await asyncio.sleep(0)  # Yield to event loop

    async def play_audio(self, audio: np.ndarray, sample_rate: int = 24000) -> None:
        """Play audio through speakers."""
        import sounddevice as sd  # type: ignore[import-untyped]

        sd.play(audio, samplerate=sample_rate)
        sd.wait()

    async def speak(self, text: str) -> None:
        """Full TTS pipeline: synthesize text → play through speakers."""
        audio = await self.synthesize(text)
        if len(audio) > 0:
            await self.play_audio(audio)

    def stop(self) -> None:
        """Stop the listening loop."""
        self._running = False
