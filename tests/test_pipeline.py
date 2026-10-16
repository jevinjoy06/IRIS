"""Tests for voice/pipeline.py — Pipeline class and state machine."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice.pipeline import (
    MAX_RECORD_FRAMES,
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

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_returns_sleeping_on_timeout(self, mock_time):
        """_active_loop should return SLEEPING if no speech for timeout duration."""
        pipeline = Pipeline({"active_session_timeout_seconds": 30})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        # Time progression: last_speech_time=0, then jumps to 35s (timeout is 30s)
        time_values = [0, 35]  # Called: last_speech_time, first check in loop
        mock_time.side_effect = time_values

        # _record_utterance returns None (no speech)
        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=None):
            with patch("websockets.connect", return_value=mock_connect_cm):
                result = await pipeline._active_loop(mock_stream, mock_vad, mock_transcriber, mock_tts)

        assert result == PipelineState.SLEEPING
        mock_tts.speak.assert_called_with("Okay, going back to sleep")

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_timeout_not_triggered_within_threshold(self, mock_time):
        """_active_loop should not timeout if speech detected within threshold."""
        pipeline = Pipeline({"active_session_timeout_seconds": 30})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        # Mock successful recording and transcription
        audio = np.ones(1000, dtype=np.float32)

        # last_speech_time=0, loop check=5 (ok, 5-0=5 not > 30), record audio,
        # update last_speech=5, then _send_and_speak returns False → exit
        time_values = [0, 5, 5]
        mock_time.side_effect = time_values

        # First call records utterance, second check time within limit
        with patch.object(
            pipeline, "_record_utterance", side_effect=[audio, None]
        ) as mock_record:
            mock_ws = AsyncMock()
            mock_connect_cm = AsyncMock()
            mock_connect_cm.__aenter__.return_value = mock_ws
            mock_connect_cm.__aexit__.return_value = None

            with patch("websockets.connect", return_value=mock_connect_cm):
                with patch.object(
                    pipeline,
                    "_send_and_speak",
                    new_callable=AsyncMock,
                    return_value=False,  # Force exit
                ):
                    mock_transcriber.transcribe.return_value = "hello"

                    result = await pipeline._active_loop(
                        mock_stream, mock_vad, mock_transcriber, mock_tts
                    )

        # Should have returned SLEEPING due to hub error, not timeout
        assert result == PipelineState.SLEEPING


class TestStopPhraseDetection:
    """Test Pipeline._active_loop() stop phrase detection."""

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_detects_stop_phrase(self, mock_time):
        """_active_loop should detect stop phrases and return SLEEPING."""
        pipeline = Pipeline({"stop_phrases": ["stop", "goodbye"]})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        # last_speech_time=0, loop check=5 ok, update=5, then stop phrase → return
        mock_time.side_effect = [0, 5, 5]

        # Transcribe returns "goodbye" (stop phrase)
        mock_transcriber.transcribe.return_value = "goodbye"

        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch("websockets.connect", return_value=mock_connect_cm):
                with patch.object(
                    pipeline,
                    "_send_and_speak",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await pipeline._active_loop(
                        mock_stream, mock_vad, mock_transcriber, mock_tts
                    )

        assert result == PipelineState.SLEEPING
        mock_tts.speak.assert_called_with("Goodbye")

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_stop_phrase_case_insensitive(self, mock_time):
        """Stop phrase detection should be case insensitive."""
        pipeline = Pipeline({"stop_phrases": ["stop"]})

        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        # last_speech_time=0, loop check=5 ok, update=5, then stop phrase → return
        mock_time.side_effect = [0, 5, 5]

        # Return uppercase stop phrase
        mock_transcriber.transcribe.return_value = "STOP"

        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch("websockets.connect", return_value=mock_connect_cm):
                with patch.object(
                    pipeline,
                    "_send_and_speak",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await pipeline._active_loop(
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

        # Mock WebSocket directly (no longer opens its own connection)
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

        result = await pipeline._send_and_speak("test message", mock_tts, mock_ws)

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

        await pipeline._send_and_speak("test", mock_tts, mock_ws)

        # Should speak the full accumulated text
        mock_tts.speak.assert_called_once_with("The quick brown fox")

    @pytest.mark.asyncio
    async def test_send_and_speak_returns_false_on_error_message(self):
        """_send_and_speak should return False if hub returns error."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        mock_ws = AsyncMock()

        async def async_iter():
            yield '{"type": "error", "text": "Something went wrong"}'

        mock_ws.__aiter__ = lambda self: async_iter()

        result = await pipeline._send_and_speak("test", mock_tts, mock_ws)

        assert result is False
        # Should not speak on error
        mock_tts.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_and_speak_returns_false_on_connection_error(self):
        """_send_and_speak should return False if send fails."""
        pipeline = Pipeline({})
        mock_tts = MagicMock()

        mock_ws = AsyncMock()
        mock_ws.send.side_effect = Exception("Connection failed")

        result = await pipeline._send_and_speak("test", mock_tts, mock_ws)

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

        result = await pipeline._send_and_speak("test", mock_tts, mock_ws)

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

        await pipeline._send_and_speak("Hello Hub", mock_tts, mock_ws)

        # Verify the message was formatted correctly
        sent_msg = mock_ws.send.call_args[0][0]
        import json
        parsed = json.loads(sent_msg)
        assert parsed["type"] == "message"
        assert parsed["text"] == "Hello Hub"


class TestPipelineConstructorUARTConfig:
    """Test Pipeline constructor UART configuration fields."""

    def test_constructor_uart_port_defaults_to_none(self):
        """uart_port should default to None when not in config."""
        pipeline = Pipeline({})
        assert pipeline.uart_port is None

    def test_constructor_uart_port_custom(self):
        """Constructor should load custom uart_wake_port."""
        pipeline = Pipeline({"uart_wake_port": "COM3"})
        assert pipeline.uart_port == "COM3"

    def test_constructor_uart_baud_default(self):
        """uart_baud should default to 115200."""
        pipeline = Pipeline({})
        assert pipeline.uart_baud == 115200

    def test_constructor_uart_baud_custom(self):
        """Constructor should load custom uart_wake_baud."""
        pipeline = Pipeline({"uart_wake_baud": 9600})
        assert pipeline.uart_baud == 9600

    def test_constructor_uart_listener_initially_none(self):
        """_uart_listener should be None before run() is called."""
        pipeline = Pipeline({})
        assert pipeline._uart_listener is None


class TestSleepingLoop:
    """Test Pipeline._sleeping_loop() wake detection."""

    def _setup(self):
        pipeline = Pipeline({})
        raw_frame = np.zeros(1280, dtype=np.int16)
        mock_stream = MagicMock()
        mock_stream.read.return_value = (raw_frame, None)
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()
        return pipeline, mock_stream, mock_vad, mock_transcriber, mock_tts

    def test_sleeping_loop_returns_active_on_wake_word(self):
        """_sleeping_loop should return ACTIVE when OWW score exceeds threshold."""
        pipeline, stream, vad, transcriber, tts = self._setup()
        mock_oww = MagicMock()
        mock_oww.prediction_buffer = {"hey_jarvis": [0.9]}

        result = pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        assert result == PipelineState.ACTIVE

    def test_sleeping_loop_speaks_yes_on_wake_word(self):
        """_sleeping_loop should call tts.speak('Yes') when wake word triggers."""
        pipeline, stream, vad, transcriber, tts = self._setup()
        mock_oww = MagicMock()
        mock_oww.prediction_buffer = {"hey_jarvis": [0.9]}

        pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        tts.speak.assert_called_once_with("Yes")

    def test_sleeping_loop_score_at_threshold_does_not_trigger(self):
        """Score exactly at threshold should not trigger (condition is score > threshold)."""
        pipeline, stream, vad, transcriber, tts = self._setup()
        pipeline.wake_word_threshold = 0.5

        scores = [0.5, 0.9]  # First at threshold (no trigger), second above (trigger)
        call_count = [0]
        buf = {"hey_jarvis": [0.5]}

        def update(audio):
            buf["hey_jarvis"] = [scores[call_count[0]]]
            call_count[0] += 1

        mock_oww = MagicMock()
        mock_oww.predict.side_effect = update
        mock_oww.prediction_buffer = buf

        result = pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        assert result == PipelineState.ACTIVE
        assert call_count[0] == 2  # Looped once before triggering

    def test_sleeping_loop_returns_active_on_uart_trigger(self):
        """_sleeping_loop should return ACTIVE when UART hardware trigger fires."""
        pipeline, stream, vad, transcriber, tts = self._setup()

        mock_oww = MagicMock()
        mock_oww.prediction_buffer = {"hey_jarvis": [0.0]}  # OWW never triggers

        pipeline._uart_listener = MagicMock()
        pipeline._uart_listener.triggered.return_value = True

        result = pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        assert result == PipelineState.ACTIVE

    def test_sleeping_loop_speaks_yes_on_uart_trigger(self):
        """_sleeping_loop should call tts.speak('Yes') when UART trigger fires."""
        pipeline, stream, vad, transcriber, tts = self._setup()

        mock_oww = MagicMock()
        mock_oww.prediction_buffer = {"hey_jarvis": [0.0]}

        pipeline._uart_listener = MagicMock()
        pipeline._uart_listener.triggered.return_value = True

        pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        tts.speak.assert_called_once_with("Yes")

    def test_sleeping_loop_no_uart_check_when_listener_is_none(self):
        """No UART listener → triggered() should never be called."""
        pipeline, stream, vad, transcriber, tts = self._setup()
        assert pipeline._uart_listener is None  # Default

        mock_oww = MagicMock()
        mock_oww.prediction_buffer = {"hey_jarvis": [0.9]}  # OWW triggers immediately

        # Should complete without AttributeError on None._uart_listener
        result = pipeline._sleeping_loop(stream, mock_oww, vad, transcriber, tts)

        assert result == PipelineState.ACTIVE


class TestActiveLoopEdgeCases:
    """Additional edge cases for Pipeline._active_loop()."""

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_skips_hub_on_empty_transcript(self, mock_time):
        """Whitespace-only transcript should not invoke _send_and_speak."""
        pipeline = Pipeline({})
        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        # last_speech_time=0
        # iter1: check=5 ok, record→audio, last_speech=5, transcribe=" " → empty → continue
        # iter2: check=36 → 36-5=31 > 30 → timeout → return SLEEPING
        mock_time.side_effect = [0, 5, 5, 36]
        mock_transcriber.transcribe.return_value = "   "

        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch("websockets.connect", return_value=mock_connect_cm):
                with patch.object(
                    pipeline, "_send_and_speak", new_callable=AsyncMock
                ) as mock_sas:
                    result = await pipeline._active_loop(
                        mock_stream, mock_vad, mock_transcriber, mock_tts
                    )

        mock_sas.assert_not_called()
        assert result == PipelineState.SLEEPING

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_returns_sleeping_on_hub_error(self, mock_time):
        """_active_loop should return SLEEPING when hub sends an error."""
        pipeline = Pipeline({})
        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        mock_time.side_effect = [0, 5, 5]
        mock_transcriber.transcribe.return_value = "hello iris"

        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch("websockets.connect", return_value=mock_connect_cm):
                with patch.object(
                    pipeline, "_send_and_speak", new_callable=AsyncMock, return_value=False
                ):
                    result = await pipeline._active_loop(
                        mock_stream, mock_vad, mock_transcriber, mock_tts
                    )

        assert result == PipelineState.SLEEPING

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_active_loop_stop_phrase_as_substring(self, mock_time):
        """Stop phrase embedded in longer utterance should still trigger session end."""
        pipeline = Pipeline({"stop_phrases": ["stop"]})
        mock_stream = MagicMock()
        mock_vad = MagicMock()
        mock_transcriber = MagicMock()
        mock_tts = MagicMock()

        audio = np.ones(1000, dtype=np.float32)
        mock_time.side_effect = [0, 5, 5]
        mock_transcriber.transcribe.return_value = "please stop listening"

        mock_ws = AsyncMock()
        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch.object(pipeline, "_record_utterance", return_value=audio):
            with patch("websockets.connect", return_value=mock_connect_cm):
                result = await pipeline._active_loop(
                    mock_stream, mock_vad, mock_transcriber, mock_tts
                )

        assert result == PipelineState.SLEEPING
        mock_tts.speak.assert_called_with("Goodbye")


class TestRecordUtteranceEdgeCases:
    """Edge cases for Pipeline._record_utterance() hard cap and frame count."""

    @patch("voice.pipeline.MAX_RECORD_FRAMES", 5)
    def test_record_utterance_hard_cap_returns_none_when_below_min_speech(self):
        """When MAX_RECORD_FRAMES hit with fewer than MIN_SPEECH_FRAMES, return None."""
        pipeline = Pipeline({})
        raw_frame = np.ones(VAD_FRAME_SAMPLES, dtype=np.int16) * 100
        mock_stream = MagicMock()
        mock_stream.read.return_value = (raw_frame, None)
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = True  # Always speech — silence cutoff never fires

        # MAX=5 frames < MIN_SPEECH_FRAMES=8 → returns None
        result = pipeline._record_utterance(mock_stream, mock_vad)

        assert result is None

    @patch("voice.pipeline.MAX_RECORD_FRAMES", 15)
    def test_record_utterance_hard_cap_returns_audio_when_enough_frames(self):
        """When MAX_RECORD_FRAMES hit with enough frames, return float32 audio."""
        pipeline = Pipeline({})
        raw_frame = np.ones(VAD_FRAME_SAMPLES, dtype=np.int16) * 100
        mock_stream = MagicMock()
        mock_stream.read.return_value = (raw_frame, None)
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = True  # Always speech

        # MAX=15 frames >= MIN_SPEECH_FRAMES=8 → returns audio
        result = pipeline._record_utterance(mock_stream, mock_vad)

        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
