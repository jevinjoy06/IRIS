"""Tests for voice/transcribe.py — Transcriber class."""
import sys
from unittest.mock import MagicMock, patch

import numpy as np

from voice.transcribe import Transcriber


class TestTranscriberConstructor:
    """Test Transcriber constructor and initial state."""

    def test_constructor_default_model_name(self):
        """Default model name should be 'moonshine/base'."""
        t = Transcriber()
        assert t._model_name == "moonshine/base"

    def test_constructor_custom_model_name(self):
        """Constructor should store a custom model name."""
        t = Transcriber(model_name="moonshine/tiny")
        assert t._model_name == "moonshine/tiny"

    def test_model_is_none_before_first_call(self):
        """Model should not be loaded until transcribe() is called."""
        t = Transcriber()
        assert t._model is None


class TestTranscriberLazyLoading:
    """Test that Transcriber loads the model on the first transcribe() call only."""

    def test_model_loaded_on_first_transcribe(self):
        """_model should be set after the first transcribe() call."""
        t = Transcriber()
        assert t._model is None

        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = ["hello world"]

        mock_onnx = MagicMock()
        mock_onnx.MoonshineOnnxModel = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"moonshine.onnx_model": mock_onnx}):
            t.transcribe(np.zeros(1000, dtype=np.float32))

        assert t._model is not None

    def test_model_not_reloaded_on_subsequent_calls(self):
        """MoonshineOnnxModel constructor should only be called once."""
        t = Transcriber()

        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = ["hello"]

        mock_onnx = MagicMock()
        mock_onnx.MoonshineOnnxModel = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"moonshine.onnx_model": mock_onnx}):
            audio = np.zeros(1000, dtype=np.float32)
            t.transcribe(audio)
            t.transcribe(audio)

        mock_onnx.MoonshineOnnxModel.assert_called_once()


class TestTranscriberONNX:
    """Test Transcriber using the ONNX backend (pre-loaded, no I/O)."""

    def _make(self, mock_model):
        """Return a Transcriber pre-loaded with the ONNX backend."""
        t = Transcriber()
        t._model = mock_model
        t._backend = "onnx"
        return t

    def test_transcribe_returns_string(self):
        """ONNX backend should return a plain string."""
        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = ["hello world"]

        t = self._make(mock_model)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert isinstance(result, str)
        assert result == "hello world"

    def test_transcribe_handles_list_return(self):
        """When decode_batch returns a list, first element should be used."""
        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = ["first", "second"]

        t = self._make(mock_model)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert result == "first"

    def test_transcribe_handles_str_return(self):
        """When decode_batch returns a plain str, it should be used directly."""
        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = "hello"

        t = self._make(mock_model)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert result == "hello"

    def test_transcribe_calls_generate_with_audio(self):
        """ONNX backend should pass the audio array to model.generate()."""
        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.tokenizer.decode_batch.return_value = ["test"]

        t = self._make(mock_model)
        audio = np.ones(500, dtype=np.float32)
        t.transcribe(audio)

        mock_model.generate.assert_called_once_with(audio)


class TestTranscriberKeras:
    """Test Transcriber using the Keras backend (pre-loaded, no I/O)."""

    def _make(self, mock_moonshine):
        """Return a Transcriber pre-loaded with the Keras backend."""
        t = Transcriber()
        t._model = mock_moonshine
        t._backend = "keras"
        return t

    def test_transcribe_returns_string(self):
        """Keras backend should return a plain string."""
        mock_moonshine = MagicMock()
        mock_moonshine.transcribe.return_value = ["hello world"]

        t = self._make(mock_moonshine)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert isinstance(result, str)
        assert result == "hello world"

    def test_transcribe_handles_list_return(self):
        """When transcribe() returns a list, first element should be used."""
        mock_moonshine = MagicMock()
        mock_moonshine.transcribe.return_value = ["first", "second"]

        t = self._make(mock_moonshine)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert result == "first"

    def test_transcribe_handles_str_return(self):
        """When transcribe() returns a plain str, it should be used directly."""
        mock_moonshine = MagicMock()
        mock_moonshine.transcribe.return_value = "hello"

        t = self._make(mock_moonshine)
        result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert result == "hello"

    def test_transcribe_passes_model_name(self):
        """Keras backend should call transcribe(audio, model_name)."""
        mock_moonshine = MagicMock()
        mock_moonshine.transcribe.return_value = ["result"]

        t = self._make(mock_moonshine)
        t._model_name = "moonshine/tiny"
        audio = np.zeros(500, dtype=np.float32)
        t.transcribe(audio)

        mock_moonshine.transcribe.assert_called_once_with(audio, "moonshine/tiny")


class TestTranscriberFallback:
    """Test Transcriber fallback from ONNX to Keras backend."""

    def test_falls_back_to_keras_when_onnx_raises(self):
        """If ONNX constructor raises, Keras backend should be used instead."""
        t = Transcriber()

        mock_onnx = MagicMock()
        mock_onnx.MoonshineOnnxModel = MagicMock(
            side_effect=RuntimeError("ONNX unavailable")
        )

        mock_moonshine = MagicMock()
        mock_moonshine.transcribe.return_value = ["keras result"]

        with patch.dict(
            sys.modules,
            {"moonshine.onnx_model": mock_onnx, "moonshine": mock_moonshine},
        ):
            result = t.transcribe(np.zeros(1000, dtype=np.float32))

        assert t._backend == "keras"
        assert result == "keras result"
