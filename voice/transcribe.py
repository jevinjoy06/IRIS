"""Moonshine speech-to-text wrapper."""
import numpy as np


class Transcriber:
    """Lazy-load Moonshine on first use so startup is fast."""

    def __init__(self, model_name: str = "moonshine/base") -> None:
        self._model_name = model_name
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            # Prefer the ONNX model — faster, no Keras/torch graph overhead.
            from moonshine.onnx_model import MoonshineOnnxModel  # type: ignore
            self._model = MoonshineOnnxModel(model_name=self._model_name)
            self._backend = "onnx"
            print(f"[transcribe] Moonshine ONNX ready ({self._model_name})")
        except Exception:
            # Fall back to Keras model (needs KERAS_BACKEND=torch in env).
            import moonshine  # type: ignore
            self._model = moonshine
            self._backend = "keras"
            print(f"[transcribe] Moonshine Keras ready ({self._model_name})")

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 numpy array at 16 kHz, shape (N,)."""
        self._load()
        if self._backend == "onnx":
            tokens = self._model.generate(audio)
            result = self._model.tokenizer.decode_batch(tokens)
            return result[0] if isinstance(result, list) else str(result)
        else:
            result = self._model.transcribe(audio, self._model_name)
            return result[0] if isinstance(result, list) else str(result)
