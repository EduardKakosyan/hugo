"""Wake-word detection via openWakeWord (ONNX backend only — see pyproject.toml's
`tool.uv.override-dependencies`: openwakeword hard-depends on tflite-runtime
on Linux, which has no Python 3.12 wheels, but the ONNX backend doesn't need
it at all — confirmed on dgx1, 2026-07-13).

No pretrained "Hey HUGO" model exists yet — custom wake words need training
(openWakeWord ships a training pipeline for this). Defaults to a stock
pretrained phrase (see DEFAULT_MODEL) as a placeholder; training a real
"Hey HUGO" model is a follow-up, not a v1 blocker. Config.wake_word already
makes this swappable.
"""

from pathlib import Path

import numpy as np
import openwakeword.utils
from openwakeword.model import Model

DEFAULT_MODEL = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5


class WakeWordDetector:
    def __init__(
        self, model_name: str = DEFAULT_MODEL, threshold: float = DEFAULT_THRESHOLD
    ) -> None:
        is_custom_model_file = model_name.endswith(".onnx")
        if not is_custom_model_file:
            # Model() doesn't auto-download its pretrained weights —
            # confirmed by a fresh-clone failure on dgx1 (2026-07-13).
            # Ensure they're present rather than requiring a separate
            # manual step first. A custom model (a path to an .onnx, e.g.
            # a trained hey_hugo) skips this: only the shared preprocessor
            # models are needed and they're already on disk from the
            # stock-model era.
            openwakeword.utils.download_models([model_name])
        self._model = Model(wakeword_models=[model_name], inference_framework="onnx")
        # openWakeWord keys its score dict by the file stem for custom
        # model paths, and by the plain name for stock models.
        self._model_name = Path(model_name).stem if is_custom_model_file else model_name
        self._threshold = threshold
        # Diagnostic hook, not used by feed()'s own return value -- lets a
        # caller (e.g. `hugo dev wake`) observe how close a frame came to
        # triggering, not just the thresholded bool.
        self.last_score: float = 0.0

    def feed(self, pcm16_chunk: bytes) -> bool:
        """Feed one chunk of 16kHz mono int16 PCM audio. Returns True the
        moment the wake word's score crosses the detection threshold."""
        samples = np.frombuffer(pcm16_chunk, dtype=np.int16)
        scores = self._model.predict(samples)
        self.last_score = float(scores.get(self._model_name, 0.0))
        return self.last_score >= self._threshold

    def reset(self) -> None:
        self._model.reset()
