"""MLX Whisper STT – transcribes audio buffers to text."""

import logging

import numpy as np

from src.config import settings

logger = logging.getLogger("hugo.stt")

# Common Whisper hallucination phrases on silence/noise
_HALLUCINATION_PHRASES = frozenset({
    "thank you",
    "thanks for watching",
    "thanks for listening",
    "subscribe",
    "like and subscribe",
    "bye",
    "goodbye",
    "you",
    "the end",
    "",
})


class SpeechToText:
    def __init__(self, model_name: str = settings.stt_model) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def load(self) -> None:
        from mlx_audio.stt.generate import load_model

        self._model = load_model(self.model_name)
        logger.info("MLX Whisper STT loaded: %s", self.model_name)

    def transcribe(self, audio: np.ndarray, sample_rate: int = settings.sample_rate) -> str:
        """Transcribe audio numpy array to text."""
        if self._model is None:
            raise RuntimeError("STT model not loaded – call load() first")

        result = self._model.generate(
            audio,
            language="en",
            condition_on_previous_text=False,
            no_speech_threshold=0.4,
            logprob_threshold=-0.8,
            compression_ratio_threshold=2.4,
            temperature=0.0,
            verbose=False,
        )

        # Extract text from result
        if hasattr(result, "segments") and result.segments:
            # Filter segments by no_speech_prob
            filtered = [
                seg for seg in result.segments
                if seg.get("no_speech_prob", 0) < 0.4
                and seg.get("avg_logprob", -999) > -0.8
            ]
            if not filtered:
                logger.info("STT: all segments filtered out (likely silence/noise)")
                return ""
            text = " ".join(seg["text"] for seg in filtered).strip()
        elif hasattr(result, "text"):
            text = result.text.strip()
        elif isinstance(result, dict):
            text = result.get("text", "").strip()
        else:
            text = str(result).strip()

        # Filter known hallucination phrases
        if text.lower().rstrip(".!?,") in _HALLUCINATION_PHRASES:
            logger.info("STT: filtered hallucination phrase: '%s'", text)
            return ""

        return text


stt = SpeechToText()
