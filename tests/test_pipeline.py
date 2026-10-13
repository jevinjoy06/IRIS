"""Tests for voice/pipeline.py — Pipeline class and state machine."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice.pipeline import (
    SILENCE_CUTOFF_FRAMES,
    MIN_SPEECH_FRAMES,
    SAMPLE_RATE,
    VAD_FRAME_SAMPLES,
    Pipeline,
    PipelineState,
)


class TestPipelineState:
    """Test PipelineState enum."""

    def test_pipeline_state_has_sleeping(self):
        """PipelineState should have SLEEPING value."""
        assert hasattr(PipelineState, "SLEEPING")
        assert PipelineState.SLEEPING.value == "sleeping"

    def test_pipeline_state_has_active(self):
        """PipelineState should have ACTIVE value."""
        assert hasattr(PipelineState, "ACTIVE")
        assert PipelineState.ACTIVE.value == "active"


class TestPipelineConstructor:
    """Test Pipeline constructor and configuration loading."""

    def test_constructor_loads_hub_url_default(self):
        """Constructor should load hub_url with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.hub_url == "ws://localhost:7865/ws"

    def test_constructor_loads_hub_url_custom(self):
        """Constructor should load custom hub_url from config."""
        cfg = {"hub_url": "ws://192.168.1.100:7865/ws"}
        pipeline = Pipeline(cfg)
        assert pipeline.hub_url == "ws://192.168.1.100:7865/ws"

    def test_constructor_loads_wake_word_model_default(self):
        """Constructor should load wake_word_model with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.wake_word_model == "hey_jarvis"

    def test_constructor_loads_wake_word_model_custom(self):
        """Constructor should load custom wake_word_model."""
        cfg = {"wake_word_model": "computer"}
        pipeline = Pipeline(cfg)
        assert pipeline.wake_word_model == "computer"

    def test_constructor_loads_wake_word_threshold_default(self):
        """Constructor should load wake_word_threshold with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.wake_word_threshold == 0.5

    def test_constructor_loads_wake_word_threshold_custom(self):
        """Constructor should load custom threshold."""
        cfg = {"wake_word_threshold": 0.7}
        pipeline = Pipeline(cfg)
        assert pipeline.wake_word_threshold == 0.7

    def test_constructor_loads_active_session_timeout_default(self):
        """Constructor should load timeout with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.active_session_timeout == 30

    def test_constructor_loads_active_session_timeout_custom(self):
        """Constructor should load custom timeout."""
        cfg = {"active_session_timeout_seconds": 60}
        pipeline = Pipeline(cfg)
        assert pipeline.active_session_timeout == 60

    def test_constructor_loads_stop_phrases_default(self):
        """Constructor should load default stop phrases."""
        cfg = {}
        pipeline = Pipeline(cfg)
        expected = ["stop", "goodbye", "that's all", "sleep", "nevermind"]
        assert pipeline.stop_phrases == expected

    def test_constructor_loads_stop_phrases_custom(self):
        """Constructor should load custom stop phrases."""
        cfg = {"stop_phrases": ["exit", "quit"]}
        pipeline = Pipeline(cfg)
        assert pipeline.stop_phrases == ["exit", "quit"]

    def test_constructor_loads_tts_rate_default(self):
        """Constructor should load tts_rate with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.tts_rate == 175

    def test_constructor_loads_tts_rate_custom(self):
        """Constructor should load custom tts_rate."""
        cfg = {"tts_rate": 200}
        pipeline = Pipeline(cfg)
        assert pipeline.tts_rate == 200

    def test_constructor_loads_tts_volume_default(self):
        """Constructor should load tts_volume with default."""
        cfg = {}
        pipeline = Pipeline(cfg)
        assert pipeline.tts_volume == 0.9

    def test_constructor_loads_tts_volume_custom(self):
        """Constructor should load custom tts_volume."""
        cfg = {"tts_volume": 0.5}
        pipeline = Pipeline(cfg)
        assert pipeline.tts_volume == 0.5

    def test_constructor_stores_full_config(self):
        """Constructor should store the full cfg dict."""
        cfg = {"hub_url": "ws://test:1234/ws", "custom_key": "custom_value"}
        pipeline = Pipeline(cfg)
        assert pipeline.cfg == cfg


class TestRecordUtterance:
    """Test Pipeline._record_utterance() method."""

    def _create_pipeline(self):
        """Helper to create Pipeline with minimal config."""
        return Pipeline({})

    def _create_mock_stream(self, vad_results):
        """Helper to create mock stream that returns audio frames and VAD results.

        Args:
            vad_results: List of booleans indicating is_speech for each frame.
        """
        stream = MagicMock()
        vad = MagicMock()

        # Create audio frames (480 samples each at 16 kHz, 30 ms)
        frame_index = [0]  # Use list to allow mutation in nested function

        def read_side_effect(num_samples):
            if frame_index[0] >= len(vad_results):
                # Return silence if we run out of results
                return np.zeros(num_samples, dtype=np.int16), None
            frame_index[0] += 1
            # Return a frame with some audio data (doesn't matter for test)
            return np.ones(num_samples, dtype=np.int16) * 100, None

        stream.read = MagicMock(side_effect=read_side_effect)

        # Set up VAD mock
        vad.is_speech = MagicMock(side_effect=vad_results)

        return stream, vad

    def test_record_utterance_returns_none_if_no_speech_in_5s(self):
        """_record_utterance should return None if no speech in first 5s."""
        pipeline = self._create_pipeline()

        # VAD always returns False (no speech)
        # 5 seconds at 16kHz with 480 samples per frame = ~167 frames
        # But we check if total > (5000 // 30) = 166, so 167 frames of silence returns None
        vad_results = [False] * 200
        stream, vad = self._create_mock_stream(vad_results)

        result = pipeline._record_utterance(stream, vad)

        assert result is None

    def test_record_utterance_returns_audio_on_speech_then_silence(self):
        """_record_utterance should return audio when speech then silence detected."""
        pipeline = self._create_pipeline()

        # Pattern: silence, then speech, then silence
        # 8 speech frames, then 20 silence frames (SILENCE_CUTOFF_FRAMES)
        vad_results = (
            [False] * 5
            + [True] * MIN_SPEECH_FRAMES
            + [False] * SILENCE_CUTOFF_FRAMES
        )
        stream, vad = self._create_mock_stream(vad_results)

        result = pipeline._record_utterance(stream, vad)

        # Should return a numpy array (concatenated frames)
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32

    def test_record_utterance_returns_none_if_empty_utterance(self):
        """_record_utterance should return None if no frames collected."""
        pipeline = self._create_pipeline()

        # Pattern: only initial silence (max 5 seconds = 167 frames of silence)
        # No speech detected at all before timeout
        vad_results = [False] * 200  # All silence, more than 5s worth
        stream, vad = self._create_mock_stream(vad_results)

        result = pipeline._record_utterance(stream, vad)

        # No speech detected, so no frames added to list
        assert result is None

    def test_record_utterance_audio_is_float32_normalized(self):
        """_record_utterance should return normalized float32 audio."""
        pipeline = self._create_pipeline()

        vad_results = (
            [False] * 5
            + [True] * MIN_SPEECH_FRAMES
            + [False] * SILENCE_CUTOFF_FRAMES
        )
        stream, vad = self._create_mock_stream(vad_results)

        result = pipeline._record_utterance(stream, vad)

        # Should be normalized to [-1.0, 1.0] range
        assert result.dtype == np.float32
        assert result.max() <= 1.0
        assert result.min() >= -1.0

    def test_record_utterance_resets_silence_count_on_speech(self):
        """_record_utterance should reset silence counter when speech resumes."""
        pipeline = self._create_pipeline()

        # Pattern: speech, silence, speech, silence (enough to end)
        vad_results = (
            [False] * 5  # Initial silence
            + [True] * MIN_SPEECH_FRAMES  # Speech started
            + [False] * 10  # Partial silence (not SILENCE_CUTOFF_FRAMES yet)
            + [True] * MIN_SPEECH_FRAMES  # More speech (resets silence counter)
            + [False] * SILENCE_CUTOFF_FRAMES  # Final silence ends recording
        )
        stream, vad = self._create_mock_stream(vad_results)

        result = pipeline._record_utterance(stream, vad)

        # Should have collected audio from both speech sections
        assert result is not None
        assert isinstance(result, np.ndarray)


class TestActiveLoopTimeout:
    """Test Pipeline._active_loop() timeout behavior."""

    @patch("time.time")
    def test_active_loop_returns_sleeping_on_timeout(self, mock_time):
        """_active_loop should return SLEEPING if no speech for timeout duration."""
        pipeline = Pipeline({"active_session_timeout_seconds": 30})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        # Time progression: session starts at 0, then jumps to 35s (timeout is 30s)
        time_values = [0, 0, 35]  # Called: initial, first check in loop, second check
        mock_time.side_effect = time_values

        # _record_utterance returns None (no speech)
        with patch.object(pipeline, "_record_utterance", return_value=None):
            result = pipeline._active_loop(mock_stream, mock_vad, mock_transcriber, mock_tts)

        assert result == PipelineState.SLEEPING
        mock_tts.speak.assert_called_with("Okay, going back to sleep")

    @patch("time.time")
    def test_active_loop_timeout_not_triggered_within_threshold(self, mock_time):
        """_active_loop should not timeout if speech detected within threshold."""
        pipeline = Pipeline({"active_session_timeout_seconds": 30})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        # Mock successful recording and transcription
        audio = np.ones(1000, dtype=np.float32)

        time_values = [0, 0, 5, 5, 10]  # Stay within timeout
        mock_time.side_effect = time_values

        # First call records utterance, second check time within limit
        with patch.object(
            pipeline, "_record_utterance", side_effect=[audio, None]
        ) as mock_record:
            with patch.object(
                pipeline,
                "_send_and_speak",
                new_callable=AsyncMock,
                return_value=False,  # Force exit
            ):
                mock_transcriber.transcribe.return_value = "hello"

                result = pipeline._active_loop(
                    mock_stream, mock_vad, mock_transcriber, mock_tts
                )

        # Should have returned SLEEPING due to hub error, not timeout
        assert result == PipelineState.SLEEPING


class TestStopPhraseDetection:
    """Test Pipeline._active_loop() stop phrase detection."""

    @patch("time.time")
    def test_active_loop_detects_stop_phrase(self, mock_time):
        """_active_loop should detect stop phrases and return SLEEPING."""
        pipeline = Pipeline({"stop_phrases": ["stop", "goodbye"]})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        # time.time() calls: session_start (2x), last_speech_time (2x), then check in loop
        mock_time.side_effect = [0, 0, 0, 0, 5]

        # Transcribe returns "goodbye" (stop phrase)
        mock_transcriber.transcribe.return_value = "goodbye"

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch.object(
                pipeline,
                "_send_and_speak",
                new_callable=AsyncMock,
                return_value=True,
            ):
                result = pipeline._active_loop(
                    mock_stream, mock_vad, mock_transcriber, mock_tts
                )

        assert result == PipelineState.SLEEPING
        mock_tts.speak.assert_called_with("Goodbye")

    @patch("time.time")
    def test_active_loop_stop_phrase_case_insensitive(self, mock_time):
        """Stop phrase detection should be case insensitive."""
        pipeline = Pipeline({"stop_phrases": ["stop"]})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        # time.time() calls: session_start (2x), last_speech_time (2x), then check in loop
        mock_time.side_effect = [0, 0, 0, 0, 5]

        # Return uppercase stop phrase
        mock_transcriber.transcribe.return_value = "STOP"

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch.object(
                pipeline,
                "_send_and_speak",
                new_callable=AsyncMock,
                return_value=True,
            ):
                result = pipeline._active_loop(
                    mock_stream, mock_vad, mock_transcriber, mock_tts
                )

        assert result == PipelineState.SLEEPING


class TestSendAndSpeak:
    """Test Pipeline._send_and_speak() async method."""

    @pytest.mark.asyncio
    async def test_send_and_speak_success_path(self):
        """_send_and_speak should successfully send message and handle response."""
        pipeline = Pipeline({"hub_url": "ws://localhost:7865/ws"})
        mock_tts = MagicMock()

        # Mock websockets.connect and the async context manager
        mock_ws = AsyncMock()
        messages = [
            '{"type": "token", "text": "Hello "}',
            '{"type": "token", "text": "world"}',
            '{"type": "done"}',
        ]

        async def async_iter():
            for msg in messages:
                yield msg

        mock_ws.__aiter__ = lambda self: async_iter()

        # Create async context manager that returns the mock WebSocket
        mock_connect = AsyncMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None

        with patch("websockets.connect", return_value=mock_connect):
            result = await pipeline._send_and_speak("test message", mock_tts)

        assert result is True
        assert mock_ws.send.called
        mock_tts.speak.assert_called_once_with("Hello world")

    @pytest.mark.asyncio
    async def test_send_and_speak_accumulates_tokens(self):
        """_send_and_speak should accumulate all tokens before speaking."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        tokens = ["The ", "quick ", "brown ", "fox"]
        messages = [f'{{"type": "token", "text": "{t}"}}' for t in tokens]
        messages.append('{"type": "done"}')

        mock_ws = AsyncMock()

        async def async_iter():
            for msg in messages:
                yield msg

        mock_ws.__aiter__ = lambda self: async_iter()

        mock_connect = AsyncMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None

        with patch("websockets.connect", return_value=mock_connect):
            await pipeline._send_and_speak("test", mock_tts)

        # Should speak the full accumulated text
        mock_tts.speak.assert_called_once_with("The quick brown fox")

    @pytest.mark.asyncio
    async def test_send_and_speak_returns_false_on_error_message(self):
        """_send_and_speak should return False if hub returns error."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        mock_ws = AsyncMock()
        mock_ws.__aiter__.return_value = [
            '{"type": "error", "text": "Something went wrong"}'
        ]

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_ws

            result = await pipeline._send_and_speak("test", mock_tts)

        assert result is False
        # Should not speak on error
        mock_tts.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_and_speak_returns_false_on_connection_error(self):
        """_send_and_speak should return False if connection fails."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            result = await pipeline._send_and_speak("test", mock_tts)

        assert result is False
        mock_tts.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_and_speak_returns_true_on_no_response_tokens(self):
        """_send_and_speak should return True even if no tokens received."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        mock_ws = AsyncMock()
        messages = ['{"type": "done"}']

        async def async_iter():
            for msg in messages:
                yield msg

        mock_ws.__aiter__ = lambda self: async_iter()

        mock_connect = AsyncMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None

        with patch("websockets.connect", return_value=mock_connect):
            result = await pipeline._send_and_speak("test", mock_tts)

        assert result is True
        # Should not speak if no tokens
        mock_tts.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_and_speak_formats_json_correctly(self):
        """_send_and_speak should format message as JSON correctly."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        mock_ws = AsyncMock()
        messages = ['{"type": "done"}']

        async def async_iter():
            for msg in messages:
                yield msg

        mock_ws.__aiter__ = lambda self: async_iter()

        mock_connect = AsyncMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None

        with patch("websockets.connect", return_value=mock_connect):
            await pipeline._send_and_speak("Hello Hub", mock_tts)

        # Verify the message was formatted correctly
        sent_msg = mock_ws.send.call_args[0][0]
        import json
        parsed = json.loads(sent_msg)
        assert parsed["type"] == "message"
        assert parsed["text"] == "Hello Hub"
